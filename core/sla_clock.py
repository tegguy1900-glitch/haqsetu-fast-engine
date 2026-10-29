"""
Haq Setu - SLA Clock Daemon (Pillar 3 completion + Pillar 2 owed-checklist expiry).
Scans the ONE ledger for open civic cases and unresolved Sabha commitments,
expires them against ISSUE_CLOCKS / resolved due-dates, and emits sla_breach
through the bus. Idempotent per case-per-rung. Never guesses a deadline.

Policy gate resolved as a CONFIG FLAG, not a hardcoded choice:
  HAQ_SLA_MODE = escalate (default) | soft
    escalate -> payload.escalated_to = next rung (dashboard RED + upward push)
    soft     -> payload.escalated_to = null   (dashboard AMBER, no push)
The decision is exposed as a knob; the default honors the recommendation that an
unkept Sabha promise must not quietly evaporate between village and block.

Reconciliation note: ISSUE_CLOCKS + LADDER here are self-contained because
box/civic_escalation.py's source was not available (uploaded files blank).
When that file returns, fold its tables in; the event contract stays identical.
"""
import os, time, datetime as _dt
from core import event_bus
from ledger import chain as _chain

MODE = (os.environ.get("HAQ_SLA_MODE", "escalate") or "escalate").strip().lower()

# hours-to-fix per asset category (drain 24 / handpump 48 mirror the legacy ladder)
ISSUE_CLOCKS = {
    "drain": 24, "handpump": 48, "water": 48, "streetlight": 72,
    "road": 168, "anganwadi": 168, "school": 168, "general": 168,
}
DEFAULT_HOURS = 168
PETITION_CLOCKS = {"default": int(os.environ.get("HAQ_PETITION_SLA_H", "72"))}  # hours to action a Haq Receipt
LADDER = ["panchayat", "block", "district", "state"]   # first breach -> rung[1]
FIRST_ESCALATION = LADDER[1]

_WD = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6,
       "somwar":0,"mangalwar":1,"budh":2,"guru":3,"shukrawar":4,"shani":5,"itwar":6,"ravivar":6,
       "mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
_ISO = _dt.datetime.strptime

def _resolve_deadline(raw, meeting_date):
    """raw phrase + meeting date -> due date, or None (NEVER invent)."""
    if not raw or not meeting_date:
        return None
    s = str(raw).strip().lower()
    try:
        md = _ISO(meeting_date, "%Y-%m-%d").date()
    except Exception:
        return None
    # explicit ISO date
    for tok in s.replace(",", " ").split():
        try:
            return _ISO(tok, "%Y-%m-%d").date()
        except Exception:
            pass
    if "today" in s or "aaj" in s:
        return md
    if "tomorrow" in s or "kal" in s:
        return md + _dt.timedelta(days=1)
    if "day after" in s or "parson" in s:
        return md + _dt.timedelta(days=2)
    # within N days / N din
    import re as _re
    m = _re.search(r"(\d+)\s*(?:day|days|din)", s)
    if m:
        return md + _dt.timedelta(days=int(m.group(1)))
    # weekday name -> next occurrence STRICTLY after meeting date
    for name, idx in _WD.items():
        if name in s:
            delta = (idx - md.weekday()) % 7 or 7
            return md + _dt.timedelta(days=delta)
    return None   # unresolvable -> caller skips + warns, never guesses

def _end_of_day(d):
    return _dt.datetime.combine(d, _dt.time(23, 59, 59)).timestamp()

def _load_state(events):
    open_civic, closed, breached_civic = {}, set(), set()
    commitments, breached_commit, fulfilled_commit, skipped = {}, set(), set(), []
    warnings = []
    for ev in events:
        t, p, cid = ev["event_type"], ev.get("payload", {}), ev.get("case_id", "")
        if t == "civic_intake":
            open_civic[cid] = {"ts": ev["timestamp"], "category": p.get("category", "general")}
        elif t == "civic_closure_verified":
            closed.add(cid); open_civic.pop(cid, None)
        elif t == "sla_breach" and p.get("kind") == "civic":
            breached_civic.add(cid)
        elif t == "sabha_signed":
            mh = (p.get("minutes_hash") or "")[:12]
            mdate = p.get("meeting_date")
            for i, a in enumerate(p.get("action_items", []) or []):
                ckey = f"COMMIT-{mh}-{i}"
                due = _resolve_deadline(a.get("deadline_raw"), mdate)
                if due is None:
                    skipped.append({"id": ckey, "raw": a.get("deadline_raw"),
                                    "reason": "unresolvable deadline; NOT guessing"})
                    warnings.append(f"[WARN] commitment {ckey} deadline "
                                    f"'{a.get('deadline_raw')}' unresolvable; NOT guessing a date.")
                    continue
                commitments[ckey] = {"owner": a.get("owner"), "task": a.get("task"),
                                     "due_date": due.isoformat(), "due_epoch": _end_of_day(due)}
        elif t == "sla_breach" and p.get("kind") == "commitment":
            breached_commit.add(p.get("commitment_id"))
        elif t == "commitment_fulfilled":
            fulfilled_commit.add(p.get("commitment_id"))
    return open_civic, closed, breached_civic, commitments, breached_commit, \
           fulfilled_commit, skipped, warnings


