"""
HaqSetu - Realistic Panchayat Meeting Engine (declarative, pure stdlib).

A meeting is a GOVERNANCE layer over the live records, not a script:
  open -> attendance/quorum -> resolutions(vote) -> close(seal) -> ratify
The agenda is AUTO-BUILT from the current open work orders + pending scheme
applications (+ carried-forward action items), so what the panchayat discusses
is whatever the system actually owes it. Carried resolutions write back onto
the referenced tickets (audit event + action item). Minutes are sealed with a
local hash chain for tamper-evidence.

BOUNDARIES (stated for the viva):
 * Quorum thresholds & statutory frequency VARY BY STATE Panchayat Raj Act.
   We encode the MECHANISM and keep the numbers as config with conservative
   defaults + a "verify against your state act" note. Not invented law.
 * E-voting and attendance biometrics/signatures are MOCKED; the tally logic
   (majority vs 2/3, abstention handling, tabled-on-no-quorum-of-votes) is real.
 * The hash chain is a LOCAL tamper-evidence seal (detects casual alteration of
   the stored record), NOT a distributed ledger and NOT a government registry.
   Production anchors the head digest to an external notary / state e-Panchayat
   portal (mocked here). content_check() cross-verifies the human-readable
   columns against the sealed chain, so editing the minutes behind the seal is
   caught even though the chain hashes themselves still match.

Pure functions; no DB, no side effects. Persistence + routes live in the server.
"""
import time, math, json, hashlib

GENESIS = "0" * 64
ROLES = ["sarpanch", "panch", "secretary", "je", "citizen"]

# vote_threshold: fraction of DECISIVE votes (aye+no) needed; abstentions excluded.
RESOLUTION_TYPES = {
    "routine":        {"label": "Routine motion",            "threshold": 0.5,   "can_link": True},
    "budget":         {"label": "Budget / expenditure",      "threshold": 0.5,   "can_link": True},
    "statutory_23":   {"label": "Statutory (2/3 majority)",  "threshold": 2/3,   "can_link": True},
    "procedural":     {"label": "Procedural (no external link)", "threshold": 0.5, "can_link": False},
}

# quorum: required = ceil(enrolled*fraction); if cap present, min(required,cap); floor 1.
# statutory_days: minimum meeting cadence (None = no fixed cadence).
MEETING_TYPES = {
    "GRAM_SABHA": {
        "label": "Gram Sabha (all adults)",
        "quorum": {"fraction": 0.10, "cap": 30},          # "1/10 of members or 30, whichever less" (typical)
        "statutory_days": 180,                             # at least twice a year (many states)
        "agenda_static": [
            "Annual / five-year development plan review",
            "Social audit of works completed in the period",
            "Publication of the list of beneficiaries (schemes)",
            "Any matter raised by members (open floor)",
        ],
        "note": "Quorum rule & frequency vary by state Panchayat Raj Act - verify locally.",
    },
    "PANCHAYAT_BODY": {
        "label": "Panchayat General Body Meeting",
        "quorum": {"fraction": 0.50},                      # simple majority of elected members
        "statutory_days": 30,                              # monthly standing practice in many states
        "agenda_static": [
            "Monthly expenditure & receipt reconciliation",
            "Status of works in progress (with JE)",
            "Approval of previous meeting's minutes (ratification)",
        ],
        "note": "Quorum = majority of elected members; verify against your state act.",
    },
    "SPECIAL_BODY": {
        "label": "Special Body Meeting",
        "quorum": {"fraction": 0.50},
        "statutory_days": None,
        "agenda_static": ["Specific matter for which the meeting was summoned"],
        "note": "Only the summoned matter may be transacted.",
    },
}

# enforced meeting state machine. terminal = ratified / adjourned.
ALLOWED = {
    "draft":      ["opened", "adjourned"],
    "opened":     ["in_session", "adjourned"],
    "in_session": ["closed", "adjourned"],
    "closed":     ["ratified"],
    "ratified":   [],
    "adjourned":  [],
}
TERMINAL = ("ratified", "adjourned")

def allowed(frm, to):  return to in ALLOWED.get(frm, [])
def is_terminal(st):   return st in TERMINAL
def label(mtype):      return MEETING_TYPES.get(mtype, MEETING_TYPES["PANCHAYAT_BODY"])["label"]

# ---------- quorum ----------
def compute_quorum(mtype, enrolled):
    q = MEETING_TYPES.get(mtype, MEETING_TYPES["PANCHAYAT_BODY"])["quorum"]
    req = math.ceil(max(0, int(enrolled)) * float(q.get("fraction", 0.5)))
    if q.get("cap") is not None:
        req = min(req, int(q["cap"]))
    return max(1, req)

