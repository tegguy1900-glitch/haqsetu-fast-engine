import sys
import zlib
from pathlib import Path

from z3 import And, Bool, Int, Or, Solver, sat

from schema import load_pack


def _str_hash(text) -> int:
    """Stable integer stand-in for text values, so Z3 can compare them."""
    return zlib.crc32(str(text).encode("utf-8"))


def translate_condition(cond, z3_vars):
    field = cond.field

    if field not in z3_vars:
        sample = cond.value
        if isinstance(sample, bool):
            z3_vars[field] = [Bool(field), "bool", {}]
        elif isinstance(sample, (int, float)):
            z3_vars[field] = [Int(field), "int", {}]
        else:
            z3_vars[field] = [Int("str_hash_" + field), "str", {}]

    var, kind, mapping = z3_vars[field]

    def cv(x):
        if kind == "bool":
            if not isinstance(x, bool):
                raise ValueError(f"Field '{field}' expects true/false, got {x!r}")
            return x
        if kind == "int":
            if isinstance(x, bool):
                return 1 if x else 0
            if isinstance(x, (int, float)):
                return x
            return _str_hash(x)
        h = _str_hash(x)
        mapping[h] = x
        return h

    op = cond.op
    val = cond.value

    if op == "eq":
        return var == cv(val)
    if op == "ne":
        return var != cv(val)
    if op == "gt":
        return var > cv(val)
    if op == "gte":
        return var >= cv(val)
    if op == "lt":
        return var < cv(val)
    if op == "lte":
        return var <= cv(val)
    if op == "in":
        if not isinstance(val, (list, tuple)):
            raise ValueError(f"Field '{field}' uses 'in' but value is not a list")
        return Or([var == cv(x) for x in val])

    raise ValueError(f"Unknown operator: {op}")


def check_contradictions(packs):
    """
    packs = list of (scheme_name, [rules]).
    Only rules INSIDE the same pack can contradict each other.
    """
    contradictions = 0

    print("--- Scanning for contradictions (inside each scheme/route only) ---")

    for scheme, rules in packs:
        z3_vars = {}
        solver = Solver()

        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                rule_a = rules[i]
                rule_b = rules[j]

                if rule_a.outcome == rule_b.outcome:
                    continue

                solver.push()
                solver.add(And([translate_condition(c, z3_vars) for c in rule_a.when]))
                solver.add(And([translate_condition(c, z3_vars) for c in rule_b.when]))

                if solver.check() == sat:
                    model = solver.model()
                    example = {}
                    for name, (var, kind, mapping) in z3_vars.items():
                        raw = str(model.eval(var, model_completion=True))
                        if kind == "str":
                            example[name] = mapping.get(int(raw), raw)
                        else:
                            example[name] = raw

                    print(f"⚠️  CONTRADICTION inside '{scheme}'!")
                    print(f"   Rule {rule_a.id} wants outcome: {rule_a.outcome.value}")
                    print(f"   Rule {rule_b.id} wants outcome: {rule_b.outcome.value}")
                    print(f"   Example input causing clash: {example}\n")
                    contradictions += 1

                solver.pop()

    if contradictions == 0:
        print("✅ No contradictions found. The rule pack is logically safe.\n")

    return contradictions


if __name__ == "__main__":
    base_dir = Path(__file__).parent
    yaml_files = sorted(base_dir.glob("schemes/*.yaml")) + sorted(base_dir.glob("routes/*.yaml"))

    packs = []
    for path in yaml_files:
        pack = load_pack(str(path))
        packs.append((pack.scheme, pack.rules))

    total_rules = sum(len(rules) for _, rules in packs)
    print(f"Loaded {total_rules} rules from {len(yaml_files)} files.\n")

    errors = check_contradictions(packs)
    sys.exit(1 if errors > 0 else 0)