def _load_petitions(events):
    """Mirror of _load_state for Pillar 1 receipts. Open = issued & not resolved/rejected.
    Abstained cases carry NO clock (already escalated to a human by design) -> shown amber."""
    open_p, resolved, rejected, breached, abstained = {}, set(), set(), set(), []
    for ev in events:
        ty, p, cid = ev["event_type"], ev.get("payload", {}), ev.get("case_id", "")
        if ty == "entitlement_petition_issued":
            open_p[cid] = {"ts": ev["timestamp"], "schemes": p.get("schemes", []),
                           "confidence": p.get("confidence"), "receipt_id": p.get("receipt_id")}
        elif ty == "petition_resolved":
            resolved.add(cid); open_p.pop(cid, None)
        elif ty == "official_rejection":           # terminal honest outcome (has reason code)
            rejected.add(cid); open_p.pop(cid, None)
        elif ty == "sla_breach" and p.get("kind") == "petition":
            breached.add(cid)
        elif ty == "entitlement_abstained":
            abstained.append({"case_id": cid, "reason": p.get("reason"),
                              "confidence": p.get("confidence")})
    return open_p, resolved, rejected, breached, abstained

def status(events=None):
    events = events if events is not None else _chain.get_chain()
    oc, cl, bc, cm, bm, fm, sk, _ = _load_state(events)
    op, rs, rj, br, ab = _load_petitions(events)
    return {"open_civic": sorted(oc), "closed_civic": sorted(cl),
            "breached_civic": sorted(bc), "tracked_commitments": sorted(cm),
            "breached_commitments": sorted(bm), "fulfilled_commitments": sorted(fm),
            "skipped_commitments": sk,
            "open_petitions": sorted(op), "resolved_petitions": sorted(rs),
            "rejected_petitions": sorted(rj), "breached_petitions": sorted(br),
            "abstained_petitions": ab}

def tick(now=None, events=None):
    """Scan + expire + emit. Returns {emitted, warnings, status}. Idempotent."""
    if not event_bus.is_ready():
        event_bus.init()
    now = now if now is not None else time.time()
    events = events if events is not None else _chain.get_chain()
    oc, cl, bc, cm, bm, fm, sk, warns = _load_state(events)
    emitted = []
    # --- civic SLA expiry ---
    for cid, info in oc.items():
        if cid in bc:
            continue
        h = ISSUE_CLOCKS.get(info["category"], DEFAULT_HOURS)
        elapsed_h = (now - info["ts"]) / 3600.0
        if elapsed_h > h:
            esc = FIRST_ESCALATION if MODE == "escalate" else None
            ev = event_bus.emit("system", cid, "sla_breach", {
                "kind": "civic", "case_id": cid, "category": info["category"],
                "sla_hours": h, "hours_overdue": round(elapsed_h, 1),
                "mode": MODE, "escalated_to": esc})
            emitted.append(ev); bc.add(cid)
    # --- commitment (owed-checklist) expiry ---
    for ckey, c in cm.items():
        if ckey in bm or ckey in fm:
            continue
        if now > c["due_epoch"]:
            oh = round((now - c["due_epoch"]) / 3600.0, 1)
            esc = FIRST_ESCALATION if MODE == "escalate" else None
            ev = event_bus.emit("system", ckey, "sla_breach", {
                "kind": "commitment", "commitment_id": ckey, "owner": c["owner"],
                "due": c["due_date"], "hours_overdue": oh, "task": c["task"],
                "mode": MODE, "escalated_to": esc})
            emitted.append(ev); bm.add(ckey)
    # --- petition (Haq Receipt) expiry ---
    op, rs, rj, br, ab = _load_petitions(events)
    for pid, info in op.items():
        if pid in br:
            continue
        h = PETITION_CLOCKS["default"]
        elapsed_h = (now - info["ts"]) / 3600.0
        if elapsed_h > h:
            esc = FIRST_ESCALATION if MODE == "escalate" else None
            ev = event_bus.emit("system", pid, "sla_breach", {
                "kind": "petition", "case_id": pid, "receipt_id": info.get("receipt_id"),
                "schemes": info.get("schemes"), "sla_hours": h,
                "hours_overdue": round(elapsed_h, 1), "mode": MODE, "escalated_to": esc})
            emitted.append(ev); br.add(pid)
    return {"emitted": emitted, "warnings": warns, "status": status(events + emitted)}

def fulfill(commitment_id, owner=None):
    """Mark an owed-checklist item done so it stops breaching."""
    if not event_bus.is_ready():
        event_bus.init()
    return event_bus.emit(owner or "secretary", commitment_id,
                          "commitment_fulfilled", {"commitment_id": commitment_id,
                                                   "owner": owner or "secretary"})
