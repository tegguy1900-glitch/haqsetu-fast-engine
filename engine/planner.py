from __future__ import annotations

import argparse
import json
import sys
from math import ceil
from pathlib import Path
from typing import Any

try:
    from .rules import evaluate_household
except ImportError:
    try:
        from engine.rules import evaluate_household
    except ImportError:
        from rules import evaluate_household

try:
    from ortools.sat.python import cp_model
except Exception:
    # Fallback for Python 3.14 where OR-Tools C++ DLLs fail to load
    cp_model = None


def collect_tasks_from_evaluation(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    tasks_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for result in evaluation.get("results", []):
        scheme = result.get("scheme")

        for item in result.get("trace", []):
            if not item.get("matched"):
                continue

            outcome = item.get("outcome_if_matched")
            if outcome not in {"include", "verify"}:
                continue

            desk = item.get("desk") or "unknown_desk"
            key = (scheme, desk)

            if key not in tasks_by_key:
                tasks_by_key[key] = {
                    "task_id": f"{scheme}:{desk}",
                    "scheme": scheme,
                    "desk": desk,
                    "documents": set(),
                    "rule_ids": [],
                    "clock_hours": item.get("clock_hours"),
                    "contact": item.get("contact"),
                }

            task = tasks_by_key[key]
            task["documents"].update(item.get("documents") or [])
            task["rule_ids"].append(item.get("rule_id"))

            if task["clock_hours"] is None and item.get("clock_hours") is not None:
                task["clock_hours"] = item.get("clock_hours")

    tasks = []
    for task in tasks_by_key.values():
        tasks.append({
            "task_id": task["task_id"],
            "scheme": task["scheme"],
            "desk": task["desk"],
            "documents": sorted(list(task["documents"])),
            "rule_ids": task["rule_ids"],
            "clock_hours": task["clock_hours"],
            "contact": task["contact"],
        })
    return tasks


def plan_from_tasks(
    tasks: list[dict[str, Any]],
    max_desks_per_visit: int = 3,
) -> dict[str, Any]:
    if max_desks_per_visit <= 0:
        raise ValueError("max_desks_per_visit must be positive.")

    if not tasks:
        return {
            "status": "no_tasks", "num_tasks": 0, "distinct_desks": 0,
            "naive_visits": 0, "planned_visits": 0, "lower_bound": 0,
            "max_desks_per_visit": max_desks_per_visit, "visits": [], "tasks": [],
        }

    n = len(tasks)
    desks = sorted({task["desk"] for task in tasks})
    distinct_desks = len(desks)
    naive_visits = n
    lower_bound = max(1, ceil(distinct_desks / max_desks_per_visit))

    # --- FALLBACK PLANNER (If OR-Tools fails to load) ---
    if cp_model is None:
        print("⚠️  OR-Tools unavailable. Using fallback greedy planner.")
        visits = []
        desks_seen = set()
        for task in tasks:
            if task["desk"] not in desks_seen:
                desks_seen.add(task["desk"])
                visits.append({
                    "visit_number": len(visits) + 1,
                    "desks": [task["desk"]],
                    "documents": task["documents"],
                    "tasks": [task["task_id"]],
                    "schemes": [task["scheme"]],
                })
        
        return {
            "status": "fallback_greedy",
            "num_tasks": n,
            "distinct_desks": distinct_desks,
            "naive_visits": naive_visits,
            "planned_visits": len(visits),
            "lower_bound": lower_bound,
            "max_desks_per_visit": max_desks_per_visit,
            "visits": visits,
            "tasks": tasks,
        }

    # --- OR-TOOLS CP-SAT PLANNER ---
    max_visits = n
    model = cp_model.CpModel()
    x = {}
    for t in range(n):
        for v in range(max_visits):
            x[t, v] = model.NewBoolVar(f"x_{t}_{v}")

    used = {}
    for v in range(max_visits):
        used[v] = model.NewBoolVar(f"used_{v}")

    for t in range(n):
        model.Add(sum(x[t, v] for v in range(max_visits)) == 1)

    for t in range(n):
        for v in range(max_visits):
            model.Add(x[t, v] <= used[v])

    for v in range(max_visits - 1):
        model.Add(used[v] >= used[v + 1])

    desk_used = {}
    for v in range(max_visits):
        desk_bools = []
        for desk in desks:
            b = model.NewBoolVar(f"desk_used_{v}_{desk}")
            desk_used[v, desk] = b
            desk_bools.append(b)
            task_indices = [t for t, task in enumerate(tasks) if task["desk"] == desk]
            if task_indices:
                for t in task_indices:
                    model.Add(x[t, v] <= b)
                model.Add(b <= sum(x[t, v] for t in task_indices))
            else:
                model.Add(b == 0)
        model.Add(sum(desk_bools) <= max_desks_per_visit)

    model.Minimize(sum(used[v] for v in range(max_visits)))
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": "infeasible", "num_tasks": n, "distinct_desks": distinct_desks,
            "naive_visits": naive_visits, "planned_visits": None, "lower_bound": lower_bound,
            "max_desks_per_visit": max_desks_per_visit, "visits": [], "tasks": tasks,
        }

    visits = []
    for v in range(max_visits):
        if not solver.Value(used[v]):
            continue
        visit_desks = set()
        visit_documents = set()
        visit_tasks = []
        visit_schemes = set()
        for t in range(n):
            if solver.Value(x[t, v]):
                task = tasks[t]
                visit_desks.add(task["desk"])
                visit_documents.update(task["documents"])
                visit_tasks.append(task["task_id"])
                visit_schemes.add(task["scheme"])
        visits.append({
            "visit_number": len(visits) + 1,
            "desks": sorted(list(visit_desks)),
            "documents": sorted(list(visit_documents)),
            "tasks": visit_tasks,
            "schemes": sorted(list(visit_schemes)),
        })

    return {
        "status": "optimal" if status == cp_model.OPTIMAL else "feasible",
        "num_tasks": n, "distinct_desks": distinct_desks, "naive_visits": naive_visits,
        "planned_visits": len(visits), "lower_bound": lower_bound,
        "max_desks_per_visit": max_desks_per_visit, "visits": visits, "tasks": tasks,
    }


def plan_from_facts(
    facts: dict[str, Any],
    rulepack_dir: Path | str | None = None,
    max_desks_per_visit: int = 3,
) -> dict[str, Any]:
    evaluation = evaluate_household(facts, rulepack_dir=rulepack_dir)
    tasks = collect_tasks_from_evaluation(evaluation)
    plan = plan_from_tasks(tasks, max_desks_per_visit=max_desks_per_visit)
    plan["facts"] = facts
    plan["final_by_scheme"] = evaluation.get("final_by_scheme", {})
    plan["includes"] = evaluation.get("includes", [])
    plan["official_needed"] = evaluation.get("official_needed", [])
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="HaqSetu one-visit planner.")
    parser.add_argument("--facts", default="{}")
    parser.add_argument("--facts-file", help="Path to a JSON file containing facts.")
    parser.add_argument("--rulepack-dir", help="Optional path to rulepack folder.")
    parser.add_argument("--max-desks-per-visit", type=int, default=3)
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

    try:
        plan = plan_from_facts(
            facts=facts,
            rulepack_dir=args.rulepack_dir,
            max_desks_per_visit=args.max_desks_per_visit,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()