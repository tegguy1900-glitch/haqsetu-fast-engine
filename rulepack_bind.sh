#!/usr/bin/env bash
# Haq Setu - bind the REAL rulepack DATA + API contract into the unified engine.
# Harvests rulepack/schemes|routes YAML (fully visible) -> engine rows; mirrors the
# /api/match contract. Does NOT import legacy engine/rules.py classes (defs not in dump)
# and does NOT resurrect the legacy chain. Grievance ROUTING (verify->civic case) is the
# named NEXT wire; today a grievance-only utterance abstains at the entitlement seam
# (safe, never mis-mints a receipt). to_api_match_shape is the bridge.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

# =================== rulepack/loader.py  (NEW: YAML data -> engine rows, yaml-guarded, loud fallback) ===================
cat > rulepack/loader.py <<'PYEOF'
"""Harvest the REAL rulepack YAML (DATA) into engine rows. We do NOT import legacy
engine/rules.py classes (their full defs aren't in the dump); we read your YAML schema
(fully visible) and translate faithfully. PyYAML-guarded: if the tool or the dir is
missing, load_rulepack_dir returns None and the caller falls back to the SEED catalog
LOUDLY (provisional) -- we never hand-roll a YAML parse, because a subtle mis-parse =
a silently wrong rule = the exact failure this build exists to prevent."""
import os, glob
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
    """Faithful translation: when(AND) -> requires; carry outcome/documents/desk/
    clock_hours/contact/source/verified_*/expires_on/test_vectors. One row per (scheme,rule)."""
    rows = []
    for pk in packs or []:
        sid = pk.get("scheme"); st = pk.get("state", "")
        for rl in pk.get("rules", []) or []:
            reqs = [{"fact": c.get("field"), "op": c.get("op", "eq"), "value": c.get("value")}
                    for c in (rl.get("when", []) or [])]
            rows.append({
                "scheme_id": sid, "rule_id": rl.get("id"), "state": st,
                "description": rl.get("description", ""), "requires": reqs,
                "outcome": rl.get("outcome", "include"),
                "documents": rl.get("documents", []) or [], "desk": rl.get("desk", ""),
                "clock_hours": rl.get("clock_hours"), "contact": rl.get("contact"),
                "source": rl.get("source", {}) or {},
                "verified_on": rl.get("verified_on"), "verified_by": rl.get("verified_by", []) or [],
                "expires_on": rl.get("expires_on"), "test_vectors": rl.get("test_vectors", []) or [],
            })
    return rows
PYEOF

# =================== core/rule_engine.py  (REWRITE: real-op set, expiry, provenance, outcome-branch, lazy catalog) ===================
cat > core/rule_engine.py <<'PYEOF'
"""
Haq Setu - Rule engine. Evaluates facts against the catalog. Catalog source is LAZY:
the REAL rulepack YAML if discoverable+parseable, else the auditable SEED catalog with
CATALOG_IS_PROVISIONAL=True (loud, never silent). Contract match_fn(facts)->
{confidence, schemes, trace, routed_verifies, provisional} is UNCHANGED so process_voice
and village are untouched; the extra keys are additive. NEVER asserts a scheme outside the
catalog; NEVER fills a missing fact; a LAPSED rule (expires_on < today) is never acted on.
NOTE (honest inference): your `max(matched_outcomes, key=PRIORITY)` caution order isn't in
the dump, so among-matched we use the conservative include->verify->needs_official_decision
ranking below and FLAG it; everything else is read from your data.
"""
from datetime import date
from rulepack import loader as _ld
from rulepack.catalog import SCHEMES as _SEED

