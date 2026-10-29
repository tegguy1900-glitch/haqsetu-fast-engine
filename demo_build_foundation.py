"""Sandboxed proof of the bedrock. Run via the wrapper below."""
import json
from core import event_bus
from ledger import chain as _chain, pii_store as _pii

def main():
    event_bus.init()
    print("[OK] ledger initialized + genesis verified")

    e1 = event_bus.emit("mitra", "HS-DEMO-00001", "entitlement_matched",
        {"schemes": ["old_age_pension_nsap", "pmay"], "confidence": 0.97})
    print(f"[OK] appended seq={e1['seq']} type={e1['event_type']}")

    try:
        event_bus.emit("mitra", "HS-DEMO-00002", "entitlement_matched",
            {"name": "Ramesh Kumar", "phone": "9876543210"})
        print("[FAIL] PII leaked into ledger!")
    except _chain.PiiLeakError as ex:
        print(f"[OK] PII guard blocked -> {ex}")

    e3 = event_bus.emit("mitra", "HS-DEMO-00003", "civic_intake",
        {"category": "handpump", "ward": 4, "photo_hash": "abc123", "gps": [28.6, 77.2]},
        pii_fields={"name": "Sita Devi", "phone": "9999888877"})
    blob = e3["payload"]["pii_ref"]
    assert "name" not in json.dumps(e3["payload"])
    print(f"[OK] civic_intake stored; PII in vault as {blob[:8]}..., ledger clean")
    print(f"     vault round-trip -> {_pii.get_pii(blob)['name']}")

    event_bus.emit("sarpanch", "HS-DEMO-00003", "sabha_signed",
        {"fund_allocated": 50000, "deadline": "2026-11-05", "response": "sanmanjit"})
    event_bus.emit("system", "HS-DEMO-00003", "sla_breach",
        {"hours_overdue": 6, "escalated_to": "block_engineer"})

    ok, bad, why = event_bus.verify()
    print(f"[OK] full chain verify -> ok={ok} ({why})")

    rows = _chain.get_chain()
    rows[1]["payload"]["confidence"] = 0.01
    with open(_chain.CHAIN_FILE, "w") as f:
        for r in rows: f.write(json.dumps(r, sort_keys=True) + "\n")
    ok, bad, why = event_bus.verify()
    print(f"[OK] tamper detected at seq={bad} -> {why}" if not ok
          else "[FAIL] tamper NOT detected")

    n = _pii.erase_pii("HS-DEMO-00003")
    print(f"[OK] erased {n} PII blob(s) on closure; ledger events remain")

if __name__ == "__main__":
    main()
