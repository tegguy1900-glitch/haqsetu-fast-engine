from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Make rulepack/schema.py importable from engine/rules.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULEPACK_DIR = PROJECT_ROOT / "rulepack"

if str(RULEPACK_DIR) not in sys.path:
    sys.path.insert(0, str(RULEPACK_DIR))

from schema import Outcome, Rule, RulePack, load_pack


# If multiple matched rules somehow disagree, choose the safest outcome.
# verify is most cautious, then needs_official_decision, then include.
PRIORITY = {
    Outcome.VERIFY: 3,
    Outcome.NEEDS_OFFICIAL_DECISION: 2,
    Outcome.INCLUDE: 1,
}


def _condition_status(cond, facts: dict[str, Any]):
    """
    Check one condition against the household facts.

    Returns:
        ok: bool
        actual: value from facts, or None if missing
        status: "met", "not_met", "missing", "type_mismatch", etc.
    """
    if cond.field not in facts:
        return False, None, "missing"

    actual = facts[cond.field]

    try:
        if cond.op == "eq":
            ok = actual == cond.value
        elif cond.op == "ne":
            ok = actual != cond.value
        elif cond.op == "gt":
            ok = actual > cond.value
        elif cond.op == "gte":
            ok = actual >= cond.value
        elif cond.op == "lt":
            ok = actual < cond.value
        elif cond.op == "lte":
            ok = actual <= cond.value
        elif cond.op == "in":
            if isinstance(cond.value, (list, tuple, set)):
                ok = actual in cond.value
            else:
                ok = actual == cond.value
        else:
            return False, actual, "unsupported_operator"

    except TypeError:
        return False, actual, "type_mismatch"

    return ok, actual, "met" if ok else "not_met"


def evaluate_rule(rule: Rule, facts: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """
    Evaluate one rule against facts and produce a proof-trace entry.
    """
    expired = rule.is_expired(today)

    condition_entries = []
    all_met = True

    for cond in rule.when:
        ok, actual, status = _condition_status(cond, facts)

        condition_entries.append(
            {
                "field": cond.field,
                "op": cond.op,
                "required": cond.value,
                "actual": actual,
                "status": status,
            }
        )

        if not ok:
            all_met = False

    matched = all_met and not expired

    entry = {
        "rule_id": rule.id,
        "description": rule.description,
        "desk": rule.desk,
        "clock_hours": rule.clock_hours,
        "contact": rule.contact,
        "documents": rule.documents,
        "source_doc": rule.source.doc,
        "source_clause": rule.source.clause,
        "source_url": rule.source.url,
        "expired": expired,
        "matched": matched,
        "outcome_if_matched": rule.outcome.value,
        "issued_outcome": rule.outcome.value if matched else None,
        "conditions": condition_entries,
    }

    if expired:
        entry["note"] = "Rule expired; not used to decide."
    elif not matched:
        entry["note"] = (
            "Conditions not fully met. This rule does not deny; "
            "it simply does not affirm."
        )
    else:
        entry["note"] = "Rule matched."

    return entry


def evaluate_pack(pack: RulePack, facts: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """
    Evaluate one YAML rule pack against facts.
    """
    trace = []
    matched_outcomes = []
    matched_rule_ids = []

    for rule in pack.rules:
        result = evaluate_rule(rule, facts, today)
        trace.append(result)

        if result["matched"]:
            matched_outcomes.append(rule.outcome)
            matched_rule_ids.append(rule.id)

    if matched_outcomes:
        final = max(matched_outcomes, key=lambda outcome: PRIORITY[outcome])
        explanation = (
            f"Matched rules: {', '.join(matched_rule_ids)}. "
            f"Selected most cautious outcome among matched rules."
        )
    else:
        final = Outcome.NEEDS_OFFICIAL_DECISION
        explanation = (
            "No rule fully matched. Sending to official decision. "
            "No denial issued."
        )

    return {
        "scheme": pack.scheme,
        "state": pack.state,
        "final_outcome": final.value,
        "matched_rules": matched_rule_ids,
        "explanation": explanation,
        "trace": trace,
    }


def load_all_packs(rulepack_dir: Path | str | None = None) -> list[RulePack]:
    """
    Load all YAML files from rulepack/schemes and rulepack/routes.
    """
    base = Path(rulepack_dir) if rulepack_dir else RULEPACK_DIR

    files = sorted(base.glob("schemes/*.yaml")) + sorted(base.glob("routes/*.yaml"))

    packs = []
    for path in files:
        packs.append(load_pack(str(path)))

    return packs


def evaluate_household(
    facts: dict[str, Any],
    rulepack_dir: Path | str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """
    Main evaluation function.

    Input:
        facts: household facts, e.g. {"age": 65, "bpl_status": true}

    Output:
        A report containing outcomes for every scheme/route and proof traces.
    """
    packs = load_all_packs(rulepack_dir)
    results = [evaluate_pack(pack, facts, today) for pack in packs]

    final_by_scheme = {result["scheme"]: result["final_outcome"] for result in results}

    includes = [
        scheme
        for scheme, outcome in final_by_scheme.items()
        if outcome == Outcome.INCLUDE.value
    ]

    official_needed = [
        scheme
        for scheme, outcome in final_by_scheme.items()
        if outcome != Outcome.INCLUDE.value
    ]

    return {
        "evaluation_date": (today or date.today()).isoformat(),
        "facts": facts,
        "never_denied": True,
        "final_by_scheme": final_by_scheme,
        "includes": includes,
        "official_needed": official_needed,
        "results": results,
    }


def _print_human(report: dict[str, Any]) -> None:
    """
    Print a readable version for demos and debugging.
    """
    print(f"Evaluation date: {report['evaluation_date']}")
    print(f"Facts: {json.dumps(report['facts'], ensure_ascii=False)}")
    print("\nNever denied: yes\n")

    for result in report["results"]:
        print(f"Scheme/Route: {result['scheme']}")
        print(f"  Final outcome: {result['final_outcome']}")
        print(f"  Explanation: {result['explanation']}")

        for item in result["trace"]:
            if item["matched"]:
                mark = "MATCH"
            elif item["expired"]:
                mark = "EXPIRED"
            else:
                mark = "-----"

            print(f"  [{mark}] {item['rule_id']}: {item['description']}")

            if item["conditions"]:
                for cond in item["conditions"]:
                    print(
                        f"       - {cond['field']} {cond['op']} {cond['required']!r} "
                        f"(actual={cond['actual']!r}, {cond['status']})"
                    )

        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate household facts against HaqSetu rule packs."
    )

    parser.add_argument(
        "--facts",
        default="{}",
        help='JSON object, e.g. \'{"age":65,"bpl_status":true}\'',
    )

    parser.add_argument(
        "--facts-file",
        help="Path to a JSON file containing facts.",
    )

    parser.add_argument(
        "--rulepack-dir",
        help="Optional path to rulepack folder.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )

    parser.add_argument(
        "--today",
        help="Override today's date as YYYY-MM-DD, useful for testing expiry.",
    )

    args = parser.parse_args()

    if args.facts_file:
        facts_text = Path(args.facts_file).read_text(encoding="utf-8")
    else:
        facts_text = args.facts

    try:
        facts = json.loads(facts_text)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON facts: {exc}", file=sys.stderr)
        sys.exit(2)

    today = None
    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print("--today must be YYYY-MM-DD", file=sys.stderr)
            sys.exit(2)

    report = evaluate_household(facts, args.rulepack_dir, today)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)


if __name__ == "__main__":
    main()