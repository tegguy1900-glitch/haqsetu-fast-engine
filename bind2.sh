#!/usr/bin/env bash
# Haq Setu bind2: close the 3 reds the REAL rulepack exposed.
#  (1) loader coerces PyYAML date objects -> ISO strings (fixes village json crash + round-trip)
#  (2) rule_engine adopts your engine/rules.py PRIORITY verbatim (max/most-cautious; was inverted)
#  (3) brain-audit + rulepack-bind PART6 become catalog-agnostic / real-aware (they asserted the old seed world)
# Whole-file rewrites only. village/facts/entitlement/catalog UNTOUCHED.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

# =================== rulepack/loader.py  (+ recursive date coercion: the village-crash fix) ===================
cat > rulepack/loader.py <<'PYEOF'
"""Harvest the REAL rulepack YAML (DATA) into engine rows. We do NOT import legacy
engine/rules.py classes; we read your YAML schema and translate faithfully. PyYAML-guarded:
if the parser or the dir is missing, load_rulepack_dir returns None and the caller falls
back to the SEED catalog LOUDLY (provisional) -- we never hand-roll a YAML parse.
CRITICAL (the village crash): your schema.py types verified_on/expires_on as `date`, and
PyYAML deserializes bare `2027-10-09` into datetime.date OBJECTS. A date object is not
JSON-serializable, so it would 500 the /voice HTTP body and break the ledger write. We
recursively coerce EVERY date/datetime in a row to its ISO string at harvest, so no date
object ever reaches json.dumps or the PII guard. This is the single fix for the
'TypeError: Object of type date is not JSON serializable' red."""
import os, glob, datetime
def _coerce_dates(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _coerce_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_dates(v) for v in obj]
    return obj
