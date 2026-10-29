#!/usr/bin/env bash
# Haq Setu pillar-1c: close red-2. The real engine's proof_trace used key "name" (a SCHEME
# name) which tripped the ledger's PII key-blacklist on the WRITE path only. Rename to
# "scheme_name" (guard stays absolute) and make brain-audit scan the EMITTED payload through
# the real guard so this bug class can never hide on the read/write asymmetry again.
# Whole-file rewrites of exactly 2 files; village/server.py + core/facts.py untouched.
cd "$(dirname "$0")" 2>/dev/null || true
source venv/bin/activate 2>/dev/null || true

# =================== core/rule_engine.py  (name -> scheme_name in the trace builder) ===================
cat > core/rule_engine.py <<'PYEOF'
"""
Haq Setu - Rule engine (Pillar 1 layer 2). Evaluates facts vs rulepack/catalog.py.
Contract: match_fn(facts) -> {confidence, schemes, trace}. NEVER asserts a scheme not
in the catalog; NEVER fills a missing fact. If any required fact of every candidate is
missing => uncertain => low confidence => the bus-side process_voice ABSTAINS (routes to
a human), honoring never-deny. A confident match-set => high confidence + proof-trace.
NOTE: the trace uses key "scheme_name" (NOT "name") so the ledger PII key-blacklist
(which forbids any key literally called "name", to stop a citizen's name being a key)
never false-positives on a scheme's display label. The guard stays absolute.
"""
from rulepack.catalog import SCHEMES

_OPS={">=":lambda a,b:a>=b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,"<":lambda a,b:a<b,
      "==":lambda a,b:a==b,"!=":lambda a,b:a!=b,
      "in":lambda a,b:a in b,"not_in":lambda a,b:a not in b,
      "truthy":lambda a,b:bool(a),"falsy":lambda a,b:not bool(a)}

def _clause(c, facts):
    """returns (state, proof): state in {sat, fail, missing}."""
    fact=c["fact"]; op=c["op"]; val=c.get("value")
    if fact not in facts: return "missing", {"fact":fact,"note":"not provided"}
    got=facts[fact]
    fn=_OPS.get(op)
    if fn is None: return "missing", {"fact":fact,"note":f"unknown op {op}"}
    try: ok=bool(fn(got,val))
    except Exception: return "missing", {"fact":fact,"note":"type mismatch"}
    return ("sat" if ok else "fail"), {"fact":fact,"op":op,"value":val,"observed":got,"result":ok}

def _eval(scheme, facts):
    sat=[]; miss=[]; fail=[]
    for c in scheme.get("requires",[]):
        st,pr=_clause(c,facts)
        (sat if st=="sat" else miss if st=="missing" else fail).append(pr)
    # alt = any-of disjunction (e.g. income OR SC/ST OR BPL)
    alt_ok=None
    if scheme.get("alt"):
        alt_states=[_clause(c,facts)[0] for c in scheme["alt"]]
        alt_ok = any(s=="sat" for s in alt_states)
        alt_missing = all(s=="missing" for s in alt_states)
    else:
        alt_ok=True; alt_missing=False
    if fail: return "ineligible", sat+fail          # a required clause clearly false
    if miss and not (alt_ok and not alt_missing):   # required missing AND alt can't rescue
        return "uncertain", sat+miss
    if not sat and not (scheme.get("alt") and alt_ok):
        return "uncertain", sat+miss
    return "match", sat

def match_fn(facts):
    facts=facts or {}
    confident=[]; trace=[]; any_uncertain=False
    for s in SCHEMES:
        state,proofs=_eval(s,facts)
        if state=="match":
            confident.append(s["id"])
            trace.append({"scheme":s["id"],"scheme_name":s["name"],"clauses":proofs,
                          "docs":s.get("docs",[]),"benefit":s.get("benefit")})
        elif state=="uncertain":
            any_uncertain=True
    if confident:
        conf=round(min(0.97, 0.6+0.12*len(confident)),2)
        return {"confidence":conf,"schemes":confident,"trace":trace}
    # no confident match => abstain (never deny). trace explains the gap honestly.
    return {"confidence":0.0,"schemes":[],
            "trace":[{"note":"no scheme confidently matched",
                      "uncertain_facts":sorted({p["fact"] for t in [ _eval(s,facts)[1] for s in SCHEMES] for p in t if p.get("note")=="not provided"}) if any_uncertain else [],
                      "guidance":"a human officer should review; the system did not guess"}]}
