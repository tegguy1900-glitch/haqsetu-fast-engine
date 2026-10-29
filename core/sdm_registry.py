"""
HaqSetu - SDM Dispatch Registry (declarative, pure stdlib).

The transmission boundary. When a sealed meeting report is generated, a dispatch
row is written to the SDM inbox AND a content fingerprint of the resolutions is
sealed at send-time. verify_dispatch() re-derives that fingerprint from the
CURRENT meeting record and compares it to what was sent, so post-dispatch
editing behind the seal is caught at the recipient side - the transmission-
boundary extension of meeting_registry.content_check.

States: received -> {queried, acknowledged, escalated}; queried -> {answered,
escalated} (answered set only by a panchayat reply, never by an SDM action);
answered -> {acknowledged, escalated}; acknowledged/escalated terminal. A query
is the SDM challenging the record; a reply is the panchayat answering it; the
thread is two dispatch rows (original + reply via reply_to), the meeting itself
is never reopened.

BOUNDARIES: single demo role (production = officer SSO); wide-area panchayat->
district transport is the mocked integration point, the inbox store + seal are
real; ack SLA is a configurable default, not statute.
"""
import time, json, hashlib
import core.meeting_registry as _mr

ACK_DAYS = 7  # configurable default; verify against local rules
TERMINAL = ("acknowledged", "escalated")
ALLOWED = {
    "received":   ["queried", "acknowledged", "escalated"],
    "queried":    ["answered", "escalated"],
    "answered":   ["acknowledged", "escalated"],
    "acknowledged": [],
    "escalated":  [],
}
def allowed(frm, to): return to in ALLOWED.get(frm, [])
def is_terminal(st):  return st in TERMINAL

def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def content_fp(resolutions):
    return hashlib.sha256(_canonical(resolutions or []).encode("utf-8")).hexdigest()

def ack_deadline(received_at, now=None):
    return (now or received_at) + ACK_DAYS * 86400
def breached(disp, now=None):
    now = now or time.time()
    if is_terminal(disp.get("status")): return False
    dl = disp.get("ack_deadline") or 0
    return bool(dl) and now > dl

def verify_dispatch(disp, meeting):
    """Re-derive the seal from the CURRENT meeting and compare to what was sent.
    Returns (ok, reasons[]). Detects: resolutions edited after dispatch (fp),
    minutes head changed after dispatch, broken chain, content_check failure."""
    reasons = []
    cur_fp = content_fp(meeting.get("resolutions") or [])
    dfp = disp.get("dispatched_content_fp")
    if dfp and cur_fp != dfp:
        reasons.append("resolutions altered after dispatch (content fingerprint mismatch)")
    dh = disp.get("dispatched_head"); mh = meeting.get("head_hash")
    if dh and mh and dh != mh:
        reasons.append("minutes seal head changed after dispatch")
    cv = _mr.chain_verify(meeting.get("chain") or [])
    if not cv[0]:
        reasons.append("hash chain broken: " + str(cv[2]))
    cc = _mr.content_check(meeting)
    if not cc[0]:
        reasons.append("content_check failed: " + str(cc[1]))
    return (len(reasons) == 0, reasons)

def inbox_sort_key(disp, now=None):
    now = now or time.time()
    term = is_terminal(disp.get("status"))
    br = breached(disp, now)
    open_rank = 0 if disp.get("status") in ("received", "queried", "answered") else 1
    return (0 if (br and not term) else 1, open_rank, -(disp.get("received_at") or 0))

