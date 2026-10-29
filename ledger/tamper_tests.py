from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from chain import Ledger
from verify import verify_chain


def write_events(ledger_path: Path, events: list[dict[str, Any]]) -> None:
    with open(ledger_path, "w", encoding="utf-8") as f:
        for event in events:
            json.dump(event, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")


def build_tmp_ledger(tmpdir: str):
    """
    Build a temporary ledger with several signed events.
    """
    ledger_path = Path(tmpdir) / "chain.jsonl"
    keys_dir = Path(tmpdir) / "keys"

    ledger = Ledger(ledger_path=ledger_path, keys_dir=keys_dir)

    ledger.ensure_initialized()

    for actor in ["facilitator", "csc_operator", "officer"]:
        ledger.generate_actor_keys(actor)

    ledger.append_event(
        actor="facilitator",
        role="facilitator",
        case_id="case-101",
        event_type="case_opened",
        data={"route": "crop_loss", "status": "opened"},
    )

    ledger.append_event(
        actor="facilitator",
        role="facilitator",
        case_id="case-101",
        event_type="documents_checked",
        data={
            "documents_checked": ["land_record", "crop_loss_photo"],
            "status": "documents_checked",
        },
    )

    ledger.append_event(
        actor="csc_operator",
        role="csc",
        case_id="case-101",
        event_type="verification_started",
        data={"status": "verification_started"},
    )

    ledger.append_event(
        actor="officer",
        role="officer",
        case_id="case-101",
        event_type="official_decision_requested",
        data={"status": "official_review"},
    )

    ledger.append_event(
        actor="facilitator",
        role="facilitator",
        case_id="case-102",
        event_type="case_opened",
        data={"route": "grievance", "status": "opened"},
    )

    clean_events = ledger.read_events()
    anchor = clean_events[-1]["hash"]
    record_count = len(clean_events)

    # Create one valid but unauthorized appended chain.
    # This is used to prove that anchor comparison catches
    # even correctly signed new records that were not authorized.
    ledger.append_event(
        actor="facilitator",
        role="facilitator",
        case_id="case-999",
        event_type="extra_event",
        data={"note": "valid signature but unauthorized addition"},
    )

    valid_appended_events = ledger.read_events()

    # Restore the clean chain on disk.
    write_events(ledger_path, clean_events)

    return ledger, clean_events, valid_appended_events, anchor, record_count


def payload_attacks(clean_events: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """
    Class 1: modify event data payloads.
    """
    attacks = []
    n = len(clean_events)

    for i in range(10):
        events = copy.deepcopy(clean_events)
        idx = (i % (n - 1)) + 1  # Avoid genesis record for most payload edits.
        record = events[idx]

        if not isinstance(record.get("data"), dict):
            record["data"] = {}

        if i == 0:
            record["data"]["tampered"] = True
        elif i == 1:
            record["data"]["status"] = "changed"
        elif i == 2:
            record["data"] = {}
        elif i == 3:
            record["data"]["nested"] = {"attack": 1}
        elif i == 4:
            record["data"]["route"] = "changed_route"
        elif i == 5:
            record["data"]["village_code"] = "ATTACK"
        elif i == 6:
            record["data"]["documents_checked"] = []
        elif i == 7:
            record["data"]["numeric"] = 123
        elif i == 8:
            if record["data"]:
                key = next(iter(record["data"]))
                del record["data"][key]
            else:
                record["data"]["added"] = "x"
        elif i == 9:
            record["data"]["unicode"] = "हस्तक्षेप"

        attacks.append(
            (
                "payload",
                f"payload attack {i}: modify data in record {idx}",
                events,
            )
        )

    return attacks


def metadata_attacks(clean_events: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """
    Class 2: modify metadata fields such as actor, case_id, event_type.
    """
    attacks = []
    n = len(clean_events)

    for i in range(10):
        events = copy.deepcopy(clean_events)
        idx = (i % (n - 1)) + 1
        record = events[idx]

        if i == 0:
            record["actor"] = "attacker"
        elif i == 1:
            record["role"] = "attacker_role"
        elif i == 2:
            record["case_id"] = "case-evil"
        elif i == 3:
            record["event_type"] = "tampered_event"
        elif i == 4:
            record["timestamp"] = str(record.get("timestamp")) + "-tampered"
        elif i == 5:
            record["schema_version"] = 999
        elif i == 6:
            record["actor"] = ""
        elif i == 7:
            record["case_id"] = ""
        elif i == 8:
            record["event_type"] = ""
        elif i == 9:
            record["role"] = "admin"

        attacks.append(
            (
                "metadata",
                f"metadata attack {i}: modify core metadata in record {idx}",
                events,
            )
        )

    return attacks


def hash_link_attacks(clean_events: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """
    Class 3: break hashes and prev_hash links.
    """
    attacks = []
    n = len(clean_events)

    for i in range(10):
        events = copy.deepcopy(clean_events)
        idx = i % n
        record = events[idx]

        if i == 0:
            record["hash"] = "0" * 64
        elif i == 1:
            record["hash"] = record["hash"][::-1]
        elif i == 2:
            record["prev_hash"] = "BAD"
        elif i == 3:
            record["prev_hash"] = "0" * 64
        elif i == 4:
            record["prev_hash"] = str(record.get("prev_hash", ""))[:10] + "deadbeef"
        elif i == 5:
            record["hash"] = record["hash"][:-4] + "ffff"
        elif i == 6:
            if idx + 1 < n:
                events[idx + 1]["prev_hash"] = "deadbeef"
            else:
                record["prev_hash"] = "deadbeef"
        elif i == 7:
            record["hash"] = record["hash"].upper()
        elif i == 8:
            record["prev_hash"] = record["hash"]
        elif i == 9:
            if idx > 0:
                record["hash"] = events[idx - 1]["hash"]
            else:
                record["hash"] = "1" * 64

        attacks.append(
            (
                "hash_link",
                f"hash/link attack {i}: break hash chain near record {idx}",
                events,
            )
        )

    return attacks


def deletion_reorder_attacks(clean_events: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """
    Class 4: delete, truncate, or reorder records.
    """
    attacks = []
    n = len(clean_events)

    # 0: delete genesis
    events = copy.deepcopy(clean_events)
    events.pop(0)
    attacks.append(("deletion_reorder", "delete genesis record", events))

    # 1: delete last record
    events = copy.deepcopy(clean_events)
    events.pop()
    attacks.append(("deletion_reorder", "delete last record", events))

    # 2: delete first non-genesis record
    events = copy.deepcopy(clean_events)
    if n > 1:
        events.pop(1)
    attacks.append(("deletion_reorder", "delete first non-genesis record", events))

    # 3: delete middle record
    events = copy.deepcopy(clean_events)
    if n > 3:
        events.pop(n // 2)
    else:
        events.pop(0)
    attacks.append(("deletion_reorder", "delete middle record", events))

    # 4: delete two records
    events = copy.deepcopy(clean_events)
    if n > 2:
        events.pop(1)
        events.pop(-1)
    attacks.append(("deletion_reorder", "delete two records", events))

    # 5: swap two records
    events = copy.deepcopy(clean_events)
    if n > 2:
        events[1], events[2] = events[2], events[1]
    attacks.append(("deletion_reorder", "swap records 1 and 2", events))

    # 6: reverse entire chain
    events = list(reversed(copy.deepcopy(clean_events)))
    attacks.append(("deletion_reorder", "reverse entire chain", events))

    # 7: move last record to front
    events = copy.deepcopy(clean_events)
    if n > 1:
        events.insert(0, events.pop())
    attacks.append(("deletion_reorder", "move last record to front", events))

    # 8: truncate to first half
    events = copy.deepcopy(clean_events)[: max(1, n // 2)]
    attacks.append(("deletion_reorder", "truncate to first half", events))

    # 9: empty ledger
    events = []
    attacks.append(("deletion_reorder", "delete all records", events))

    return attacks


def make_forged_record(
    clean_events: list[dict[str, Any]],
    seq: int,
    prev_hash: str,
    **overrides: Any,
) -> dict[str, Any]:
    base = clean_events[-1]

    record = {
        "schema_version": 1,
        "seq": seq,
        "timestamp": base.get("timestamp", "2026-01-01T00:00:00+00:00"),
        "actor": "attacker",
        "role": "attacker",
        "case_id": "case-evil",
        "event_type": "forged_event",
        "data": {"forged": True},
        "prev_hash": prev_hash,
        "hash": "f" * 64,
        "signature": "ab" * 64,
    }

    record.update(overrides)
    return record


def injection_attacks(
    clean_events: list[dict[str, Any]],
    valid_appended_events: list[dict[str, Any]],
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """
    Class 5: inject forged records or unauthorized valid records.
    """
    attacks = []
    n = len(clean_events)
    last = clean_events[-1]

    # 0: append forged record
    events = copy.deepcopy(clean_events)
    events.append(
        make_forged_record(
            clean_events,
            seq=n,
            prev_hash=last["hash"],
        )
    )
    attacks.append(("injection", "append forged record", events))

    # 1: insert forged record after genesis
    events = copy.deepcopy(clean_events)
    events.insert(
        1,
        make_forged_record(
            clean_events,
            seq=1,
            prev_hash=clean_events[0]["hash"],
        ),
    )
    attacks.append(("injection", "insert forged record after genesis", events))

    # 2: duplicate last record at end
    events = copy.deepcopy(clean_events)
    events.append(copy.deepcopy(last))
    attacks.append(("injection", "duplicate last record at end", events))

    # 3: duplicate middle record
    events = copy.deepcopy(clean_events)
    mid_index = n // 2
    events.insert(mid_index, copy.deepcopy(clean_events[mid_index]))
    attacks.append(("injection", "duplicate middle record", events))

    # 4: append forged record with empty signature
    events = copy.deepcopy(clean_events)
    events.append(
        make_forged_record(
            clean_events,
            seq=n,
            prev_hash=last["hash"],
            signature="",
        )
    )
    attacks.append(("injection", "append forged record with empty signature", events))

    # 5: append forged record with zero signature
    events = copy.deepcopy(clean_events)
    events.append(
        make_forged_record(
            clean_events,
            seq=n,
            prev_hash=last["hash"],
            signature="0" * 128,
        )
    )
    attacks.append(("injection", "append forged record with zero signature", events))

    # 6: modify last hash then append forged record
    events = copy.deepcopy(clean_events)
    events[-1]["hash"] = "e" * 64
    events.append(
        make_forged_record(
            clean_events,
            seq=n,
            prev_hash=events[-1]["hash"],
        )
    )
    attacks.append(("injection", "modify last hash then append forged record", events))

    # 7: append forged record with wrong sequence number
    events = copy.deepcopy(clean_events)
    events.append(
        make_forged_record(
            clean_events,
            seq=n - 1,
            prev_hash=last["hash"],
        )
    )
    attacks.append(("injection", "append forged record with wrong seq", events))

    # 8: append forged record with changed schema version
    events = copy.deepcopy(clean_events)
    events.append(
        make_forged_record(
            clean_events,
            seq=n,
            prev_hash=last["hash"],
            schema_version=999,
        )
    )
    attacks.append(("injection", "append forged record with schema_version 999", events))

    # 9: append a correctly signed but unauthorized record.
    # This should be caught by anchor/record-count mismatch.
    events = copy.deepcopy(valid_appended_events)
    attacks.append(
        (
            "injection",
            "append correctly signed but unauthorized record",
            events,
        )
    )

    return attacks


def main() -> None:
    print("Building temporary ledger...")

    with tempfile.TemporaryDirectory() as tmpdir:
        ledger, clean_events, valid_appended_events, anchor, record_count = build_tmp_ledger(tmpdir)

        ledger_path = ledger.ledger_path
        keys_dir = ledger.keys_dir

        attacks = []
        attacks.extend(payload_attacks(clean_events))
        attacks.extend(metadata_attacks(clean_events))
        attacks.extend(hash_link_attacks(clean_events))
        attacks.extend(deletion_reorder_attacks(clean_events))
        attacks.extend(injection_attacks(clean_events, valid_appended_events))

        if len(attacks) != 50:
            print(f"ERROR: expected 50 attacks, got {len(attacks)}", file=sys.stderr)
            sys.exit(1)

        print(f"Running {len(attacks)} tamper attacks across 5 classes...\n")

        detected = 0
        undetected = []

        detected_by_class = {
            "payload": 0,
            "metadata": 0,
            "hash_link": 0,
            "deletion_reorder": 0,
            "injection": 0,
        }

        total_by_class = {
            "payload": 0,
            "metadata": 0,
            "hash_link": 0,
            "deletion_reorder": 0,
            "injection": 0,
        }

        for i, (attack_class, description, events) in enumerate(attacks, start=1):
            total_by_class[attack_class] += 1

            write_events(ledger_path, events)

            result = verify_chain(
                ledger_path=ledger_path,
                keys_dir=keys_dir,
                expected_anchor=anchor,
                expected_records=record_count,
            )

            if not result["ok"]:
                detected += 1
                detected_by_class[attack_class] += 1
                status = "DETECTED"
            else:
                status = "UNDETECTED"
                undetected.append(
                    {
                        "attack_number": i,
                        "class": attack_class,
                        "description": description,
                    }
                )

            print(f"[{status}] {i:02d} {attack_class}: {description}")

        # Restore clean chain at the end.
        write_events(ledger_path, clean_events)

        summary = {
            "total_attacks": len(attacks),
            "detected": detected,
            "undetected": len(undetected),
            "detected_by_class": detected_by_class,
            "total_by_class": total_by_class,
            "undetected_attacks": undetected,
        }

        print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))

        if undetected:
            print("\nWARNING: Some attacks were not detected.", file=sys.stderr)
            sys.exit(1)

        print("\nALL 50 ATTACKS DETECTED")


if __name__ == "__main__":
    main()