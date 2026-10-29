"""Pillar 1 bus-side proof (reference matcher = stand-in for engine.rules.match).
Run: python -m core.run_pillar1_demo   (sandboxed via env by the caller)"""
import os, sys, json, time
from core import event_bus, entitlement as ent, sla_clock as clock
from ledger import chain as _chain
from sdm import view_model

FAIL = []
def chk(n, c, e=""):
    print(f"  [{'OK' if c else 'FAIL'}] {n}{(' :: '+e) if e else ''}")
    if not c: FAIL.append(n)

def main():
    event_bus.init()
    print("##### PILLAR 1 BUS-SIDE (reference matcher; bind engine.rules.match to go live) #####")
    # A) confident match -> matched + petition issued (clock starts); PII to vault only
    a = ent.process_voice("mitra", {"age": 65, "is_widow": True, "has_pucca_house": False},
                          ent.reference_match_fn,
                          pii_fields={"name": "Lakshmi Bai", "phone": "9900112233"},
                          case_id="HS-P1-A")
    chk("A matched (3 schemes)", a["decision"] == "matched" and len(a["schemes"]) == 3, str(a.get("schemes")))
    seqs = [e["seq"] for e in a["events"]]
    chk("A emitted matched+petition", seqs == sorted(seqs) and len(seqs) == 2)
    blob = a["events"][0]["payload"].get("pii_ref")
    chk("A ledger payload has NO raw PII", "Lakshmi" not in json.dumps(a["events"][0]["payload"]))
    chk("A proof_trace present", bool(a["events"][0]["payload"].get("proof_trace")))
    # B) ambiguous -> abstain (never deny)
    b = ent.process_voice("mitra", {"_ambiguous": True}, ent.reference_match_fn, case_id="HS-P1-B")
    chk("B abstained (not denied)", b["decision"] == "abstained", b.get("reason",""))
    # C) brain crash -> abstain (never deny)
    c = ent.process_voice("mitra", {"_boom": True, "age": 70}, ent.reference_match_fn, case_id="HS-P1-C")
    chk("C abstained on brain_error", c["decision"] == "abstained" and "brain_error" in c["reason"])
    # D) match then officer RESOLVES -> green, no breach
    d = ent.process_voice("mitra", {"age": 62}, ent.reference_match_fn, case_id="HS-P1-D")
    event_bus.emit("officer", "HS-P1-D", "petition_resolved", {"by": "panchayat_secretary"})
    # E) match then officer REJECTS WITH reason -> slate closed_rejected (honest terminal)
    e = ent.process_voice("mitra", {"age": 61, "is_widow": True}, ent.reference_match_fn, case_id="HS-P1-E")
    event_bus.emit("officer", "HS-P1-E", "official_rejection", {"reason_code": "ineligible_age_doc_missing"})
    # F) match then IGNORED -> will breach on the clock
    f = ent.process_voice("mitra", {"has_pucca_house": False}, ent.reference_match_fn, case_id="HS-P1-F")
    base = len(_chain.get_chain())
    print(f"  [info] seeded 6 voice cases; chain_len={base}")

    # ---- the ONE clock expires the ignored receipt (F) like any case; D/E closed, B/C no clock ----
    fut = time.time() + 100 * 3600
    tr = clock.tick(now=fut)
    pkinds = [x["payload"]["kind"] for x in tr["emitted"]]
    chk("clock emitted a petition breach (for ignored F)", "petition" in pkinds, str(pkinds))
    chk("resolved D did NOT breach", "HS-P1-D" not in [x["case_id"] for x in tr["emitted"] if x["payload"]["kind"]=="petition"])
    chk("rejected E did NOT breach", "HS-P1-E" not in [x["case_id"] for x in tr["emitted"] if x["payload"]["kind"]=="petition"])
    chk("abstained B/C produced NO petition clock",
        not any(x["case_id"] in ("HS-P1-B","HS-P1-C") for x in tr["emitted"]))

    st = clock.status()
    chk("status exposes petition buckets", all(k in st for k in
        ("open_petitions","resolved_petitions","rejected_petitions","breached_petitions","abstained_petitions")))
    chk("F is breached petition", "HS-P1-F" in st["breached_petitions"])
    chk("D resolved / E rejected / B,C abstained accounted",
        "HS-P1-D" in st["resolved_petitions"] and "HS-P1-E" in st["rejected_petitions"]
        and {x["case_id"] for x in st["abstained_petitions"]} == {"HS-P1-B","HS-P1-C"})

    # ---- SDM board renders the 4th lane with correct colors ----
    v = view_model.build(now=fut)
    pc = {p["case_id"]: p["color"] for p in v["petitions"]}
    chk("board F red (breached petition)", pc.get("HS-P1-F") == "red", str(pc))
    chk("board D green (resolved)", pc.get("HS-P1-D") == "green")
    chk("board E slate (closed_rejected)", pc.get("HS-P1-E") == "slate")
    chk("board B,C amber (abstained_human)", pc.get("HS-P1-B") == "amber" and pc.get("HS-P1-C") == "amber")
    chk("counts now include petition colors", v["counts"]["red"] >= 1 and v["counts"]["amber"] >= 2)
    ok,_,why = event_bus.verify(); chk("chain verifies after all pillars incl petitions", ok, why)
    print(f"  [info] final chain_len={len(_chain.get_chain())}  lanes=civic/commitments/sabhas/petitions")
    print("\n[RESULT]", "PILLAR 1 BUS-SIDE GREEN" if not FAIL else f"FAILED: {FAIL}")
    sys.exit(0 if not FAIL else 1)

if __name__ == "__main__":
    main()
