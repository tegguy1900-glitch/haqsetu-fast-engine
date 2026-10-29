from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .chain import Ledger
except ImportError:
    from chain import Ledger


DEFAULT_ANCHOR_PATH = Path(__file__).resolve().parent / "anchor.json"


def verify_chain(
    ledger_path: Path | str | None = None,
    keys_dir: Path | str | None = None,
    expected_anchor: str | None = None,
    expected_records: int | None = None,
) -> dict[str, Any]:
    """
    Verify the ledger chain.

    Checks:
    - sequence numbers
    - prev_hash links
    - record hashes
    - signatures
    - optional expected anchor hash
    - optional expected record count
    """
    ledger = Ledger(ledger_path=ledger_path, keys_dir=keys_dir)

    result = ledger.quick_check()
    events = ledger.read_events()

    anchor = events[-1]["hash"] if events else None

    result["anchor"] = anchor
    result["record_count"] = len(events)
    result["errors"] = result.get("errors", [])

    if expected_anchor is not None and anchor != expected_anchor:
        result["ok"] = False
        result["errors"].append(
            f"anchor mismatch: expected {expected_anchor}, got {anchor}"
        )

    if expected_records is not None and len(events) != expected_records:
        result["ok"] = False
        result["errors"].append(
            f"record count mismatch: expected {expected_records}, got {len(events)}"
        )

    return result


def load_anchor_file(anchor_path: Path) -> dict[str, Any] | None:
    if not anchor_path.exists():
        return None

    try:
        return json.loads(anchor_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_anchor_file(
    anchor_path: Path,
    anchor: str | None,
    record_count: int,
) -> None:
    payload = {
        "anchor": anchor,
        "record_count": record_count,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }

    anchor_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify HaqSetu ledger chain and anchor."
    )

    parser.add_argument(
        "--ledger",
        default=None,
        help="Path to ledger chain.jsonl file.",
    )

    parser.add_argument(
        "--keys",
        default=None,
        help="Path to ledger keys directory.",
    )

    parser.add_argument(
        "--anchor-file",
        default=str(DEFAULT_ANCHOR_PATH),
        help="Path to anchor file.",
    )

    parser.add_argument(
        "--write-anchor",
        action="store_true",
        help="Write the current ledger anchor to the anchor file.",
    )

    parser.add_argument(
        "--ignore-anchor",
        action="store_true",
        help="Do not compare against the anchor file.",
    )

    parser.add_argument(
        "--expected-anchor",
        default=None,
        help="Explicit expected anchor hash.",
    )

    parser.add_argument(
        "--expected-records",
        type=int,
        default=None,
        help="Explicit expected number of records.",
    )

    args = parser.parse_args()

    expected_anchor = args.expected_anchor
    expected_records = args.expected_records

    anchor_path = Path(args.anchor_file)

    if not args.ignore_anchor and anchor_path.exists():
        anchor_data = load_anchor_file(anchor_path)

        if anchor_data:
            if expected_anchor is None:
                expected_anchor = anchor_data.get("anchor")

            if expected_records is None:
                expected_records = anchor_data.get("record_count")

    result = verify_chain(
        ledger_path=args.ledger,
        keys_dir=args.keys,
        expected_anchor=expected_anchor,
        expected_records=expected_records,
    )

    if args.write_anchor:
        write_anchor_file(
            anchor_path=anchor_path,
            anchor=result.get("anchor"),
            record_count=result.get("record_count", 0),
        )

        result["anchor_file"] = str(anchor_path)
        result["anchor_written"] = True

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()