"""
Haq Setu - SDM View-Model (the rendering brain; NO port, NO source-of-truth).
chain + sabha_minutes sqlite  ->  a structured, color-tagged view dict.
State logic is IMPORTED from core.sla_clock._load_state so the board and the
clock daemon can never diverge on open/breached/fulfilled/skipped.
Color rules (legend mirrored in board.html):
  RED    = breach under escalate (act + pushed up)  OR unsigned/contested Sabha
  AMBER  = breach under soft (watch) OR Sabha signed-but-SDM-ack-pending
           OR commitment with UNRESOLVABLE deadline (needs a human date)
           OR civic/commitment within 80% of its clock (about to breach)
  GREEN  = closed civic (verified fix) OR fulfilled commitment OR Sabha acked
  SLATE  = open civic / owed commitment still within SLA (counting down)
Per-event policy is read from payload.mode/escalated_to (the env knob from the
daemon is honored here at RENDER time, not baked in).
"""
import os, time, datetime as _dt
from core import sla_clock as _clock
from core.sla_clock import _load_state, ISSUE_CLOCKS, DEFAULT_HOURS
from ledger import chain as _chain
from sabha import push_sdm as _db

def _iso(ts):
    return _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")

def _color_for_breach(payload):
    return "amber" if (payload or {}).get("mode") == "soft" else "red"

def _mh_map(events):
    """minutes_hash[:12] -> (gp, date) so commitments/civic can cite their Sabha."""
    m = {}
    for ev in events:
        if ev["event_type"] == "sabha_signed":
            p = ev.get("payload", {})
            mh = (p.get("minutes_hash") or "")[:12]
            if mh:
                m[mh] = (p.get("gp", "?"), p.get("meeting_date", "?"))
    return m

def _intake_meta(events):
    src, obm, evid = {}, {}, {}
    for ev in events:
        t, p, cid = ev["event_type"], ev.get("payload", {}), ev.get("case_id", "")
        if t == "civic_intake":
            src[cid] = p.get("source"); obm[cid] = p.get("opened_by_minutes")
        elif t == "civic_closure_verified":
            evid[cid] = p.get("photo_hash")
    return src, obm, evid

def _breach_meta(events):
    """case/commitment id -> {mode, escalated_to, hours_overdue} from sla_breach events."""
    out = {}
    for ev in events:
        if ev["event_type"] == "sla_breach":
            p = ev.get("payload", {})
            key = p.get("commitment_id") if p.get("kind") == "commitment" else ev.get("case_id")
            if key:
                out[key] = {"mode": p.get("mode"), "escalated_to": p.get("escalated_to"),
                            "hours_overdue": p.get("hours_overdue")}
    return out

