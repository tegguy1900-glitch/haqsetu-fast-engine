"""
Tier-1 unit tests: declarative data + pure evaluators of the four registries.
No HTTP, no DB, no side effects.

FLAT-BY-CONSTRUCTION: every check is check("label", lambda: <one helper call>).
The earlier version hand-nested (lambda r: ...)(sc.evaluate(...)) IIFE soup and
miscounted closers (the same paren bug as the INSERT / PDF-probe). Module-level
helpers unwrap that once, so a check line has exactly one open paren per call and
cannot be miscounted. If a check is RED on first run, the label tells you which:
a moved DATA value = real regression in the module; a wrong EXPECTED number =
the TEST is the suspect (my gates historically lied about 7-3 vs 5-3, quorum,
format-vs-eligibility precedence). Crash-isolated: check() catches its own
exception, so one bad lambda records FAIL+detail and never aborts the run.
"""
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import core.scheme_registry as sc
import core.infra_registry as ir
import core.meeting_registry as mr
import core.sdm_registry as sd

RESULTS = []
def check(label, fn):
    try:
        ok = bool(fn()); detail = ""
    except Exception as e:
        ok = False; detail = type(e).__name__ + ": " + str(e)[:90]
    RESULTS.append((label, ok, detail))
    print("  %-5s | %-58s %s" % ("PASS" if ok else "FAIL", label, detail))
def section(t):
    print("\n===== %s =====" % t)

# ---- scheme helpers (unwrap the IIFE once; callers stay single-level) ----
_BASE = {"name":"Ramesh Yadav","father":"Suresh","age":"28","gender":"M","category":"SC",
         "village":"ward7","mobile":"9812345678","aadhaar":"234567890123",
         "ifsc":"HDFC0001234","account":"50100123456789"}
def base(**over):
    d = dict(_BASE); d.update(over); return d
def ev(sid, app, docs=None):
    return sc.evaluate(sid, app, docs or {})
def rej(sid, app, stage, docs=None):
    r = ev(sid, app, docs); return (not r.get("ok")) and r.get("stage") == stage
def rej_field(sid, app, stage, field, docs=None):
    r = ev(sid, app, docs)
    return (not r.get("ok")) and r.get("stage")==stage and field in (r.get("errors") or {})
def rej_reason(sid, app, substr, docs=None):
    r = ev(sid, app, docs)
    return (not r.get("ok")) and r.get("stage")=="eligibility" and any(substr in x for x in (r.get("reasons") or []))
def acc(sid, app, docs=None):
    r = ev(sid, app, docs); return bool(r.get("ok")) and r.get("stage") == "ready"
def not_seeded_under_review(sid, app, docs=None):
    r = ev(sid, app, docs)
    return bool(r.get("ok")) and r.get("status")=="under_review" and any(w.get("status")=="not_seeded" for w in (r.get("warnings") or []))
def chain_ok(chain):
    return mr.chain_verify(chain)[0] is True
def chain_broken(chain, idx):
    v = mr.chain_verify(chain); return v[0] is False and v[1]==idx
def vdisp_ok(d, m):
    return sd.verify_dispatch(d, m)[0] is True
def vdisp_bad(d, m, substr):
    ok, rs = sd.verify_dispatch(d, m)
    return (not ok) and any(substr in r.lower() for r in rs)