def compose_sdm_summary(meeting, disp, verify_ok, verify_reasons, thread):
    res = meeting.get("resolutions") or []
    carried = [r for r in res if r.get("outcome") == "carried"]
    defeated = [r for r in res if r.get("outcome") == "defeated"]
    tabled = [r for r in res if r.get("outcome") == "tabled"]
    req = meeting.get("quorum_required") or 0
    att = meeting.get("attendance") or []
    present = len(att) if att else (meeting.get("quorum_present") or 0)
    return {
        "dispatch_id": disp.get("id"), "meeting_id": meeting.get("id"),
        "meeting_title": meeting.get("title"), "meeting_type": _mr.label(meeting.get("mtype")),
        "chair": meeting.get("chair"), "venue": meeting.get("venue"),
        "quorum": {"required": req, "present": present, "met": (req > 0 and present >= req)},
        "carried": len(carried), "defeated": len(defeated), "tabled": len(tabled),
        "resolutions": res, "agenda": meeting.get("agenda") or [],
        "minutes_text": meeting.get("minutes_text") or "",
        "report_path": disp.get("report_path"), "recipient": disp.get("recipient"),
        "status": disp.get("status"), "query_text": disp.get("query_text") or "",
        "response_text": disp.get("response_text") or "", "reply_to": disp.get("reply_to"),
        "dispatched_head": disp.get("dispatched_head"), "current_head": meeting.get("head_hash"),
        "dispatched_fp": disp.get("dispatched_content_fp"),
        "seal_ok": verify_ok, "seal_reasons": verify_reasons,
        "breached": breached(disp), "age_hours": round((time.time() - (disp.get("received_at") or time.time())) / 3600.0, 1),
        "audit": disp.get("audit") or [], "thread": thread or [],
        "boundaries": [
            "SDM view is a demo role; production gates it behind officer SSO.",
            "Wide-area panchayat->district transport is the mocked integration point; the inbox store and seal are real.",
            "Acknowledge SLA (%d days) is a configurable default, not statute." % ACK_DAYS,
        ],
    }

if __name__ == "__main__":
    print("=== SDM DISPATCH REGISTRY - HEADLESS DEMO (no DB) ===")
    fe = content_fp([])
    f1 = content_fp([{"id": 1, "text": "repair WO/2026/WTR/00003", "outcome": "carried"}])
    print("  content_fp stable&distinct -> %s" % (fe != f1 and content_fp([{"id":1,"text":"repair WO/2026/WTR/00003","outcome":"carried"}]) == f1))
    disp = {"dispatched_content_fp": fe, "dispatched_head": "HH", "status": "received", "received_at": time.time()-3600, "ack_deadline": ack_deadline(time.time()-3600)}
    m_clean = {"id":1,"resolutions":[],"head_hash":"HH","chain":[],"agenda":[],"attendance":[],"title":"X","mtype":"GRAM_SABHA"}
    ok, rs = verify_dispatch(disp, m_clean); print("  verify clean          -> ok=%s reasons=%s" % (ok, rs))
    m_tam = dict(m_clean); m_tam["resolutions"] = [{"id":9,"text":"INJECTED","outcome":"carried"}]
    ok2, rs2 = verify_dispatch(disp, m_tam); print("  verify res-edit       -> ok=%s reasons=%s" % (ok2, [r[:40] for r in rs2]))
    disp_hd = dict(disp); disp_hd["dispatched_head"] = "AA"
    ok3, rs3 = verify_dispatch(disp_hd, m_clean); print("  verify head-change      -> ok=%s reasons=%s" % (ok3, [r[:40] for r in rs3]))
    sm = [("received","acknowledged",True),("received","queried",True),("received","answered",False),
          ("queried","answered",True),("queried","acknowledged",False),("answered","acknowledged",True),
          ("acknowledged","queried",False),("escalated","received",False)]
    bad = [(f,t,e) for f,t,e in sm if allowed(f,t)!=e]
    print("  state machine         -> %s" % ("ALL %d CORRECT"%len(sm) if not bad else "MISMATCH %s"%bad))
    now = time.time()
    inbox = [
        {"id":1,"status":"received","received_at":now-100,"ack_deadline":now-10},      # breached-open
        {"id":2,"status":"received","received_at":now-50,"ack_deadline":now+1000},     # open
        {"id":3,"status":"acknowledged","received_at":now-200,"ack_deadline":now+100}, # terminal
    ]
    inbox.sort(key=lambda d: inbox_sort_key(d, now))
    print("  inbox sort (overdue-first) -> %s" % ([d["id"] for d in inbox], ))
    summ = compose_sdm_summary(m_tam, disp, ok2, rs2, [])
    print("  summary keys         -> %s" % ("seal_ok" in summ and "carried" in summ and summ["seal_ok"]==False))
    print("=== demo complete ===")