def build(now=None, events=None):
    now = now if now is not None else time.time()
    events = events if events is not None else _chain.get_chain()
    oc, cl, bc, cm, bm, fm, sk, _warns = _load_state(events)
    mhmap = _mh_map(events)
    src, obm, evid = _intake_meta(events)
    bmeta = _breach_meta(events)

    # ---- civic board ----
    civic = []
    for cid, info in sorted(oc.items()):
        cat = info.get("category", "general")
        sla_h = ISSUE_CLOCKS.get(cat, DEFAULT_HOURS)
        elapsed_h = (now - info["ts"]) / 3600.0
        if cid in bc:
            state, color = "breached", _color_for_breach(bmeta.get(cid))
        elif cid in cl:
            state, color = "closed", "green"
        elif elapsed_h >= 0.8 * sla_h:
            state, color = "near_breach", "amber"
        else:
            state, color = "in_sla", "slate"
        mh = obm.get(cid)
        civic.append({
            "case_id": cid, "category": cat, "ward": info.get("ward"),
            "state": state, "color": color, "sla_hours": sla_h,
            "hours_elapsed": round(elapsed_h, 1),
            "hours_remaining": round(max(0.0, sla_h - elapsed_h), 1),
            "escalated_to": (bmeta.get(cid) or {}).get("escalated_to"),
            "breach_mode": (bmeta.get(cid) or {}).get("mode"),
            "evidence_hash": evid.get(cid),
            "from_sabha": ("%s %s" % mhmap[mh]) if (mh and mh in mhmap) else None,
        })
    # closed cases live in cl but not oc; add them
    for cid in sorted(cl - set(oc.keys())):
        civic.append({"case_id": cid, "category": "?", "ward": None, "state": "closed",
                      "color": "green", "sla_hours": None, "hours_elapsed": None,
                      "hours_remaining": 0, "escalated_to": None, "breach_mode": None,
                      "evidence_hash": evid.get(cid), "from_sabha": None})

    # ---- owed checklist (commitments) ----
    commitments = []
    skip_ids = {s["id"] for s in sk}
    for s in sk:
        commitments.append({"id": s["id"], "owner": None, "task": None, "due": None,
                            "state": "needs_date", "color": "amber",
                            "raw_deadline": s.get("raw"), "reason": s.get("reason"),
                            "hours_overdue": None, "escalated_to": None,
                            "breach_mode": None, "from_sabha": None})
    for ckey, c in sorted(cm.items()):
        due_ep = c["due_epoch"]
        if ckey in fm:
            state, color = "fulfilled", "green"
        elif ckey in bm:
            state, color = "breached", _color_for_breach(bmeta.get(ckey))
        elif now > due_ep:
            state, color = "overdue_unprocessed", "red"   # daemon didn't run; flag honestly
        elif (due_ep - now) <= 0.2 * max(1, (due_ep - c.get("created_epoch", due_ep - 86400))):
            state, color = "near_due", "amber"
        else:
            state, color = "in_time", "slate"
        mh = ckey.split("-")[1] if "-" in ckey else None
        commitments.append({"id": ckey, "owner": c.get("owner"), "task": c.get("task"),
                            "due": c.get("due_date"), "state": state, "color": color,
                            "hours_overdue": (bmeta.get(ckey) or {}).get("hours_overdue"),
                            "escalated_to": (bmeta.get(ckey) or {}).get("escalated_to"),
                            "breach_mode": (bmeta.get(ckey) or {}).get("mode"),
                            "from_sabha": ("%s %s" % mhmap[mh]) if (mh and mh in mhmap) else None})

    # ---- sabha archive ----
    all_ids = {r[0] for r in _db.all_rows()}
    pending_ids = {r[0] for r in _db.pending_acks()}
    sabhas = []
    for r in _db.all_rows():
        rid, gp, date, mhash, seq, signed = r[0], r[1], r[2], r[3], r[4], r[5]
        if not signed:
            state, color = "contested", "red"          # refused/unsigned record
        elif rid in pending_ids:
            state, color = "pending_ack", "amber"      # missing block-ack stays VISIBLE
        else:
            state, color = "acked", "green"
        sabhas.append({"row_id": rid, "gp": gp, "date": date, "signed": bool(signed),
                       "acked": rid not in pending_ids, "state": state, "color": color,
                       "minutes_hash": (mhash or "")[:12], "ledger_seq": seq,
                       "refuse_reason": None})
    # attach refuse_reason for unsigned rows from the chain
    for ev in events:
        if ev["event_type"] == "sabha_unsigned":
            p = ev.get("payload", {})
            for s in sabhas:
                if not s["signed"] and s["minutes_hash"] == (p.get("minutes_hash") or "")[:12]:
                    s["refuse_reason"] = p.get("reason")

    ok, bad, why = _chain.verify_chain(_chain.load_or_create_keys()[1]) if False else (True, None, "see header")
    # verify without regenerating keys: load pub from disk via event_bus path
    from core import event_bus as _eb
    if not _eb.is_ready():
        _eb.init()
    ok, bad, why = _eb.verify()

    # ---- petitions / Haq Receipts lane (Pillar 1) ----
    op, rs, rj, br, ab = _clock._load_petitions(events)
    petitions = []
    for pid, info in sorted(op.items()):
        if pid in br:
            state, color = "breached", _color_for_breach(bmeta.get(pid))
        elif (now - info["ts"]) / 3600.0 >= 0.8 * _clock.PETITION_CLOCKS["default"]:
            state, color = "near_breach", "amber"
        else:
            state, color = "in_sla", "slate"
        petitions.append({"case_id": pid, "receipt_id": info.get("receipt_id"),
                          "schemes": info.get("schemes"), "confidence": info.get("confidence"),
                          "state": state, "color": color,
                          "sla_hours": _clock.PETITION_CLOCKS["default"],
                          "hours_elapsed": round((now - info["ts"]) / 3600.0, 1),
                          "escalated_to": (bmeta.get(pid) or {}).get("escalated_to"),
                          "breach_mode": (bmeta.get(pid) or {}).get("mode")})
    for pid in sorted(rs - set(op.keys())):
        petitions.append({"case_id": pid, "receipt_id": None, "schemes": [], "confidence": None,
                          "state": "resolved", "color": "green", "sla_hours": None,
                          "hours_elapsed": None, "escalated_to": None, "breach_mode": None})
    for pid in sorted(rj - set(op.keys())):
        petitions.append({"case_id": pid, "receipt_id": None, "schemes": [], "confidence": None,
                          "state": "closed_rejected", "color": "slate", "sla_hours": None,
                          "hours_elapsed": None, "escalated_to": None, "breach_mode": None})
    for a in ab:
        petitions.append({"case_id": a["case_id"], "receipt_id": None, "schemes": [],
                          "confidence": a.get("confidence"), "state": "abstained_human",
                          "color": "amber", "sla_hours": None, "hours_elapsed": None,
                          "escalated_to": None, "breach_mode": None, "reason": a.get("reason")})

    counts = {"red": 0, "amber": 0, "green": 0, "slate": 0}
    for grp in (civic, commitments, sabhas, petitions):
        for it in grp:
            counts[it["color"]] = counts.get(it["color"], 0) + 1

    return {
        "generated_at": _iso(now),
        "integrity": {"chain_ok": ok, "first_bad_seq": bad, "verify_reason": why,
                      "chain_len": len(events), "pii_guard": "active",
                      "sla_mode_default": os.environ.get("HAQ_SLA_MODE", "escalate")},
        "legend": {
            "red": "breach (escalate) / contested Sabha — act + pushed upward",
            "amber": "breach (soft) / pending SDM ack / deadline needs a human date / near-breach — watch",
            "green": "closed civic / fulfilled commitment / acked Sabha — done",
            "slate": "open civic / owed commitment within SLA — counting down",
        },
        "counts": counts,
        "civic": civic, "commitments": commitments, "sabhas": sabhas, "petitions": petitions,
    }