_OPS = {"eq": lambda a,b:a==b, "ne": lambda a,b:a!=b, "gt": lambda a,b:a>b,
        "gte": lambda a,b:a>=b, "lt": lambda a,b:a<b, "lte": lambda a,b:a<=b,
        "in": lambda a,b:(a in b) if isinstance(b,(list,tuple,set)) else False,
        "not_in": lambda a,b:(a not in b) if isinstance(b,(list,tuple,set)) else True,
        "truthy": lambda a,b:bool(a), "falsy": lambda a,b:not bool(a),
        # aliases so the SEED catalog (>=,<,==) and your YAML (gte,lt,eq) both flow:
        ">=": lambda a,b:a>=b, "<=": lambda a,b:a<=b, ">": lambda a,b:a>b, "<": lambda a,b:a<b,
        "==": lambda a,b:a==b, "!=": lambda a,b:a!=b}
_CAUTION = {"include": 0, "verify": 1, "needs_official_decision": 2}   # conservative; see NOTE

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
            outcome = min((_CAUTION.get(r.get("outcome","include"),2) for r,_ in matched),
                          default=2)
            oname = {0:"include",1:"verify",2:"needs_official_decision"}[outcome]
            for r,p in matched:
                trace.append({"scheme": sid, "scheme_name": r.get("description","") or sid,
                              "rule_id": r.get("rule_id"), "outcome": oname, "clauses": p,
                              "docs": r.get("documents",[]), "benefit": r.get("desk",""),
                              "verified_by": r.get("verified_by",[]), "source": r.get("source",{}),
                              "expires_on": r.get("expires_on"), "lapsed": lapsed})
            if oname=="include": includes.append(sid)
            elif oname=="verify": verifies.append(sid)
        else:
            miss_facts = sorted({pr["fact"] for (_,st,ps) in evs if st in ("uncertain","lapsed") for pr in ps if pr.get("note")=="not provided"})
            trace.append({"scheme": sid, "scheme_name": sid, "rule_id": None,
                          "outcome": "needs_official_decision", "clauses": [],
                          "docs": [], "benefit": None, "verified_by": [], "source": {},
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
    """Mirror your /api/match contract {action,facts,civic,can,likely,case,speak}.
    can=confident includes; likely=uncertain-but-partial schemes; civic=verify-routed.
    ABSTAIN when nothing confident -- exactly your intake_abstain path."""
    res = match_fn(facts)
    can = res["schemes"]; civic = res["routed_verifies"]
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

# =================== core/facts.py  (REWRITE: + grounded loss%/days/insurance tri-state, never-invent) ===================
cat > core/facts.py <<'PYEOF'
"""
Haq Setu - Fact extractor. Parses Hinglish/Hindi/English into a normalized facts dict.
NEVER invents: a field appears only when a pattern matches; absent => missing => abstain.
Grounded additions from your visible extractor: crop loss %, days-since-work-demand, and
insurance TRI-STATE with the neg-first guard (your comment: "not insured" contains
"insured", so check negative before positive). Age requires a cue word; income parses
magnitude words and stops at the first non-magnitude token.
"""
import re
_AGE = re.compile(r"\b(\d{2,3})\b\s*(?:saal|sal|years?|year|umar|age|barsa|varsh|वर्ष|साल|उम्र)", re.I)
_INCOME = re.compile(r"(?:income|aamdani|aamdni|amdani|kamai|earning|आमदननी|आय|कमाई)\b[\s,:]*(.{0,40})", re.I)
_LOSS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|pratishat|प्रतिशत)", re.I)
_LOSS2 = re.compile(r"(?:loss|damage|kharab|nuksan|nuqsan|नुकसान)\s*(?:of|is|was|hai)?\s*(\d+(?:\.\d+)?)", re.I)
_DAYS = re.compile(r"(\d+)\s*(?:days?|din|दिन)", re.I)
_WEEKS = re.compile(r"(\d+)\s*(?:weeks?|hafte|सप्ताह|हफ्तो)", re.I)
_INS_POS = ["insured","beema","bima","pmfby","बीमा","भरसा"]
_INS_NEG = ["not insured","uninsured","nahi","nhi","not beema","no beema","नहीं","ना"]
_MULT = {"hazaar":1000,"hazar":1000,"thousand":1000,"k":1000,"हजार":1000,
         "lakh":100000,"lac":100000,"लाख":100000,"crore":10000000,"karod":10000000,"करोड़":10000000}
_VOCAB = {
 "is_widow":(r"widow|vidhwa|vidawa|parinemta|parinamita|विधवा",None),
 "is_woman":(r"\bwoman\b|\bfemale\b|mahila|aurat|stree|स्त्री|महिला",r"\bman\b|\bmale\b|purush|aadmi"),
 "is_disabled":(r"disab|viklang|diggaj|विकलांग|दिव्यांग",None),
 "has_pucca_house":(r"pucca|pakka|pakke|concrete|cement|पक्का",r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी"),
 "is_farmer":(r"farmer|kisan|krishak|khedut|किसान|खेती|farm",None),
 "has_lpg":(r"lpg|gas connection|गैस",None),
 "is_sc_st":(r"\bsc\b|\bst\b|scheduled caste|scheduled tribe|dalit|आदिवासी|अनुसूचित",None),
 "is_bpl":(r"bpl|below poverty|garib|गरीब|बीपीएल|yellow card",None),
 "has_school_child":(r"child|bachcha|baccha|beta|beti|student|school|पढ़ता|विद्यालय|स्कूल",None),
 "has_land":(r"land|zameen|jameen|khet|plot|भूमि|जमीन|खेत",None),
 "is_pregnant_or_lactating":(r"pregnant|garbhavati|feeding|sthan|दूध पिला|गर्भवती",None),
 "is_student":(r"student|padhta|padhti|chhatra|chatra|विद्यार्थी|पढ़ता",None),
 "is_girl_child":(r"girl child|beti|kanya|bachi|बेटी|कन्या",None),
 "is_single_woman":(r"single woman|akeli mahila|unmarried woman|अकेली",None),
}
def _collapse(s): return re.sub(r"(?<=\d)[, ](?=\d)", "", s)
def _parse_amount(chunk):
    c=_collapse(chunk or ""); toks=re.findall(r"\d+|[^\d\s]+", c); total=0; i=0; n=len(toks); started=False
    while i<n:
        t=toks[i]
        if t.isdigit():
            cur=int(t); started=True; i+=1
            if i<n and toks[i].lower() in _MULT: total+=cur*_MULT[toks[i].lower()]; continue
            else: total+=cur; break
        else: break
    return total if (started and total>0) else None
def _insured(low):
    for kw in _INS_NEG:
        if kw in low: return False          # neg-first: "not insured" contains "insured"
    for kw in _INS_POS:
        if kw in low: return True
    return None
def extract(raw_text, lang=None):
    t=(raw_text or "").strip(); low=t.lower(); f={}
    if not t: return f
    m=_AGE.search(low)
    if m and 18<=int(m.group(1))<=120: f["age"]=int(m.group(1))
    im=_INCOME.search(low) or _INCOME.search(t)
    if im:
        amt=_parse_amount(im.group(1))
        if amt is not None: f["annual_income_inr"]=amt
    lm=_LOSS.search(low) or _LOSS2.search(low)
    if lm:
        try:
            v=float(lm.group(1))
            if 0<=v<=100: f["crop_loss_percentage"]=v
        except ValueError: pass
    dm=_DAYS.search(low)
    if dm: f["days_since_work_demand"]=int(dm.group(1))
    else:
        wm=_WEEKS.search(low)
        if wm: f["days_since_work_demand"]=int(wm.group(1))*7
    ins=_insured(low)
    if ins is not None: f["is_insured"]=ins
    for fact,(pos,neg) in _VOCAB.items():
        if re.search(pos,low) or re.search(pos,t):
            if neg and re.search(neg,low): continue
            f[fact]=True
    if "has_pucca_house" not in f and re.search(r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी",low):
        f["has_pucca_house"]=False
    if f.get("is_woman") and "has_lpg" not in f and not re.search(r"lpg|gas",low):
        f["has_lpg"]=False
    return f
PYEOF

# =================== core/run_rulepack_bind.py  (NEW proof: every assert grounded in YOUR bytes) ===================
cat > core/run_rulepack_bind.py <<'PYEOF'
"""Bind-the-real-rulepack proof. Run: python -m core.run_rulepack_bind.
Every assertion is grounded in YAML/contract I can SEE in the upload -- not assumed.
Feeds your real schema-as-dicts to rows_from_packs + evaluate, runs your test_vectors as
abstention fixtures, proves expiry + provenance + outcome-branch + grounded extractor
additions + the loud provisional fallback + the /api/match contract mirror."""
import sys, os, tempfile
from rulepack import loader as ld
from core import rule_engine as eng, facts as fx
FAIL=[]
def chk(n,c,e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)

# --- your REAL YAML blocks, transcribed verbatim from the upload (schema-as-dicts) ---
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
  "outcome":"verify","documents":[],"desk":"panchayat","clock_hours":24,"contact":"Grievance Officer",
  "source":{"doc":"Civic Guidelines","clause":"SLA","url":"https://india.gov.in/"},
  "verified_on":"2026-10-09","verified_by":["System","Auto-Verifier"],"expires_on":"2027-10-09",
  "test_vectors":[{"input":{},"expect":"needs_official_decision"}]}]}

