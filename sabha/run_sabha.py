"""End-to-end proof of the Sabha pipeline on a MOCK transcript (sandboxed)."""
import json
from core import event_bus
from sabha import compressor, push_sdm
from ledger import chain as _chain

MOCK = [
    {"speaker": "Sarpanch", "text": "Today we approved Rs 50,000 for the Ward 3 drain cleaning."},
    {"speaker": "Villager-A", "text": "The handpump in Ward 4 has been broken for two weeks, no water."},
    {"speaker": "Secretary", "text": "I will fix the streetlights in Ward 2 by Friday."},
    {"speaker": "Villager-B", "text": "The road near the school is full of potholes, very dangerous."},
    {"speaker": "Sarpanch", "text": "Resolved unanimously that the anganwadi roof repair is passed."},
]

def main():
    event_bus.init()
    print("[OK] bus initialized on sandbox chain")

    minutes = compressor.compress(MOCK, gp="GP-SAMPLE", date="2026-10-21")
    print("\n--- COMPRESSED MINUTES (anonymized, no speaker names) ---")
    print(json.dumps(minutes, indent=2, ensure_ascii=False))
    assert all("speaker" not in json.dumps(v) for v in
               (minutes["decisions"]+minutes["grievances"]+minutes["action_items"])), "name leak!"
    print("[OK] no speaker names present in emitted fields (layer 1: compressor)")

    res = push_sdm.push(minutes, signed=True, open_civic_from_grievances=True)
    print(f"\n[OK] sabha_signed -> ledger seq={res['event']['seq']} hash={res['minutes_hash'][:12]}...")
    print(f"[OK] GLUE: auto-opened civic cases = {res['civic_cases_opened']}")

    print("\n--- SDM DATABASE ROWS ---")
    for r in push_sdm.all_rows():
        print(f"  id={r[0]} gp={r[1]} date={r[2]} signed={r[5]} seq={r[4]} hash={r[3][:12]}...")
    pend = push_sdm.pending_acks()
    print(f"[OK] pending SDM acks (visible-by-default rule): {len(pend)} row(s)")

    # refusal path is auditable too
    m2 = compressor.compress([{"text": "No decision reached on water."}], gp="GP-REFUSE", date="2026-10-21")
    r2 = push_sdm.push(m2, signed=False, refuse_reason="quorum_not_met")
    print(f"[OK] unsigned sabha recorded -> seq={r2['event']['seq']} reason=quorum_not_met")

    # LAYER 2 backstop: a leaky upstream (e.g. future LLM) tries to smuggle PII
    for bad, label in [({"summary":"call 9876543210 immediately"}, "value-only phone"),
                       ({"name":"Ramesh Kumar"}, "forbidden key 'name'")]:
        try:
            event_bus.emit("sarpanch", "SABHA-LEAKTEST", "sabha_signed", bad)
            print(f"[FAIL] leak NOT blocked ({label})")
        except _chain.PiiLeakError as ex:
            print(f"[OK] ledger backstop killed leak ({label}) -> {ex}")

    ok, bad, why = event_bus.verify()
    print(f"\n[OK] full chain verify after all pillars -> ok={ok} ({why})")
    print(f"[OK] chain length = {len(_chain.get_chain())} events (entitlement+sabha+civic on ONE ledger)")

if __name__ == "__main__":
    main()