PYEOF

# =================== core/run_brain_audit.py  (+ write-path guard scan: closes the asymmetry) ===================
cat > core/run_brain_audit.py <<'PYEOF'
"""Pillar-1 brain audit. Run: python -m core.run_brain_audit. Asserts the REAL engine
never fabricates a fact/scheme and abstains on gaps, AND that the EXACT emitted payload
passes the ledger PII guard (so a forbidden key can never hide on the read/write
asymmetry that produced the 'name' crash). Catalog VALUES are seed data to verify; this
proves the MACHINE + the write contract, not the numbers."""
import sys
from core import facts, rule_engine as eng
from rulepack.catalog import SCHEMES
from ledger.chain import _scan_pii, PiiLeakError   # the REAL guard the ledger runs on write
FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)

def _scan_ok(payload):
    """Return (True,'') if the payload survives the ledger PII guard, else (False, msg)."""
    try:
        _scan_pii(payload); return True, ""
    except PiiLeakError as ex:
        return False, str(ex)

def main():
    print("##### PILLAR-1 BRAIN AUDIT (real extractor + declarative engine + write-guard) #####")
    # 1) extractor: real Hinglish -> facts, magnitude words parsed
    f = facts.extract("Main 68 saal ki vidhwa hoon, mera kacha ghar hai, saal ki aamdani 80 hazaar hai")
    chk("extract age=68 (cue 'saal')", f.get("age") == 68, str(f))
    chk("extract is_widow", f.get("is_widow") is True)
    chk("extract has_pucca_house=False (kacha)", f.get("has_pucca_house") is False)
    chk("extract annual_income=80000 (80 hazaar)", f.get("annual_income") == 80000, str(f.get("annual_income")))
    # 1b) magnitude + Indian comma + compound + no-overread + negation-guard
    fc = facts.extract("mere ghar ki aamdani 1,20,000 rupaye hai")
    chk("extract Indian comma 1,20,000=120000", fc.get("annual_income") == 120000, str(fc.get("annual_income")))
    chk("extract comma did NOT invent age=20", "age" not in fc, str(fc))
    fk = facts.extract("sal ki kamai 2 lakh 50 hazaar hai")
    chk("extract compound 2 lakh 50 hazaar=250000", fk.get("annual_income") == 250000, str(fk.get("annual_income")))
    fo = facts.extract("aamdani 80 hazaar hai aur 2 bachche hain")
    chk("extract no-overread: stops at 'hai', ignores '2 bachche'", fo.get("annual_income") == 80000, str(fo.get("annual_income")))
    fn = facts.extract("income nahi hai, 2 bachche")
    chk("extract does NOT grab stray number after negation", "annual_income" not in fn, str(fn))
    # 2) NO FABRICATION: no age number => no age (didn't guess from 'budhi')
    f2 = facts.extract("bahut budhi hoon, garib hoon")
    chk("no-fabrication: 'budhi' does NOT invent an age", "age" not in f2, str(f2))
    chk("no-fabrication: garib => is_bpl True", f2.get("is_bpl") is True, str(f2))
    # 3) engine: confident match set + proof_trace, high conf
    r = eng.match_fn(f)
    chk("engine confident (conf>0.6)", r["confidence"] > 0.6, str(r["confidence"]))
    chk("engine matched nsap_old_age", "nsap_old_age" in r["schemes"], str(r["schemes"]))
    chk("engine matched nsap_widow", "nsap_widow" in r["schemes"])
    chk("engine matched pmay_gramin (kacha)", "pmay_gramin" in r["schemes"])
    chk("engine matched ayushman (income 80000<1.8L)", "ayushman_bharat" in r["schemes"])
    chk("engine proof_trace present", bool(r["trace"]) and all("clauses" in t for t in r["trace"]))
    chk("trace uses scheme_name (NOT forbidden key 'name')",
        all("scheme_name" in t and "name" not in t for t in r["trace"]),
        str(list(r["trace"][0].keys())))
    # 3b) INTEGRATION: extractor -> engine on the real text yields the expected superset
    chk("integration: real-text facts -> 6 flagship schemes",
        {"nsap_old_age","nsap_widow","pmay_gramin","ayushman_bharat","ration_pds","indira_awas"} <= set(r["schemes"]),
        str(r["schemes"]))
    # 3c) WRITE-GUARD: the EXACT payload process_voice emits must survive the ledger guard
    matched_payload = {"schemes": r["schemes"], "confidence": r["confidence"],
                       "proof_trace": r["trace"], "facts_keys": sorted(f.keys())}
    ok_scan, err = _scan_ok(matched_payload)
    chk("matched payload passes ledger PII guard (write-path)", ok_scan, err)
    # 4) engine ABSTAINS on missing facts (never deny, never guess)
    r_empty = eng.match_fn({})
    chk("engine abstains on empty facts (conf~0)", r_empty["confidence"] < 0.3 and r_empty["schemes"] == [], str(r_empty["confidence"]))
    chk("abstain trace explains gap", any("note" in t for t in r_empty["trace"]), str(r_empty["trace"])[:80])
    abstain_payload = {"reason": "low_confidence_or_unsure", "confidence": r_empty["confidence"],
                       "facts_keys": []}
    ok_scan2, err2 = _scan_ok(abstain_payload)
    chk("abstain payload passes ledger PII guard (write-path)", ok_scan2, err2)
    # 5) engine never asserts a scheme outside the catalog
    ids = {s["id"] for s in SCHEMES}
    r2 = eng.match_fn({"age":70,"is_widow":True,"has_pucca_house":False,"is_disabled":True,"is_farmer":True})
    chk("engine only returns catalog ids", all(sid in ids for sid in r2["schemes"]), str(r2["schemes"]))
    chk("engine picked up disability+pm_kisan too", {"nsap_disability","pm_kisan"} <= set(r2["schemes"]), str(r2["schemes"]))
    # 6) alt-disjunction: SC/ST rescues ayushman even without an income figure
    r3 = eng.match_fn({"is_sc_st":True})
    chk("alt disjunction: is_sc_st => ayushman eligible", "ayushman_bharat" in r3["schemes"], str(r3["schemes"]))
    print("\n[RESULT]", "BRAIN AUDIT GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)
if __name__ == "__main__": main()
PYEOF

echo "########## SYNTAX / IMPORT SMOKE ##########"
python -m py_compile core/rule_engine.py core/run_brain_audit.py \
  && echo "  [OK] 2 rewritten files compile" || { echo "  [FAIL] compile"; exit 1; }
python -c "import core.rule_engine, core.run_brain_audit, village.server; print('  [OK] imports resolve (engine + audit + village)')" || exit 1

echo "########## GATES (tail 30) ##########"
GATES=""
gate(){ local L="$1"; shift; local d; d="$(mktemp -d /tmp/p1c_XXXXXX)"
  env HAQ_CHAIN="$d/chain.jsonl" HAQ_VAULT="$d/vault.jsonl" HAQ_KEYS="$d/keys" HAQ_VAULT_KEY="$d/pii.key" \
      SDM_DB="$d/sdm.db" HAQ_OUTBOX="$d/outbox.db" HAQ_SABHA_PORT=8020 HAQ_SDM_PORT=8110 HAQ_VILLAGE_PORT=8000 \
      HAQ_XP_DIR="$d" HAQ_DASH_DIR="$d" HAQ_B_DIR="$d/b" "$@" 2>&1 | tail -n 30
  local rc="${PIPESTATUS[0]}"; printf '>>> %-12s exit=%s\n' "$L" "$rc"; rm -rf "$d"; GATES="$GATES $L=$rc"; }
gate "brain-audit" python -m core.run_brain_audit
gate "village"     python -m core.run_village_demo
gate "pillar1"     python -m core.run_pillar1_demo
gate "launch"      python -m core.run_launcher_demo
echo "########## SUMMARY ##########"
echo "GATES:$GATES"
allok=1; for kv in $GATES; do [ "${kv#*=}" = "0" ] || allok=0; done
[ "$allok" = 1 ] && echo "PILLAR 1 CLOSED :: real engine write-path guarded; scheme_name rename fixed red-2; audit now catches this bug class on the write path" || echo "SEE RED GATE ABOVE"