def part1():
    print("\n##### PART 1 : faithful translation of YOUR schema (rows_from_packs) #####")
    rows = ld.rows_from_packs([WIDOW, POSTMAT, POSHAN, ROAD])
    by = {r["rule_id"]: r for r in rows}
    w = by["widow_pension_001"]
    chk("widow row scheme_id/rule_id carried", w["scheme_id"]=="widow_pension" and w["rule_id"]=="widow_pension_001")
    chk("widow when(AND)->requires, op eq, value True", w["requires"]==[{"fact":"is_widow","op":"eq","value":True}], str(w["requires"]))
    chk("widow outcome=include carried", w["outcome"]=="include")
    chk("widow expires_on carried", w["expires_on"]=="2027-10-09", str(w["expires_on"]))
    chk("widow verified_by carried (provenance)", w["verified_by"]==["System","Auto-Verifier"], str(w["verified_by"]))
    chk("widow source doc/clause/url carried", w["source"]["doc"]=="Widow Pension Guidelines" and w["source"]["url"]=="https://india.gov.in/")
    chk("widow test_vector carried", w["test_vectors"]==[{"input":{},"expect":"needs_official_decision"}])
    pm = by["post_matric_001"]
    chk("post_matric AND of TWO when -> two requires", len(pm["requires"])==2 and pm["requires"][1]["fact"]=="class_gte", str(pm["requires"]))
    rd = by["road_repair_001"]
    chk("route outcome=verify + clock_hours + contact + desk carried", rd["outcome"]=="verify" and rd["clock_hours"]==24 and rd["contact"]=="Grievance Officer" and rd["desk"]=="panchayat", str({k:rd[k] for k in('outcome','clock_hours','contact','desk')}))