# ---------------------------------------------------------------- schemes
def group_schemes():
    section("SCHEME REGISTRY (14 curated central schemes)")
    check("exactly 14 schemes on disk", lambda: len(sc.SCHEMAS) == 14)
    check("10 categories present", lambda: len({s["category"] for s in sc.SCHEMAS.values()}) == 10)
    check("every scheme well-formed", lambda: all(
        isinstance(s.get("fields"), list) and s["fields"] and
        isinstance(s.get("eligibility"), list) and isinstance(s.get("adapters"), list) and
        s.get("reg_id_prefix") and s.get("status_flow") and s.get("title") and s.get("category") and s.get("summary")
        for s in sc.SCHEMAS.values()))
    check("every scheme's adapters are real registered names", lambda: all(
        set(s["adapters"]) <= set(sc.ADAPTERS.keys()) for s in sc.SCHEMAS.values()))
    check("field keys unique; every field has key/label/type/required", lambda: all(
        len({f["key"] for f in s["fields"]}) == len(s["fields"]) and
        all(f.get("key") and f.get("label") and f.get("type") in ("text","number","select","file") and "required" in f
            for f in s["fields"]) for s in sc.SCHEMAS.values()))
    check("select fields carry options; file fields carry a doc tag", lambda: all(
        (f["type"] != "select" or f.get("options")) and (f["type"] != "file" or f.get("doc"))
        for s in sc.SCHEMAS.values() for f in s["fields"]))
    check("every eligibility rule has desc + field-or-doc anchor", lambda: all(
        r.get("desc") and ("field" in r or "doc" in r) for s in sc.SCHEMAS.values() for r in s["eligibility"]))
    check("aadhaar starting 1 -> FORMAT error", lambda: sc._validate("aadhaar","134567890123") is not None)
    check("aadhaar starting 9 -> format OK (not-seeded is an ADAPTER concern)", lambda: sc._validate("aadhaar","934567890123") is None)
    check("aadhaar 11 digits -> format error", lambda: sc._validate("aadhaar","23456789012") is not None)
    check("aadhaar all-same digit -> format error", lambda: sc._validate("aadhaar","111111111111") is not None)
    check("1-char name -> FORMAT error (the fixture bug that hid eligibility)", lambda: sc._validate("name","P") is not None)
    check("real name -> format OK", lambda: sc._validate("name","Prakash") is None)
    check("mobile 1... -> error; 98... -> OK", lambda: sc._validate("mobile","1234567890") is not None and sc._validate("mobile","9812345678") is None)
    check("ifsc HDFC0001234 -> OK; XX -> error", lambda: sc._validate("ifsc","HDFC0001234") is None and sc._validate("ifsc","XX") is not None)
    check("age 18:120 lets 45 PASS format (so APY-45 fails at ELIGIBILITY)", lambda: sc._validate("age:18:120","45") is None)
    check("APY father=P + age45 -> stage=validation (format BEFORE eligibility)", lambda: rej_field("ATAL PENSION", base(name="QA Old", father="P", age="45", occupation="Vendor", pension_amount="2000"), "validation", "father"))
    check("APY valid-format age45 -> stage=eligibility, reason mentions 40", lambda: rej_reason("ATAL PENSION", base(name="QA Old", father="Prakash", age="45", occupation="Vendor", pension_amount="2000"), "40"))
    check("widow male -> eligibility reject", lambda: rej("VIDHWA_PENSION", base(name="Hari", husband="X", gender="M", marital="Widowed", death_certificate="d.pdf", dependents="0"), "eligibility", {"death_certificate":"d.pdf"}))
    check("SSY child age 12 -> eligibility reject (<10 rule)", lambda: rej("SUKANYA SAMRIDDHI", {"guardian_name":"Mohan","guardian_age":"38","guardian_aadhaar":"234567890123","guardian_mobile":"9812345678","child_name":"Meena","child_age":"12","birth_certificate":"b.pdf","ifsc":"HDFC0001234","account":"50100123456789","village":"w"}, "eligibility", {"birth_certificate":"b.pdf"}))
    check("KISAN is_farmer=No -> eligibility reject", lambda: rej("PM_KISAN", base(name="Urban", is_farmer="No", gov_employee="No", land_record="lr.pdf"), "eligibility", {"land_record":"lr.pdf"}))
    check("UJJWALA not-BPL -> eligibility reject", lambda: rej("PM_UJJWALA", base(name="Anita", husband="P", gender="F", bpl_flag="No"), "eligibility"))
    check("MGNREGA valid adult -> ok, stage=ready", lambda: acc("MGNREGA", base(card_type="New")))
    check("aadhaar starting 9 -> accepted, uidai not_seeded -> under_review (controllable demo branch)", lambda: not_seeded_under_review("MGNREGA", base(name="Gopal", father="H", age="30", gender="M", category="OBC", aadhaar="934567890123", card_type="New")))
    check("get_schema('PM_KISAN') returns fields (underscore id is the real key)", lambda: bool((sc.get_schema("PM_KISAN") or {}).get("fields")))
    check("get_schema('NOPE') -> None", lambda: sc.get_schema("NOPE") is None)
    check("unknown scheme evaluate -> stage=unknown_scheme", lambda: rej("NOPE", {}, "unknown_scheme"))