def discover_root():
    cands = [os.environ.get("HAQ_RULEPACK"), os.getcwd(),
             os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
    for base in cands:
        if base and os.path.isdir(os.path.join(base, "rulepack", "schemes")):
            return base
    return None
def load_rulepack_dir(root=None):
    root = root if root is not None else discover_root()
    if not root: return None
    try:
        import yaml
    except Exception:
        return None                      # no safe parser -> caller goes provisional
    packs = []
    for sub in ("schemes", "routes"):
        for f in sorted(glob.glob(os.path.join(root, "rulepack", sub, "*.yaml"))):
            try:
                doc = yaml.safe_load(open(f, encoding="utf-8"))
            except Exception:
                continue                 # a bad file is SKIPPED, not guessed
            if isinstance(doc, dict) and "scheme" in doc and "rules" in doc:
                packs.append(doc)
    return packs or None
def rows_from_packs(packs):
    """Faithful translation: when(AND)->requires; carry outcome/documents/desk/clock_hours/
    contact/source/verified_*/expires_on/test_vectors. One row per (scheme,rule). All date
    objects coerced to ISO strings (see _coerce_dates) so downstream json + guard are safe."""
    rows = []
    for pk in packs or []:
        sid = pk.get("scheme"); st = pk.get("state", "")
        for rl in pk.get("rules", []) or []:
            reqs = [{"fact": c.get("field"), "op": c.get("op", "eq"), "value": c.get("value")}
                    for c in (rl.get("when", []) or [])]
            row = {
                "scheme_id": sid, "rule_id": rl.get("id"), "state": st,
                "description": rl.get("description", ""), "requires": reqs,
                "outcome": rl.get("outcome", "include"),
                "documents": rl.get("documents", []) or [], "desk": rl.get("desk", ""),
                "clock_hours": rl.get("clock_hours"), "contact": rl.get("contact"),
                "source": rl.get("source", {}) or {},
                "verified_on": rl.get("verified_on"), "verified_by": rl.get("verified_by", []) or [],
                "expires_on": rl.get("expires_on"), "test_vectors": rl.get("test_vectors", []) or [],
            }
            rows.append(_coerce_dates(row))
    return rows
PYEOF

# =================== core/rule_engine.py  (adopt YOUR engine/rules.py PRIORITY verbatim) ===================
cat > core/rule_engine.py <<'PYEOF'
"""
Haq Setu - Rule engine. Evaluates facts against the catalog. Catalog source is LAZY:
the REAL rulepack YAML if discoverable+parseable (it IS, on this box), else the auditable
SEED catalog with provisional=True (loud, never silent). Contract match_fn(facts)->
{confidence, schemes, trace, routed_verifies, provisional} is UNCHANGED so process_voice
and village are untouched; extra keys are additive. NEVER asserts a scheme outside the
catalog; NEVER fills a missing fact; a LAPSED rule (expires_on < today) is never acted on.

PRIORITY is taken VERBATIM from your engine/rules.py:
    PRIORITY = {Outcome.VERIFY:3, Outcome.NEEDS_OFFICIAL_DECISION:2, Outcome.INCLUDE:1}
    final    = max(matched_outcomes, key=PRIORITY)        # most-cautious wins
(An earlier draft of this file inverted it with min/include-wins; corrected here against
your literal constant. So among a scheme's FULLY-MATCHED rules, the most cautious outcome
governs: a scheme with both an include and a verify rule is routed to verify, not minted.)
Trace shape additionally mirrors your engine/matcher.py proof: per-scheme decision
(INCLUDE/ESCALATE) + a formal_logic one-liner + matched/failed clause lists. We do NOT
embed citizen_facts on-chain (avoid any leak surface); facts carry no name/phone anyway.
"""
from datetime import date
from rulepack import loader as _ld
from rulepack.catalog import SCHEMES as _SEED

_OPS = {"eq": lambda a,b:a==b, "ne": lambda a,b:a!=b, "gt": lambda a,b:a>b,
        "gte": lambda a,b:a>=b, "lt": lambda a,b:a<b, "lte": lambda a,b:a<=b,
        "in": lambda a,b:(a in b) if isinstance(b,(list,tuple,set)) else False,
        "not_in": lambda a,b:(a not in b) if isinstance(b,(list,tuple,set)) else True,
        "truthy": lambda a,b:bool(a), "falsy": lambda a,b:not bool(a),
        ">=": lambda a,b:a>=b, "<=": lambda a,b:a<=b, ">": lambda a,b:a>b, "<": lambda a,b:a<b,
        "==": lambda a,b:a==b, "!=": lambda a,b:a!=b}
# VERBATIM from your engine/rules.py (most-cautious wins via max):
_PRIORITY = {"include": 1, "needs_official_decision": 2, "verify": 3}
_RANK2NAME = {1: "include", 2: "needs_official_decision", 3: "verify"}

_cat = None; _prov = None
def _catalog():
    global _cat, _prov
    if _cat is None:
        packs = _ld.load_rulepack_dir()
        if packs:
            _cat = _ld.rows_from_packs(packs); _prov = False
        else:
            _cat = [{"scheme_id": s["id"], "rule_id": s["id"]+"_seed", "state": "",
                     "description": s.get("name",""), "requires": s.get("requires",[]),
                     "outcome": "include", "documents": s.get("docs",[]), "desk": "",
                     "clock_hours": None, "contact": None, "source": {"doc": s.get("source","")},
                     "verified_on": None, "verified_by": ["Seed", "VERIFY-BEFORE-PROD"],
                     "expires_on": None, "test_vectors": []} for s in _SEED]
            _prov = True
    return _cat, _prov

def _clause(c, facts):
    fact = c.get("fact"); op = c.get("op","eq"); val = c.get("value")
    if fact not in facts: return "missing", {"fact": fact, "note": "not provided"}
    got = facts[fact]; fn = _OPS.get(op)
    if fn is None: return "missing", {"fact": fact, "note": f"unknown op {op}"}
    try: ok = bool(fn(got, val))
    except Exception: return "missing", {"fact": fact, "note": "type mismatch"}
    return ("sat" if ok else "fail"), {"fact": fact, "op": op, "value": val, "observed": got, "result": ok}

def _eval_row(row, facts, today):
    if row.get("expires_on") and str(row["expires_on"]) < today:
        return "lapsed", []                       # don't act on lapsed authority
    sat=[]; miss=[]; fail=[]
    for c in row.get("requires",[]):
        st,pr=_clause(c,facts); (sat if st=="sat" else miss if st=="missing" else fail).append(pr)
    if fail: return "ineligible", sat+fail
    if miss: return "uncertain", sat+miss
    return "match", sat

def _formal_logic(sid, oname, clauses):
    parts = " AND ".join(f'{c["fact"]} {c.get("op","==")} {c.get("value")!r}'
                         for c in clauses if "op" in c) or "no conditions"
    return f'{sid.upper()} := ({parts}) -> {oname.upper()}'

def evaluate(rows, facts, today=None):
    facts = facts or {}; today = today or date.today().isoformat()
    by_scheme = {}
    for r in rows:
        st, proofs = _eval_row(r, facts, today)
        by_scheme.setdefault(r["scheme_id"], []).append((r, st, proofs))
    includes=[]; verifies=[]; trace=[]
    for sid, evs in by_scheme.items():
        matched = [(r,p) for (r,st,p) in evs if st=="match"]
        lapsed  = any(st=="lapsed" for (_,st,_) in evs)
        if matched:
            rank = max((_PRIORITY.get(r.get("outcome","include"),2) for r,_ in matched), default=2)
            oname = _RANK2NAME[rank]                                   # most-cautious wins (your PRIORITY)
            allp = [p for _,p in matched]
            for r,p in matched:
                trace.append({"scheme": sid, "scheme_name": r.get("description","") or sid,
                              "rule_id": r.get("rule_id"), "outcome": oname,
                              "decision": ("INCLUDE" if oname=="include" else "ESCALATE"),
                              "formal_logic": _formal_logic(sid, oname, p),
                              "clauses": p, "docs": r.get("documents",[]), "benefit": r.get("desk",""),
                              "verified_by": r.get("verified_by",[]), "source": r.get("source",{}),
                              "expires_on": r.get("expires_on"), "lapsed": lapsed})
            if oname=="include": includes.append(sid)
            elif oname=="verify": verifies.append(sid)
        else:
            miss_facts = sorted({pr["fact"] for (_,st,ps) in evs if st in ("uncertain","lapsed") for pr in ps if pr.get("note")=="not provided"})
            trace.append({"scheme": sid, "scheme_name": sid, "rule_id": None,
                          "outcome": "needs_official_decision", "decision": "ESCALATE",
                          "formal_logic": _formal_logic(sid, "needs_official_decision", []),
                          "clauses": [], "docs": [], "benefit": None, "verified_by": [], "source": {},
                          "expires_on": None, "lapsed": lapsed,
                          "uncertain_facts": miss_facts,
                          "note": ("all rules lapsed" if lapsed else "no rule fully matched")})
    conf = round(min(0.97, 0.6 + 0.12*len(includes)), 2) if includes else 0.0
    _, prov = _catalog()
    return {"confidence": conf, "schemes": sorted(set(includes)),
            "routed_verifies": sorted(set(verifies)), "trace": trace, "provisional": prov}

def match_fn(facts):
    rows, _ = _catalog()
    return evaluate(rows, facts)

def to_api_match_shape(facts, civic_hints=None):
    """Mirror your /api/match + triage/abstain contract {action,facts,civic,can,likely,case,speak}.
    can=confident includes; likely=uncertain-but-partial; civic=verify-routed (+ any hints).
    ABSTAIN when nothing confident -- exactly your intake_abstain path."""
    res = match_fn(facts)
    can = res["schemes"]; civic = list(res["routed_verifies"])
    if civic_hints:
        civic = sorted(set(civic) | set(civic_hints))
    likely = sorted({t["scheme"] for t in res["trace"]
                     if t.get("outcome")=="needs_official_decision" and t.get("uncertain_facts")})
    if not can and not civic:
        action="ABSTAIN"; speak="I did not catch clear conditions. The facilitator will ask one question."
    elif can:
        action="INCLUDE"; speak=f"Based on what you told me, you appear eligible for {len(can)} scheme(s)."
    else:
        action="VERIFY"; speak=f"This looks like a grievance to route for verification ({len(civic)})."
    return {"action": action, "facts": facts, "civic": civic, "can": can,
            "likely": likely, "case": "", "speak": speak, "provisional": res["provisional"]}
PYEOF

# =================== core/run_brain_audit.py  (catalog-agnostic: proves the MACHINE, not seed ids) ===================
cat > core/run_brain_audit.py <<'PYEOF'
"""Pillar-1 brain audit, CATALOG-AGNOSTIC. Run: python -m core.run_brain_audit.
Proves the MACHINE against WHATEVER catalog is live (here: your REAL rulepack, since the
YAML dir is on disk). Asserts NEVER-fabricate, NEVER-deny, only-live-ids, expiry, provenance
(your schema min_length=2 verified_by), write-guard, and the /api/match mirror -- using
SUBSTRING id matches + the live id-set, so it passes on seed OR real and breaks if the
engine ever fabricates an id or a fact. Field keys use your REAL vocabulary (annual_income_inr)."""
import sys, json, datetime
from core import facts as fx, rule_engine as eng
from ledger.chain import _scan_pii, PiiLeakError
FAIL=[]
def chk(n,c,e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
def _scan_ok(p):
    try: _scan_pii(p); return True,""
    except PiiLeakError as ex: return False,str(ex)

def main():
    live_rows, prov = eng._catalog()
    live_ids = {r["scheme_id"] for r in live_rows}
    print("##### PILLAR-1 BRAIN AUDIT (catalog-agnostic; live catalog is %s, %d schemes) #####"
          % ("REAL rulepack" if not prov else "SEED(provisional)", len(live_ids)))
    # ---- extractor: REAL field keys, never-invent ----
    f = fx.extract("Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai")
    chk("extract age=68 (cue 'saal')", f.get("age")==68, str(f))
    chk("extract is_widow", f.get("is_widow") is True)
    chk("extract has_pucca_house=False (kacha)", f.get("has_pucca_house") is False)
    chk("extract annual_income_inr=80000 (80 hazaar)", f.get("annual_income_inr")==80000, str(f.get("annual_income_inr")))
    chk("extract Indian comma 1,20,000=120000", fx.extract("aamdani 1,20,000 rupaye").get("annual_income_inr")==120000)
    chk("extract comma did NOT invent age=20", "age" not in fx.extract("aamdani 1,20,000 rupaye"))
    chk("extract compound 2 lakh 50 hazaar=250000", fx.extract("kamai 2 lakh 50 hazaar").get("annual_income_inr")==250000)
    chk("extract no-overread stops at 'hai'", fx.extract("aamdani 80 hazaar hai aur 2 bachche").get("annual_income_inr")==80000)
    chk("extract no stray number after negation", "annual_income_inr" not in fx.extract("income nahi hai, 2 bachche"))
    chk("no-fabrication: 'budhi' invents no age", "age" not in fx.extract("bahut budhi hoon, garib hoon"))
    chk("garib => is_bpl True", fx.extract("garib hoon").get("is_bpl") is True)
    chk("loss% 40 -> crop_loss_percentage=40.0", fx.extract("fasal 40 percent kharab").get("crop_loss_percentage")==40.0)
    chk("15 din -> days_since_work_demand=15", fx.extract("15 din se kaam nahi mila").get("days_since_work_demand")==15)
    chk("2 hafte -> 14 days", fx.extract("2 hafte se kaam ka intezaar").get("days_since_work_demand")==14)
    chk("neg-first: 'not insured' -> False", fx.extract("I am not insured under PMFBY").get("is_insured") is False)
    chk("positive beema -> True", fx.extract("PMFBY ke tahat beema karwaya").get("is_insured") is True)
    chk("off-topic -> no fabricated facts", fx.extract("aaj mausam kaisa hai")=={})
    # ---- engine: NEVER-deny + only-live-ids + provenance + decision ----
    r_empty = eng.match_fn({})
    chk("empty facts -> ABSTAIN (conf<0.3, no schemes, no verifies)",
        r_empty["confidence"]<0.3 and r_empty["schemes"]==[] and r_empty["routed_verifies"]==[], str(r_empty["confidence"]))
    chk("empty-facts trace all ESCALATE/needs", all(t["outcome"]=="needs_official_decision" for t in r_empty["trace"]))
    rw = eng.match_fn({"is_widow":True})
    chk("is_widow -> a widow scheme INCLUDED (substring, catalog-agnostic)",
        any("widow" in s for s in rw["schemes"]), str(rw["schemes"]))
    chk("returned ids are SUBSET of live catalog (never fabricates a scheme)",
        all(s in live_ids for s in rw["schemes"]), str([s for s in rw["schemes"] if s not in live_ids]))
    wt = next((t for t in rw["trace"] if "widow" in t["scheme"] and t["outcome"]=="include"), None)
    chk("included trace has decision=INCLUDE + formal_logic", wt and wt["decision"]=="INCLUDE" and "INCLUDE" in wt["formal_logic"], str(wt and wt["formal_logic"]))
    chk("provenance: verified_by present AND len>=2 (your schema min_length=2)", wt and len(wt["verified_by"])>=2, str(wt and wt["verified_by"]))
    chk("provenance: source url present (SDM sees authority)", wt and bool((wt["source"] or {}).get("url")), str(wt and wt["source"]))
    chk("expires_on is a STRING not a date object (coercion held)", wt and isinstance(wt["expires_on"], str), str(type(wt and wt["expires_on"])))
    rc = eng.match_fn({"crop_loss_percentage":40})
    chk("crop_loss 40% -> a crop scheme INCLUDED", any("crop" in s for s in rc["schemes"]), str(rc["schemes"]))
    rr = eng.match_fn({"road_damaged":True})
    chk("road_damaged -> VERIFY-routed, NOT entitlement include",
        any("road" in s for s in rr["routed_verifies"]) and not any("road" in s for s in rr["schemes"]),
        str({k:rr[k] for k in('schemes','routed_verifies')}))
    rp = eng.match_fn({"is_student":True,"class_gte":11})
    chk("post_matric BOTH facts -> matric scheme INCLUDED", any("matric" in s for s in rp["schemes"]), str(rp["schemes"]))
    rpart = eng.match_fn({"is_student":True})
    chk("post_matric PARTIAL -> NOT included (never-guess)", not any("matric" in s for s in rpart["schemes"]), str(rpart["schemes"]))
    chk("partial trace names the missing fact class_gte",
        any("class_gte" in (t.get("uncertain_facts") or []) for t in rpart["trace"] if "matric" in t["scheme"]),
        str([t.get("uncertain_facts") for t in rpart["trace"] if "matric" in t["scheme"]]))
    # ---- expiry with a REAL date OBJECT (proves coercion end-to-end + json-safety) ----
    lapack = {"scheme":"widow_pension","state":"haryana","rules":[{"id":"lp_001","description":"x",
        "when":[{"field":"is_widow","op":"eq","value":True}],"outcome":"include","documents":[],
        "desk":"bdo","source":{"doc":"d","clause":"c","url":"u"},"verified_on":datetime.date(2026,1,1),
        "verified_by":["A","B"],"expires_on":datetime.date(2025,1,1),"test_vectors":[]}]}
    lrows = __import__("rulepack.loader", fromlist=["x"]).rows_from_packs([lapack])
    chk("loader coerced a date OBJECT to ISO string", isinstance(lrows[0]["expires_on"], str) and lrows[0]["expires_on"]=="2025-01-01", str(lrows[0]["expires_on"]))
    rl = eng.evaluate(lrows, {"is_widow":True}, today="2026-10-21")
    chk("LAPSED rule (date obj, expires 2025<2026) -> NOT included", "widow_pension" not in rl["schemes"], str(rl["schemes"]))
    chk("lapsed trace flags lapsed + ESCALATE", any(t.get("lapsed") and t["decision"]=="ESCALATE" for t in rl["trace"]))
    try:
        json.dumps(rl["trace"]); chk("lapsed trace JSON-serializable (no date obj leaked)", True)
    except TypeError as e:
        chk("lapsed trace JSON-serializable (no date obj leaked)", False, str(e))
    # ---- write-guard on the EXACT emitted payloads ----
    mp = {"schemes":rw["schemes"],"confidence":rw["confidence"],"proof_trace":rw["trace"],"facts_keys":sorted(f.keys())}
    okm,em=_scan_ok(mp); chk("matched payload passes ledger PII guard (write-path)", okm, em)
    ap = {"reason":"low_confidence_or_unsure","confidence":r_empty["confidence"],"facts_keys":[]}
    oka,ea=_scan_ok(ap); chk("abstain payload passes ledger PII guard (write-path)", oka, ea)
    # ---- /api/match mirror ----
    a0=eng.to_api_match_shape({}); chk("mirror empty -> ABSTAIN", a0["action"]=="ABSTAIN" and a0["can"]==[] and a0["civic"]==[])
    a1=eng.to_api_match_shape({"is_widow":True}); chk("mirror is_widow -> can has a widow scheme", any("widow" in s for s in a1["can"]), str(a1["can"]))
    a2=eng.to_api_match_shape({"road_damaged":True}); chk("mirror road -> civic routed, can empty", a2["civic"] and not a2["can"], str({k:a2[k] for k in('action','can','civic')}))
    print("\n[RESULT]", "BRAIN AUDIT GREEN (catalog-agnostic)" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__=="__main__": main()
PYEOF

# =================== core/run_rulepack_bind.py  (PART1-5 verbatim; PART6 -> assert the LIVE real bind) ===================
cat > core/run_rulepack_bind.py <<'PYEOF'
"""Bind-the-real-rulepack proof. Every assertion grounded in YAML/contract VISIBLE in the
upload. PART1-5 faithful-translation/semantics/vectors/expiry/extractor (unchanged, were green).
PART6 REWRITTEN: the earlier 'provisional True in sandbox' premise was WRONG -- the real
rulepack dir IS on disk, so the engine loads it and provisional is False. PART6 now asserts
the LIVE real bind (a real-only id served + provisional False) and the date-coerced round-trip."""
import sys, json, datetime
from rulepack import loader as ld
from core import rule_engine as eng, facts as fx
FAIL=[]
def chk(n,c,e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)
WIDOW = {"scheme":"widow_pension","state":"haryana","rules":[{"id":"widow_pension_001",
  "description":"Widow Pension eligibility.","when":[{"field":"is_widow","op":"eq","value":True}],
  "outcome":"include","documents":["aadhaar","death_cert"],"desk":"bdo",
  "source":{"doc":"Widow Pension Guidelines","clause":"Eligibility","url":"https://india.gov.in/"},
  "verified_on":"2026-10-09","verified_by":["System","Auto-Verifier"],"expires_on":"2027-10-09",
  "test_vectors":[{"input":{},"expect":"needs_official_decision"}]}]}
POSTMAT = {"scheme":"post_matric","state":"haryana","rules":[{"id":"post_matric_001",
  "description":"Post-Matric Sch. eligibility.",
  "when":[{"field":"is_student","op":"eq","value":True},{"field":"class_gte","op":"eq","value":11}],
  "outcome":"include","documents":["aadhaar","income_cert"],"desk":"education_dept",
  "source":{"doc":"Post-Matric Sch. Guidelines","clause":"Eligibility","url":"https://india.gov.in/"},
  "verified_on":"2026-10-09","verified_by":["System","Auto-Verifier"],"expires_on":"2027-10-09",
  "test_vectors":[{"input":{},"expect":"needs_official_decision"}]}]}
POSHAN = {"scheme":"poshan","state":"haryana","rules":[{"id":"poshan_001",
  "description":"Poshan Abhiyaan eligibility.","when":[{"field":"is_pregnant_or_lactating","op":"eq","value":True}],
  "outcome":"include","documents":["aadhaar"],"desk":"anganwadi",
  "source":{"doc":"Poshan Abhiyaan Guidelines","clause":"Eligibility","url":"https://india.gov.in/"},
  "verified_on":"2026-10-09","verified_by":["System","Auto-Verifier"],"expires_on":"2027-10-09",
  "test_vectors":[{"input":{},"expect":"needs_official_decision"}]}]}
ROAD = {"scheme":"road_repair","state":"haryana","rules":[{"id":"road_repair_001",
  "description":"Road Repair grievance.","when":[{"field":"road_damaged","op":"eq","value":True}],
  "outcome":"verify","documents":[],"desk":"block_development_officerclock_hours":72,"contact":"Grievance Officer",
  "source":{"doc":"Civic Guidelines","clause":"SLA","url":"https://india.gov.in/"},
  "verified_on":"2026-10-09","verified_by":["System","Auto-Verifier"],"expires_on":"2027-10-09",
  "test_vectors":[{"input":{},"expect":"needs_official_decision"}]}]}
def part1():
    print("\n##### PART 1 : faithful translation of YOUR schema (rows_from_packs) #####")
    rows = ld.rows_from_packs([WIDOW, POSTMAT, POSHAN, ROAD]); by={r["rule_id"]:r for r in rows}
    w=by["widow_pension_001"]
    chk("widow row scheme_id/rule_id carried", w["scheme_id"]=="widow_pension" and w["rule_id"]=="widow_pension_001")
    chk("widow when(AND)->requires, op eq, value True", w["requires"]==[{"fact":"is_widow","op":"eq","value":True}], str(w["requires"]))
    chk("widow outcome=include carried", w["outcome"]=="include")
    chk("widow expires_on carried", w["expires_on"]=="2027-10-09", str(w["expires_on"]))
    chk("widow verified_by carried (provenance)", w["verified_by"]==["System","Auto-Verifier"], str(w["verified_by"]))
    chk("widow source doc/clause/url carried", w["source"]["doc"]=="Widow Pension Guidelines" and w["source"]["url"]=="https://india.gov.in/")
    chk("widow test_vector carried", w["test_vectors"]==[{"input":{},"expect":"needs_official_decision"}])
    pm=by["post_matric_001"]; chk("post_matric AND of TWO when -> two requires", len(pm["requires"])==2 and pm["requires"][1]["fact"]=="class_gte", str(pm["requires"]))
    rd=by["road_repair_001"]; chk("route outcome=verify + clock_hours + contact + desk carried", rd["outcome"]=="verify" and rd["clock_hours"]==72 and rd["contact"]=="Grievance Officer" and rd["desk"]=="block_development_officerclock_hours", str({k:rd[k] for k in('outcome','clock_hours','contact','desk')}))
def part2():
    print("\n##### PART 2 : engine honors YOUR semantics (include/verify/AND/never-guess) #####")
    rows=ld.rows_from_packs([WIDOW,POSTMAT,POSHAN,ROAD])
    r1=eng.evaluate(rows,{"is_widow":True},today="2026-10-21")
    chk("is_widow True -> widow_pension INCLUDED","widow_pension" in r1["schemes"],str(r1["schemes"]))
    chk("included trace carries provenance verified_by",any(t.get("verified_by")==["System","Auto-Verifier"] for t in r1["trace"] if t["scheme"]=="widow_pension"))
    chk("included trace carries source url (SDM sees authority)",any((t.get("source") or {}).get("url")=="https://india.gov.in/" for t in r1["trace"] if t["scheme"]=="widow_pension"))
    r2=eng.evaluate(rows,{"is_student":True,"class_gte":11},today="2026-10-21")
    chk("post_matric BOTH when met -> included","post_matric" in r2["schemes"],str(r2["schemes"]))
    r3=eng.evaluate(rows,{"is_student":True},today="2026-10-21")
    chk("post_matric PARTIAL facts -> NOT included (never-guess)","post_matric" not in r3["schemes"],str(r3["schemes"]))
    chk("partial-facts trace lists the missing fact",any("class_gte" in (t.get("uncertain_facts") or []) for t in r3["trace"] if t["scheme"]=="post_matric"),str([t.get("uncertain_facts") for t in r3["trace"] if t["scheme"]=="post_matric"]))
    r4=eng.evaluate(rows,{"road_damaged":True},today="2026-10-21")
    chk("road_damaged -> VERIFY-routed, NOT an entitlement include","road_repair" in r4["routed_verifies"] and "road_repair" not in r4["schemes"],str({k:r4[k] for k in('schemes','routed_verifies')}))
def part3():
    print("\n##### PART 3 : YOUR test_vectors enforce never-deny (empty input -> abstain) #####")
    rows=ld.rows_from_packs([WIDOW,POSTMAT,POSHAN,ROAD]); abstained=True
    for r in rows:
        for tv in r["test_vectors"]:
            res=eng.evaluate([r],tv["input"],today="2026-10-21"); want=tv["expect"]
            got="needs_official_decision" if (want=="needs_official_decision" and not res["schemes"] and not res["routed_verifies"]) else "OTHER"
            if got!=want: abstained=False
            chk(f"vector {r['rule_id']} input={tv['input']} -> {want}",got==want,f"got {got}; schemes={res['schemes']}")
    chk("ALL your test_vectors abstain on empty input (never-deny, YOUR data)",abstained)
def part4():
    print("\n##### PART 4 : expiry + provenance (don't act on lapsed authority) #####")
    rows=ld.rows_from_packs([WIDOW]); rr=[dict(rows[0],expires_on="2025-01-01")]
    rl=eng.evaluate(rr,{"is_widow":True},today="2026-10-21")
    chk("LAPSED rule -> NOT included (expires_on < today)","widow_pension" not in rl["schemes"],str(rl["schemes"]))
    chk("lapsed trace flags lapsed=True + note",any(t.get("lapsed") and "lapsed" in (t.get("note") or "") for t in rl["trace"] if t["scheme"]=="widow_pension"),str([t.get('note') for t in rl['trace']]))
    rn=eng.evaluate(rows,{"is_widow":True},today="2026-10-21")
    chk("NON-lapsed rule (2027-10-09) -> included","widow_pension" in rn["schemes"])
def part5():
    print("\n##### PART 5 : grounded extractor additions (your visible regexes) #####")
    chk("loss% 40 percent -> crop_loss_percentage=40.0",fx.extract("meri fusal 40 percent kharab ho gayi").get("crop_loss_percentage")==40.0)
    chk("15 din -> days_since_work_demand=15",fx.extract("15 din se kaam nahi mila").get("days_since_work_demand")==15)
    chk("2 hafte -> days_since_work_demand=14",fx.extract("2 hafte se kaam ka intezaar").get("days_since_work_demand")==14)
    chk("neg-first: 'not insured' -> is_insured=False (NOT True)",fx.extract("I am not insured under PMFBY").get("is_insured") is False)
    chk("positive: beema karwaya -> is_insured=True",fx.extract("maine PMFBY ke tahat beema karwaya tha").get("is_insured") is True)
    chk("off-topic -> no fabricated facts",fx.extract("aaj mausam kaisa hai")=={})
def part6():
    print("\n##### PART 6 : the LIVE real bind + date-coerced round-trip (premise corrected) #####")
    chk("load_rulepack_dir('/nonexistent') -> None (no silent parse)", ld.load_rulepack_dir("/nonexistent") is None)
    rows, prov = eng._catalog()
    ids = {r["scheme_id"] for r in rows}
    chk("REAL rulepack is LIVE on disk -> provisional is False", prov is False, str(prov))
    chk("live catalog carries REAL-only ids (not in the 12-row seed)",
        {"widow_pension","crop_loss","road_repair","pm_kisan","kcc","soil_health"} <= ids,
        str(sorted(ids)[:12]))
    chk("live catalog is LARGE (your expand_rulepack ~50 schemes + ~20 routes)", len(ids) >= 20, f"{len(ids)} schemes")
    chk("a real-only id actually decides: is_widow -> widow_pension included",
        "widow_pension" in eng.match_fn({"is_widow":True})["schemes"])
    try:
        import yaml
        ytxt=("scheme: widow_pension\nstate: haryana\nrules:\n- id: widow_pension_001\n"
              "  description: \"Widow Pension eligibility.\"\n  when:\n  - field: is_widow\n    op: eq\n    value: true\n"
              "  outcome: include\n  documents: ['aadhaar', 'death_cert']\n  desk: bdo\n"
              "  source: {doc: \"Widow Pension Guidelines\", clause: \"Eligibility\", url: \"https://india.gov.in/\"}\n"
              "  verified_on: 2026-10-09\n  verified_by: [System, Auto-Verifier]\n  expires_on: 2027-10-09\n"
              "  test_vectors:\n  - input: {}\n    expect: needs_official_decision\n")
        pk=yaml.safe_load(ytxt)
        chk("PyYAML parsed bare date as a date OBJECT (the crash source)", isinstance(pk["rules"][0]["expires_on"], datetime.date), str(type(pk["rules"][0]["expires_on"])))
        rw=ld.rows_from_packs([pk])[0]
        chk("loader COERCED that date object -> ISO string (round-trip faithful + json-safe)",
            rw["requires"]==[{"fact":"is_widow","op":"eq","value":True}] and rw["expires_on"]=="2027-10-09" and rw["verified_on"]=="2026-10-09" and rw["verified_by"]==["System","Auto-Verifier"],
            f"expires_on={rw['expires_on']!r} verified_on={rw['verified_on']!r}")
        json.dumps(rw); chk("coerced row JSON-serializable (village /voice crash fixed at the source)", True)
    except ImportError:
        print("  [note] PyYAML absent -> round-trip skipped; live-bind assertions above stand.")
    a0=eng.to_api_match_shape({}); chk("mirror empty -> ABSTAIN (your intake_abstain)", a0["action"]=="ABSTAIN" and a0["can"]==[] and a0["civic"]==[])
    a1=eng.to_api_match_shape({"is_widow":True}); chk("mirror is_widow -> can includes a widow scheme", any("widow" in s for s in a1["can"]), str(a1["can"]))
    a2=eng.to_api_match_shape({"road_damaged":True}); chk("mirror road_damaged -> civic routed (verify), not can", a2["civic"] and not a2["can"], str({k:a2[k] for k in('action','can','civic')}))
def main():
    print("##### BIND THE REAL RULEPACK (data + contract harvested; legacy chain NOT resurrected) #####")
    part1(); part2(); part3(); part4(); part5(); part6()
    print("\n[RESULT]", "RULEPACK BOUND (LIVE)" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__=="__main__": main()
PYEOF

echo "########## SYNTAX / IMPORT SMOKE ##########"
python -m py_compile rulepack/loader.py core/rule_engine.py core/run_brain_audit.py core/run_rulepack_bind.py \
  && echo "  [OK] 4 files compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import rulepack.loader, core.rule_engine, core.run_brain_audit, core.run_rulepack_bind, village.server; print('  [OK] imports resolve (loader+engine+audits+village)')" || exit 1

echo "########## GATES (real-catalog bind + unregression) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/b2_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_BLOCK_DB="$d/block.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 HAQ_BLOCK_PORT=8100 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 30
  local rc="${PIPESTATUS[0]}"; printf '>>> %-14s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "rulepack-bind" python -m core.run_rulepack_bind
gate "brain-audit"  python -m core.run_brain_audit
gate "village"      python -m core.run_village_demo
gate "pillar1"      python -m core.run_pillar1_demo
gate "launch"       python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "REAL RULEPACK LIVE :: your ~70 YAML schemes drive decisions on the unified ledger; PRIORITY adopted verbatim from engine/rules.py; PyYAML date objects coerced (village crash gone); audit is catalog-agnostic (proves the machine, not seed ids); never-deny enforced by YOUR test_vectors" || echo "SOME GATE RED :: see exit!=0 above"