def part2():
    print("\n##### PART 2 : engine honors YOUR semantics (include/verify/AND/never-guess) #####")
    rows = ld.rows_from_packs([WIDOW, POSTMAT, POSHAN, ROAD])
    r1 = eng.evaluate(rows, {"is_widow":True}, today="2026-10-21")
    chk("is_widow True -> widow_pension INCLUDED", "widow_pension" in r1["schemes"], str(r1["schemes"]))
    chk("included trace carries provenance verified_by", any(t.get("verified_by")==["System","Auto-Verifier"] for t in r1["trace"] if t["scheme"]=="widow_pension"))
    chk("included trace carries source url (SDM sees authority)", any((t.get("source") or {}).get("url")=="https://india.gov.in/" for t in r1["trace"] if t["scheme"]=="widow_pension"))
    r2 = eng.evaluate(rows, {"is_student":True,"class_gte":11}, today="2026-10-21")
    chk("post_matric BOTH when met -> included", "post_matric" in r2["schemes"], str(r2["schemes"]))
    r3 = eng.evaluate(rows, {"is_student":True}, today="2026-10-21")  # missing class_gte
    chk("post_matric PARTIAL facts -> NOT included (never-guess)", "post_matric" not in r3["schemes"], str(r3["schemes"]))
    chk("partial-facts trace lists the missing fact", any("class_gte" in (t.get("uncertain_facts") or []) for t in r3["trace"] if t["scheme"]=="post_matric"), str([t.get("uncertain_facts") for t in r3["trace"] if t["scheme"]=="post_matric"]))
    r4 = eng.evaluate(rows, {"road_damaged":True}, today="2026-10-21")
    chk("road_damaged -> VERIFY-routed, NOT an entitlement include", "road_repair" in r4["routed_verifies"] and "road_repair" not in r4["schemes"], str({k:r4[k] for k in('schemes','routed_verifies')}))