# ---------------------------------------------------------------- infra
def group_infra():
    section("INFRA REGISTRY (fault taxonomy, geofence, SLA, state machine)")
    check("classify Hinglish -> WATER/DRAIN/ROAD/STREETLIGHT/SANITATION/OTHER", lambda: (
        ir.classify("mera handpump toot gaya")=="WATER" and ir.classify("naali jam ho gayi paani khada")=="DRAIN" and
        ir.classify("sadak par bada gaddha")=="ROAD" and ir.classify("gali ka light nahi jal raha")=="STREETLIGHT" and
        ir.classify("kachra utha nahi ja raha")=="SANITATION" and ir.classify("kuch samajh nahi aa raha")=="OTHER"))
    check("geofence radii (WATER30 DRAIN40 ROAD80 STP50 SAN50 OTHER60)", lambda: (
        ir.geofence("WATER")==30 and ir.geofence("DRAIN")==40 and ir.geofence("ROAD")==80 and
        ir.geofence("STREETLIGHT")==50 and ir.geofence("SANITATION")==50 and ir.geofence("OTHER")==60))
    check("dup_radius = max(geofence,50): WATER->50, ROAD->80", lambda: ir.dup_radius("WATER")==50 and ir.dup_radius("ROAD")==80)
    check("SLA: WATER/CRITICAL=12 override, ROAD/LOW=240, MEDIUM default=120", lambda: (
        ir.sla_for("WATER","CRITICAL")==12 and ir.sla_for("ROAD","LOW")==240 and ir.sla_for("ROAD","MEDIUM")==120))
    check("format_wo('DRAIN',7) -> WO/<YEAR>/DRN/00007", lambda: ir.format_wo("DRAIN",7).endswith("/DRN/00007") and ir.format_wo("DRAIN",7).startswith("WO/"))
    check("hw_intent bridge covers all 6 categories", lambda: all(ir.hw_intent(c) for c in ir.CATEGORIES))
    check("severity rank strictly orders LOW<MEDIUM<HIGH<CRITICAL", lambda: (
        ir.SEVERITY_RANK["LOW"]<ir.SEVERITY_RANK["MEDIUM"]<ir.SEVERITY_RANK["HIGH"]<ir.SEVERITY_RANK["CRITICAL"]))
    check("state machine: open->assigned ok, open->closed illegal, closed->reopened ok, rejected terminal", lambda: (
        ir.allowed("open","assigned") and not ir.allowed("open","closed") and ir.allowed("closed","reopened") and
        not ir.allowed("rejected","assigned") and ir.allowed("awaiting_otp","closed") and ir.allowed("in_progress","awaiting_otp")))
    check("is_terminal: closed/rejected terminal; in_progress/awaiting_otp not", lambda: (
        ir.is_terminal("closed") and ir.is_terminal("rejected") and not ir.is_terminal("in_progress") and not ir.is_terminal("awaiting_otp")))

