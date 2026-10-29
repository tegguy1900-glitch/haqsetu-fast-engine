import sys
from datetime import date
from pathlib import Path

from schema import load_pack, Outcome


def condition_met(cond, facts):
    if cond.field not in facts:
        return False
    actual = facts[cond.field]
    if cond.op == "eq":
        return actual == cond.value
    if cond.op == "ne":
        return actual != cond.value
    if cond.op == "gt":
        return actual > cond.value
    if cond.op == "gte":
        return actual >= cond.value
    if cond.op == "lt":
        return actual < cond.value
    if cond.op == "lte":
        return actual <= cond.value
    if cond.op == "in":
        return actual in cond.value
    return False


def run_rule(rule, facts):
    if all(condition_met(c, facts) for c in rule.when):
        return rule.outcome
    return Outcome.NEEDS_OFFICIAL_DECISION


def check_file(path):
    pack = load_pack(path)
    failures = 0
    for rule in pack.rules:
        if rule.is_expired(date.today()):
            print(f"  WARN {rule.id}: expired on {rule.expires_on}")
        for i, v in enumerate(rule.test_vectors, start=1):
            got = run_rule(rule, v.input)
            if got == v.expect:
                print(f"  PASS {rule.id} vector {i}")
            else:
                print(f"  FAIL {rule.id} vector {i}: expected {v.expect.value}, got {got.value}")
                failures += 1
    return failures


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(str(p) for p in Path(__file__).parent.glob("*/*.yaml"))
    total = 0
    for p in paths:
        print(p)
        total += check_file(p)
    print("ALL PASSED" if total == 0 else f"{total} FAILED")
    sys.exit(1 if total else 0)