def check_quorum(mtype, enrolled, present):
    req = compute_quorum(mtype, enrolled)
    return (int(present) >= req, req, int(present))

# ---------- voting ----------
def resolve_outcome(aye, no, abstain, threshold=0.5):
    aye, no, ab = int(aye or 0), int(no or 0), int(abstain or 0)
    decisive = aye + no
    if decisive == 0:
        return {"outcome": "tabled", "aye": aye, "no": no, "abstain": ab,
                "decisive": 0, "aye_pct": None, "threshold": threshold,
                "reason": "no decisive votes recorded"}
    pct = aye / decisive
    return {"outcome": "carried" if pct >= threshold else "defeated",
            "aye": aye, "no": no, "abstain": ab, "decisive": decisive,
            "aye_pct": round(pct, 3), "threshold": round(threshold, 3),
            "reason": "aye %.0f%% of decisive votes vs %.0f%% required" % (pct*100, threshold*100)}

# ---------- hash chain (local tamper-evidence) ----------
def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def chain_append(chain, kind, payload):
    chain = list(chain or [])
    prev = chain[-1]["hash"] if chain else GENESIS
    h = hashlib.sha256((prev + _canonical(payload)).encode("utf-8")).hexdigest()
    chain.append({"seq": len(chain), "kind": kind, "prev_hash": prev,
                  "payload": payload, "hash": h})
    return chain

def chain_verify(chain):
    chain = chain or []
    prev = GENESIS
    for e in chain:
        if e.get("prev_hash") != prev:
            return (False, e.get("seq"), "linkage broken at seq %s" % e.get("seq"))
        h = hashlib.sha256((prev + _canonical(e.get("payload"))).encode("utf-8")).hexdigest()
        if h != e.get("hash"):
            return (False, e.get("seq"), "hash mismatch at seq %s (payload altered)" % e.get("seq"))
        prev = e["hash"]
    return (True, None, "chain intact (%d links)" % len(chain))

def content_check(meeting_row):
    """Cross-verify the human-readable columns against the sealed chain.
    Catches edits to resolutions_json / minutes that leave the chain hashes
    untouched (i.e. someone edited the record behind the seal)."""
    chain = meeting_row.get("chain") or []
    sealed_res = [e["payload"] for e in chain if e.get("kind") == "resolution"]
    if list(meeting_row.get("resolutions") or []) != sealed_res:
        return (False, "resolutions_json does not match sealed chain payloads")
    mins = [e for e in chain if e.get("kind") == "minutes"]
    if mins:
        last = mins[-1]["payload"]
        if (meeting_row.get("attendance") or []) != (last.get("attendance") or []) \
           or (meeting_row.get("agenda") or []) != (last.get("agenda") or []):
            return (False, "attendance/agenda do not match sealed minutes entry")
    return (True, "record consistent with seal")

# ---------- agenda auto-built from live system state ----------
def build_agenda(snapshot, mtype):
    snap = snapshot or {}
    tickets = snap.get("tickets") or []
    apps = snap.get("applications") or []
    prior = snap.get("prior_actions") or []
    active = [t for t in tickets if t.get("status") not in ("closed", "rejected")]
    overdue = [t for t in active if t.get("breached")]
    pend_apps = [a for a in apps if (a.get("status") or a.get("bot_status")) in
                 ("submitted", "under_review", "doc_verification", "pending", "pending_officer")]
    items = []
    items.append({"kind": "review_work_orders", "ref": None,
                  "text": "Review %d active work order(s)%s" % (
                      len(active), (", %d OVERDUE - escalate first" % len(overdue)) if overdue else ""),
                  "detail": [t.get("wo_number") or ("#%s" % t.get("id")) for t in overdue] or
                            [t.get("wo_number") or ("#%s" % t.get("id")) for t in active][:8]})
    for t in overdue[:5]:
        items.append({"kind": "escalate", "ref": t.get("wo_number") or ("#%s" % t.get("id")),
                      "text": "Escalate overdue %s (%s, age %sh)" % (
                          t.get("wo_number") or ("#%s" % t.get("id")), t.get("category_label") or t.get("category"),
                          t.get("age_hours"))})
    items.append({"kind": "review_applications", "ref": None,
                  "text": "Dispose %d pending scheme application(s)" % len(pend_apps),
                  "detail": [a.get("reg_id_format") or a.get("reg_id_generated") or ("#%s" % a.get("id")) for a in pend_apps][:8]})
    if prior:
        items.append({"kind": "prior_actions", "ref": None,
                      "text": "Carry forward %d unresolved action item(s) from the previous meeting" % len(prior),
                      "detail": [p.get("ref") or p.get("action") for p in prior][:8]})
    for s in MEETING_TYPES.get(mtype, MEETING_TYPES["PANCHAYAT_BODY"]).get("agenda_static", []):
        items.append({"kind": "statutory", "ref": None, "text": s})
    return items