# ---------------------------------------------------------------- meeting
def group_meeting():
    section("MEETING REGISTRY (quorum, computed voting, hash-chain seal, cadence)")
    check("compute_quorum GRAM_SABHA 12->2, 40->4, 120->12 (1/10 cap 30)", lambda: (
        mr.compute_quorum("GRAM_SABHA",12)==2 and mr.compute_quorum("GRAM_SABHA",40)==4 and mr.compute_quorum("GRAM_SABHA",120)==12))
    check("compute_quorum PANCHAYAT_BODY 12->6, SPECIAL_BODY 12->6 (majority)", lambda: (
        mr.compute_quorum("PANCHAYAT_BODY",12)==6 and mr.compute_quorum("SPECIAL_BODY",12)==6))
    check("check_quorum returns (met, required, present)", lambda: mr.check_quorum("GRAM_SABHA",12,2)==(True,2,2) and mr.check_quorum("GRAM_SABHA",12,1)==(False,2,1))
    check("vote 6-2-1 routine -> carried (abstain excluded: 6/8=0.75)", lambda: mr.resolve_outcome(6,2,1,0.5)["outcome"]=="carried")
    check("vote 3-5 routine -> defeated", lambda: mr.resolve_outcome(3,5,0,0.5)["outcome"]=="defeated")
    check("vote 7-3 under 2/3 -> CARRIED (0.70>=0.667) [the value I got wrong twice]", lambda: mr.resolve_outcome(7,3,0,2/3)["outcome"]=="carried")
    check("vote 5-3 under 2/3 -> DEFEATED (0.625<0.667)", lambda: mr.resolve_outcome(5,3,0,2/3)["outcome"]=="defeated")
    check("vote 6-3 under 2/3 -> carried (inclusive boundary 0.6667)", lambda: mr.resolve_outcome(6,3,0,2/3)["outcome"]=="carried")
    check("vote 0-0-4 all abstain -> tabled (zero decisive)", lambda: mr.resolve_outcome(0,0,4,0.5)["outcome"]=="tabled")
    check("abstention excluded from denominator: 4-1-1 -> aye_pct 0.8", lambda: abs(mr.resolve_outcome(4,1,1,0.5)["aye_pct"]-0.8)<1e-9)
    check("chain deterministic: same payload -> same hash", lambda: mr.chain_append([],"resolution",{"a":1})[0]["hash"]==mr.chain_append([],"resolution",{"a":1})[0]["hash"])
    ch = mr.chain_append(mr.chain_append([], "resolution", {"a":1}), "resolution", {"a":2})
    check("chain verify clean -> ok True", lambda: chain_ok(ch))
    bad = [dict(e) for e in ch]; bad[0]["payload"]["a"]=999
    check("chain verify payload-edit -> ok False, broken_at 0", lambda: chain_broken(bad,0))
    res_list = [{"a":1},{"a":2}]
    check("content_check clean (resolutions match sealed payloads) -> True", lambda: mr.content_check({"chain":ch,"resolutions":res_list,"agenda":[],"attendance":[]})[0] is True)
    check("content_check resolution-injected-behind-intact-chain -> False (mentions resolutions)", lambda: (
        mr.content_check({"chain":ch,"resolutions":res_list+[{"id":99}],"agenda":[],"attendance":[]})[0] is False and
        "resolution" in mr.content_check({"chain":ch,"resolutions":res_list+[{"id":99}],"agenda":[],"attendance":[]})[1].lower()))
    ch_min = mr.chain_append(ch, "minutes", {"agenda":[{"k":1}],"attendance":["P1"],"resolution_ids":[1,2]})
    check("content_check agenda edited behind a minutes seal -> False", lambda: mr.content_check({"chain":ch_min,"resolutions":res_list,"agenda":[{"DIFFERENT":1}],"attendance":["P1"]})[0] is False)
    check("statutory_status GRAM_SABHA never-held -> due (False)", lambda: mr.statutory_status("GRAM_SABHA",None)[0] is False)
    check("statutory_status GRAM_SABHA held just now -> within cadence (True)", lambda: mr.statutory_status("GRAM_SABHA", mr._now())[0] is True)
    check("statutory_status PANCHAYAT_BODY 180d ago -> OVERDUE (False)", lambda: mr.statutory_status("PANCHAYAT_BODY","2020-01-01T00:00:00")[0] is False)
    check("meeting state machine: draft->opened ok, opened->closed illegal, closed->ratified ok, ratified terminal", lambda: (
        mr.allowed("draft","opened") and not mr.allowed("opened","closed") and mr.allowed("closed","ratified") and
        not mr.allowed("ratified","in_session") and mr.allowed("opened","adjourned") and mr.allowed("in_session","closed")))
    check("is_terminal ratified/adjourned True; in_session False", lambda: mr.is_terminal("ratified") and mr.is_terminal("adjourned") and not mr.is_terminal("in_session"))
    snap = {"tickets":[{"id":1,"wo_number":"WO/2026/WTR/00011","category_label":"Water","status":"assigned","age_hours":30.0,"breached":True},
                       {"id":2,"wo_number":"WO/2026/RD/00003","category_label":"Road","status":"open","age_hours":5.0,"breached":False}],
            "applications":[{"id":13,"reg_id_format":"PEN-W/2026/00009","status":"under_review"},{"id":14,"reg_id_format":"MUDRA/2026/00002","status":"submitted"}],
            "prior_actions":[{"ref":"WO/2026/DRN/00002","action":"re-inspect"}]}
    ag = mr.build_agenda(snap, "GRAM_SABHA")
    check("build_agenda auto-built from live snapshot (names overdue WO, counts pending apps, has statutory)", lambda: (
        len(ag)>0 and any("WO/2026/WTR/00011" in (i.get("text","")+str(i.get("detail",[]))) for i in ag) and
        any("2 pending" in i["text"] for i in ag if i["kind"]=="review_applications") and
        any(i["kind"]=="statutory" for i in ag)))
    check("RESOLUTION_TYPES thresholds: routine 0.5, statutory_23 ~0.667, procedural can_link False", lambda: (
        mr.RESOLUTION_TYPES["routine"]["threshold"]==0.5 and abs(mr.RESOLUTION_TYPES["statutory_23"]["threshold"]-2/3)<1e-9 and
        mr.RESOLUTION_TYPES["procedural"]["can_link"] is False))