def part3():
    print("\n##### PART 3 : YOUR test_vectors enforce never-deny (empty input -> abstain) #####")
    rows = ld.rows_from_packs([WIDOW, POSTMAT, POSHAN, ROAD])
    abstained = True
    for r in rows:
        for tv in r["test_vectors"]:
            res = eng.evaluate([r], tv["input"], today="2026-10-21")
            want = tv["expect"]
            got = "needs_official_decision" if (want=="needs_official_decision" and not res["schemes"] and not res["routed_verifies"]) else "OTHER"
            if got != want: abstained = False
            chk(f"vector {r['rule_id']} input={tv['input']} -> {want}", got==want, f"got {got}; schemes={res['schemes']}")
    chk("ALL your test_vectors abstain on empty input (never-deny, YOUR data)", abstained)

def part4():
    print("\n##### PART 4 : expiry + provenance (don't act on lapsed authority) #####")
    rows = ld.rows_from_packs([WIDOW])
    rr = [dict(rows[0], expires_on="2025-01-01")]   # lapsed relative to today
    rl = eng.evaluate(rr, {"is_widow":True}, today="2026-10-21")
    chk("LAPSED rule -> NOT included (expires_on < today)", "widow_pension" not in rl["schemes"], str(rl["schemes"]))
    chk("lapsed trace flags lapsed=True + note", any(t.get("lapsed") and "lapsed" in (t.get("note") or "") for t in rl["trace"] if t["scheme"]=="widow_pension"), str([t.get('note') for t in rl['trace']]))
    rn = eng.evaluate(rows, {"is_widow":True}, today="2026-10-21")
    chk("NON-lapsed rule (2027-10-09) -> included", "widow_pension" in rn["schemes"])

def part5():
    print("\n##### PART 5 : grounded extractor additions (your visible regexes) #####")
    f1 = fx.extract("meri fusal 40 percent kharab ho gayi")
    chk("loss% 40 percent -> crop_loss_percentage=40.0", f1.get("crop_loss_percentage")==40.0, str(f1))
    f2 = fx.extract("15 din se kaam nahi mila")
    chk("15 din -> days_since_work_demand=15", f2.get("days_since_work_demand")==15, str(f2))
    f3 = fx.extract("2 hafte se kaam ka intezaar")
    chk("2 hafte -> days_since_work_demand=14", f3.get("days_since_work_demand")==14, str(f3))
    f4 = fx.extract("I am not insured under PMFBY")
    chk("neg-first: 'not insured' -> is_insured=False (NOT True)", f4.get("is_insured") is False, str(f4))
    f5 = fx.extract("maine PMFBY ke tahat beema karwaya tha")
    chk("positive: beema karwaya -> is_insured=True", f5.get("is_insured") is True, str(f5))
    f6 = fx.extract("aaj mausam kaisa hai")
    chk("off-topic -> no fabricated facts (empty-ish)", "crop_loss_percentage" not in f6 and "days_since_work_demand" not in f6 and "is_insured" not in f6, str(f6))