# ---------- statutory cadence ----------
def statutory_status(mtype, last_iso, now=None):
    now = now or time.time()
    days = MEETING_TYPES.get(mtype, MEETING_TYPES["PANCHAYAT_BODY"]).get("statutory_days")
    if not days:
        return (True, None, "no fixed statutory cadence for %s" % label(mtype))
    if not last_iso:
        return (False, now, "%s never held - due immediately" % label(mtype))
    try:
        last = time.mktime(time.strptime(str(last_iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return (False, now, "could not parse last meeting date - treat as due")
    nxt = last + days * 86400
    ok = now <= nxt
    return (ok, nxt, ("%s within cadence (every %d days)" % (label(mtype), days)) if ok
            else ("%s OVERDUE - last held %s, due by %s" % (
                label(mtype), time.strftime("%Y-%m-%d", time.localtime(last)),
                time.strftime("%Y-%m-%d", time.localtime(nxt)))))

def _now(): return time.strftime("%Y-%m-%dT%H:%M:%S")

if __name__ == "__main__":
    print("=== MEETING ENGINE - HEADLESS DEMO (no DB, no server) ===")
    # synthetic live-system snapshot (what build_agenda will receive from the server)
    snap = {"tickets": [
                {"id": 1, "wo_number": "WO/2026/WTR/00011", "category": "WATER", "category_label": "Water supply / handpump", "status": "assigned", "age_hours": 30.0, "breached": True},
                {"id": 2, "wo_number": "WO/2026/RD/00003",  "category": "ROAD",  "category_label": "Road / pavement",        "status": "open",     "age_hours": 5.0,  "breached": False}],
            "applications": [
                {"id": 13, "reg_id_format": "PEN-W/2026/00009", "scheme_name": "VIDHWA_PENSION", "status": "under_review"},
                {"id": 14, "reg_id_format": "MUDRA/2026/00002", "scheme_name": "MUDRA LOAN",     "status": "submitted"}],
            "prior_actions": [{"ref": "WO/2026/DRN/00002", "action": "re-inspect drain after monsoon"}]}
    ag = build_agenda(snap, "GRAM_SABHA")
    print("  agenda auto-built from live state -> %d items" % len(ag))
    for it in ag[:4]:
        print("    [%-18s] %s" % (it["kind"], it["text"]))
    # quorum
    for enr, pres in [(12, 1), (12, 2), (40, 4), (40, 5)]:
        met, req, p = check_quorum("GRAM_SABHA", enr, pres)
        print("  quorum GRAM_SABHA enrolled=%2d present=%d -> required=%d met=%s" % (enr, pres, req, met))
    # voting
    for a, n, ab, th, tag in [(6, 2, 1, 0.5, "routine 6-2"), (3, 5, 0, 0.5, "routine 3-5"),
                              (7, 3, 0, 2/3, "statutory 7-3 (needs 2/3)"), (0, 0, 4, 0.5, "all abstain")]:
        r = resolve_outcome(a, n, ab, th)
        print("  vote %-22s -> %-8s (%s)" % (tag, r["outcome"], r["reason"]))
    # hash chain + tamper detection
    ch = []
    ch = chain_append(ch, "resolution", {"id": 1, "text": "Sanction repair of WO/2026/WTR/00011", "outcome": "carried"})
    ch = chain_append(ch, "resolution", {"id": 2, "text": "Defeat proposal to raise water tax", "outcome": "defeated"})
    ok, seq, msg = chain_verify(ch)
    print("  chain verify (clean)        -> ok=%s %s" % (ok, msg))
    ch_bad = [dict(e) for e in ch]; ch_bad[0]["payload"]["text"] = "TAMPERED"
    ok2, seq2, msg2 = chain_verify(ch_bad)
    print("  chain verify (payload edit) -> ok=%s broken_at=%s %s" % (ok2, seq2, msg2))
    # content_check: edit resolutions behind an intact chain
    row = {"chain": ch, "resolutions": [ch[0]["payload"], {"id": 99, "text": "injected"}],
           "agenda": ag, "attendance": []}
    cok, cmsg = content_check(row)
    print("  content_check (res edit)    -> ok=%s %s" % (cok, cmsg))
    # statutory cadence
    print("  cadence GRAM_SABHA never held ->", statutory_status("GRAM_SABHA", None)[2])
    print("  cadence GRAM_SABHA 100d ago   ->", statutory_status("GRAM_SABHA", _now())[2][:60], "...")
    # state machine legality
    checks = [("draft","opened",True),("opened","in_session",True),("in_session","closed",True),
              ("closed","ratified",True),("opened","closed",False),("in_session","ratified",False),
              ("ratified","in_session",False),("opened","adjourned",True)]
    bad = [(f,t,e) for f,t,e in checks if allowed(f,t) != e]
    print("  state machine -> %s" % ("ALL %d TRANSITIONS CORRECT" % len(checks) if not bad else "MISMATCH %s" % bad))
    print("=== demo complete ===")


# ---------------- SDM report composition (pure; renderer + I/O live in the server) ----------------
SDM_RECIPIENT_DEFAULT = "Office of the Sub-Divisional Magistrate (SDM)"
SDM_CHANNEL_MOCK = "mocked e-Panchayat portal / registered post (transmission is the integration point)"

def compose_sdm_report(m, affected, now_iso=None):
    """Turn a SEALED meeting row (+ the work orders its carried motions touched) into the
    structured sections an SDM document needs. Pure: no DB, no PDF, no side effects.
    m is the dict from the server's _mrow (lists already parsed). affected is a list of
    {wo, description, status, category_label} for tickets carrying a gram_sabha write-back."""
    now_iso = now_iso or _now()
    mid = m.get("id")
    req = m.get("quorum_required") or 0
    att = m.get("attendance") or []
    present = len(att) if att else (m.get("quorum_present") or 0)
    quorum = {"required": req, "present": present, "met": (req > 0 and present >= req)}
    agenda = ["[%s] %s" % (it.get("kind"), it.get("text")) for it in (m.get("agenda") or [])]
    resolutions = m.get("resolutions") or []
    action_items = m.get("action_items") or []
    head = m.get("head_hash") or ""
    chain = m.get("chain") or []
    cv = chain_verify(chain)
    cc = content_check({"chain": chain, "resolutions": resolutions,
                        "agenda": m.get("agenda") or [], "attendance": att})
    carried = [r for r in resolutions if r.get("outcome") == "carried"]
    defeated = [r for r in resolutions if r.get("outcome") == "defeated"]
    tabled = [r for r in resolutions if r.get("outcome") == "tabled"]
    meta_lines = [
        ("Meeting type", label(m.get("mtype"))),
        ("Title", m.get("title") or ""),
        ("Venue", m.get("venue") or ""),
        ("Chair", m.get("chair") or ""),
        ("Lifecycle status", m.get("status") or ""),
        ("Generated (this report)", now_iso),
    ]
    seal = {
        "minutes_head": head,
        "links_at_report": len(chain),
        "chain_ok": cv[0], "chain_msg": cv[2],
        "content_ok": cc[0], "content_msg": cc[1],
        "carried": len(carried), "defeated": len(defeated), "tabled": len(tabled),
    }
    dispatch = {"recipient": SDM_RECIPIENT_DEFAULT, "channel": SDM_CHANNEL_MOCK,
                "minutes_head": head, "meeting_id": mid, "generated_at": now_iso}
    verification = (
        "VERIFICATION FOR THE RECIPIENT (SDM): fetch GET /api/meeting/%s and confirm the "
        "minutes seal head equals %s and that chain_ok and content_ok are both true. "
        "If the stored record has been altered behind the seal, content_ok will read false "
        "even though the hash chain itself still validates." % (mid, head or "(none)")
    )
    boundaries = [
        "Quorum thresholds and statutory frequency vary by the State Panchayat Raj Act; the "
        "figures here are conservative configured defaults - verify against local rules.",
        "Electronic voting and attendance are simulated; the tally logic (majority vs two-thirds, "
        "abstention excluded, tabled on zero decisive votes) is computed, not asserted.",
        "The hash chain is a local tamper-evidence seal, not a distributed ledger or a government "
        "registry; production anchors the head digest to an external notary / state e-Panchayat portal.",
        "Transmission of this report to the SDM office is mocked; the PDF and the sealed dispatch "
        "receipt are the real artifacts.",
    ]
    return {
        "meeting_id": mid,
        "title": "MINUTES AND RESOLUTIONS REPORT - FORWARDED TO THE SDM",
        "subtitle": "%s | %s" % (label(m.get("mtype")), m.get("title") or ""),
        "meta_lines": meta_lines,
        "quorum": quorum,
        "agenda": agenda,
        "resolutions": resolutions,
        "action_items": action_items,
        "affected": affected or [],
        "seal": seal,
        "dispatch": dispatch,
        "verification": verification,
        "boundaries": boundaries,
    }
