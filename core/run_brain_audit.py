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