def part6():
    print("\n##### PART 6 : loud provisional fallback + /api/match contract mirror #####")
    chk("load_rulepack_dir('/nonexistent') -> None (no silent parse)", ld.load_rulepack_dir("/nonexistent") is None)
    res = eng.match_fn({"is_widow":True})           # sandbox: no real dir -> seed, provisional
    chk("no real dir -> engine still serves seed catalog", "nsap_widow" in res["schemes"] or "widow_pension" in res["schemes"], str(res["schemes"]))
    chk("no real dir -> CATALOG_IS_PROVISIONAL True (loud, not silent)", res["provisional"] is True, str(res["provisional"]))
    a0 = eng.to_api_match_shape({})
    chk("contract mirror: empty facts -> action ABSTAIN (your intake_abstain)", a0["action"]=="ABSTAIN" and a0["can"]==[] and a0["civic"]==[] and a0["speak"], str(a0["action"]))
    a1 = eng.to_api_match_shape({"is_widow":True})
    chk("contract mirror: is_widow -> can includes a widow scheme", any("widow" in s for s in a1["can"]), str(a1["can"]))
    a2 = eng.to_api_match_shape({"road_damaged":True})
    chk("contract mirror: road_damaged -> civic routed (verify), not can", a2["civic"] and not a2["can"], str({k:a2[k] for k in('action','can','civic')}))
    # optional: if PyYAML present, round-trip your REAL widow YAML text -> same row as dict path
    try:
        import yaml
        ytxt = ("scheme: widow_pension\nstate: haryana\nrules:\n- id: widow_pension_001\n"
                "  description: \"Widow Pension eligibility.\"\n  when:\n  - field: is_widow\n    op: eq\n    value: true\n"
                "  outcome: include\n  documents: ['aadhaar', 'death_cert']\n  desk: bdo\n"
                "  source: {doc: \"Widow Pension Guidelines\", clause: \"Eligibility\", url: \"https://india.gov.in/\"}\n"
                "  verified_on: 2026-10-09\n  verified_by: [System, Auto-Verifier]\n  expires_on: 2027-10-09\n"
                "  test_vectors:\n  - input: {}\n    expect: needs_official_decision\n")
        pk = yaml.safe_load(ytxt); rw = ld.rows_from_packs([pk])[0]
        chk("PyYAML round-trip of YOUR real YAML == dict path (parse is faithful)",
            rw["requires"]==[{"fact":"is_widow","op":"eq","value":True}] and rw["expires_on"]=="2027-10-09" and rw["verified_by"]==["System","Auto-Verifier"], str(rw["requires"]))
    except ImportError:
        print("  [note] PyYAML absent -> YAML->dict round-trip skipped (loader would go provisional on a real dir); dict-path proofs above stand.")

def main():
    print("##### BIND THE REAL RULEPACK (data + contract harvested; legacy chain NOT resurrected) #####")
    part1(); part2(); part3(); part4(); part5(); part6()
    print("\n[RESULT]", "RULEPACK BOUND" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__=="__main__": main()
PYEOF

echo "########## SYNTAX / IMPORT SMOKE ##########"
python -m py_compile rulepack/loader.py core/rule_engine.py core/facts.py core/run_rulepack_bind.py \
  && echo "  [OK] 4 files compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import rulepack.loader, core.rule_engine, core.facts, core.run_rulepack_bind, village.server; print('  [OK] imports resolve (loader+engine+facts+bind+village)')" || exit 1

echo "########## GATES (bind proof + unregression of the brain surface) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/rpb_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_BLOCK_DB="$d/block.db" \
      HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 HAQ_BLOCK_PORT=8100 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 26
  local rc="${PIPESTATUS[0]}"; printf '>>> %-12s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "rulepack-bind" python -m core.run_rulepack_bind
gate "brain-audit"  python -m core.run_brain_audit
gate "village"      python -m core.run_village_demo
gate "pillar1"      python -m core.run_pillar1_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "RULEPACK BOUND :: your real YAML schema evaluated faithfully (include/verify/AND/expiry/provenance), your test_vectors now enforce never-deny in CI, /api/match contract mirrored, seed fallback LOUD+provisional, brain surface unregressed" || echo "SOME GATE RED :: see exit!=0 above"
