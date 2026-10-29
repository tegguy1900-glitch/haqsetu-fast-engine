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
  "outcome":"verify","documents":[],"desk":"block_development_officer","clock_hours":72,"contact":"Grievance Officer",
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
    rd=by["road_repair_001"]; chk("route outcome=verify + clock_hours + contact + desk carried", rd["outcome"]=="verify" and rd["clock_hours"]==72 and rd["contact"]=="Grievance Officer" and rd["desk"]=="block_development_officer", str({k:rd[k] for k in('outcome','clock_hours','contact','desk')}))
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