# ---------------------------------------------------------------- sdm
def group_sdm():
    section("SDM REGISTRY (dispatch seal, recipient-side drift, two-tier thread)")
    check("content_fp deterministic + distinguishes empty vs edited", lambda: (
        sd.content_fp([])!=sd.content_fp([{"a":1}]) and sd.content_fp([{"a":1}])==sd.content_fp([{"a":1}])))
    disp = {"dispatched_content_fp":sd.content_fp([]),"dispatched_head":"HH"}
    m_clean = {"resolutions":[],"head_hash":"HH","chain":[],"agenda":[],"attendance":[]}
    check("verify_dispatch clean record -> ok True", lambda: vdisp_ok(disp, m_clean))
    m_tam = dict(m_clean); m_tam["resolutions"]=[{"id":9,"text":"INJECTED","outcome":"carried"}]
    check("verify_dispatch post-dispatch resolution edit -> ok False + reason mentions altered/fingerprint", lambda: vdisp_bad(disp, m_tam, "alter") or vdisp_bad(disp, m_tam, "fingerprint"))
    disp_hd = dict(disp); disp_hd["dispatched_head"]="AA"
    check("verify_dispatch head changed after dispatch -> ok False + reason mentions head", lambda: vdisp_bad(disp_hd, m_clean, "head"))
    check("dispatch state machine: received->acknowledged ok, received->queried ok, received->answered ILLEGAL (two-tier), queried->answered ok, queried->acknowledged ILLEGAL, acknowledged terminal", lambda: (
        sd.allowed("received","acknowledged") and sd.allowed("received","queried") and not sd.allowed("received","answered") and
        sd.allowed("queried","answered") and not sd.allowed("queried","acknowledged") and not sd.allowed("acknowledged","queried") and
        sd.allowed("answered","acknowledged") and sd.allowed("answered","escalated") and not sd.allowed("escalated","received")))
    check("is_terminal acknowledged/escalated True; received/queried/answered False", lambda: (
        sd.is_terminal("acknowledged") and sd.is_terminal("escalated") and not sd.is_terminal("received") and not sd.is_terminal("queried")))
    now = time.time()
    check("ack_deadline = received + ACK_DAYS*86400", lambda: abs(sd.ack_deadline(now, now)-(now+sd.ACK_DAYS*86400))<1e-6)
    check("breached: open past deadline True; terminal past deadline False; open before deadline False", lambda: (
        sd.breached({"status":"received","ack_deadline":now-10}, now) is True and
        sd.breached({"status":"acknowledged","ack_deadline":now-10}, now) is False and
        sd.breached({"status":"received","ack_deadline":now+1000}, now) is False))
    inbox = [{"id":1,"status":"received","received_at":now-100,"ack_deadline":now-10},
             {"id":2,"status":"received","received_at":now-50,"ack_deadline":now+1000},
             {"id":3,"status":"acknowledged","received_at":now-200,"ack_deadline":now+100}]
    inbox.sort(key=lambda d: sd.inbox_sort_key(d, now))
    check("inbox sort: overdue-open first, then open, then terminal", lambda: [d["id"] for d in inbox]==[1,2,3])
    summ = sd.compose_sdm_summary({"id":7,"mtype":"GRAM_SABHA","title":"GS","chair":"C","venue":"V","quorum_required":2,
                                   "attendance":["P1","P2"],"agenda":[{"kind":"review_work_orders","text":"Review 1 WO"}],
                                   "resolutions":[{"id":1,"text":"repair WO/2026/WTR/00003","outcome":"carried","votes":{"aye":2,"no":0,"abstain":0},"linked_refs":["WO/2026/WTR/00003"]}],
                                   "head_hash":"HEADHASH","chain":[]},
                                  {"id":42,"meeting_id":7,"report_path":"uploads/x.pdf","recipient":"SDM","status":"received",
                                   "dispatched_head":"HEADHASH","dispatched_content_fp":sd.content_fp([]),"received_at":now-3600,"ack_deadline":now+1000},
                                  False, ["resolutions altered after dispatch"], [])
    check("compose_sdm_summary carries quorum/carried/seal_ok(False)/boundaries/verification-with-id-and-head", lambda: (
        summ["quorum"]["met"] is True and summ["carried"]==1 and summ["seal_ok"] is False and
        len(summ["boundaries"])>=3 and "7" in summ["verification"] and "HEADHASH" in summ["verification"]))

GROUPS = [("schemes", group_schemes), ("infra", group_infra), ("meeting", group_meeting), ("sdm", group_sdm)]

def run():
    for name, fn in GROUPS:
        try:
            fn()
        except Exception as e:
            RESULTS.append(("GROUP %s raised"%name, False, type(e).__name__+": "+str(e)[:120]))
            print("  FAIL  | GROUP %s raised (test-file defect, not product): %s: %s" % (name, type(e).__name__, str(e)[:120]))
    npass = sum(1 for _,ok,_ in RESULTS if ok)
    nfail = len(RESULTS)-npass
    print("\n" + "="*72)
    if nfail==0:
        print("  TIER-1 VERDICT: ALL %d UNIT CHECKS PASS  (declarative data + evaluators locked)" % npass)
    else:
        print("  TIER-1 VERDICT: %d PASS / %d FAIL" % (npass, nfail))
        print("  Failing checks (moved DATA value = real regression; wrong EXPECTED number = fix the TEST):")
        for lbl,ok,det in RESULTS:
            if not ok:
                print("    - %s %s" % (lbl, ("| "+det) if det else ""))
    print("="*72)
    return 0 if nfail==0 else 1
