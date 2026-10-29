from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Make rulepack/schema.py importable from engine/clocks.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULEPACK_DIR = PROJECT_ROOT / "rulepack"

if str(RULEPACK_DIR) not in sys.path:
    sys.path.insert(0, str(RULEPACK_DIR))

from schema import load_pack


@dataclass
class RouteClock:
    route: str
    clock_hours: int
    contact: str | None = None
    desk: str | None = None


def _parse_time(value: datetime | str) -> datetime:
    """
    Accepts a datetime object or an ISO string like:
    2026-10-08T09:00:00
    """
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def load_route_clocks(rulepack_dir: Path | str | None = None) -> dict[str, RouteClock]:
    """
    Load all route YAML files and extract their clock_hours and contact fields.
    """
    base = Path(rulepack_dir) if rulepack_dir else RULEPACK_DIR
    clocks: dict[str, RouteClock] = {}

    for path in sorted(base.glob("routes/*.yaml")):
        pack = load_pack(str(path))

        clock_hours = None
        contact = None
        desk = None

        for rule in pack.rules:
            if clock_hours is None and rule.clock_hours is not None:
                clock_hours = int(rule.clock_hours)

            if contact is None and rule.contact:
                contact = rule.contact

            if desk is None and rule.desk:
                desk = rule.desk

        if clock_hours is None:
            continue

        clocks[pack.scheme] = RouteClock(
            route=pack.scheme,
            clock_hours=clock_hours,
            contact=contact,
            desk=desk,
        )

    return clocks


def clock_status(
    opened_at: datetime | str,
    now: datetime | str | None = None,
    clock_hours: int = 72,
    alert_hours_before: int = 24,
) -> dict[str, Any]:
    """
    Checks whether a case is inside its route deadline.

    Example:
        crop_loss has clock_hours = 72.

    If now is before deadline:
        state = ok or due_soon

    If now is after deadline:
        state = overdue
    """
    opened_dt = _parse_time(opened_at)
    now_dt = _parse_time(now) if now is not None else datetime.now()

    deadline = opened_dt + timedelta(hours=clock_hours)

    elapsed = now_dt - opened_dt
    remaining = deadline - now_dt

    hours_elapsed = elapsed.total_seconds() / 3600
    hours_remaining = remaining.total_seconds() / 3600

    if now_dt > deadline:
        state = "overdue"
        alert = True
        reason = f"Deadline passed {-hours_remaining:.1f} hours ago."

    elif hours_remaining <= alert_hours_before:
        state = "due_soon"
        alert = True
        reason = f"Deadline is near. {hours_remaining:.1f} hours remaining."

    else:
        state = "ok"
        alert = False
        reason = f"On track. {hours_remaining:.1f} hours remaining."

    return {
        "state": state,
        "alert": alert,
        "reason": reason,
        "opened_at": opened_dt.isoformat(),
        "now": now_dt.isoformat(),
        "deadline": deadline.isoformat(),
        "clock_hours": clock_hours,
        "hours_elapsed": round(hours_elapsed, 2),
        "hours_remaining": round(hours_remaining, 2),
    }


def stall_status(
    last_event_at: datetime | str,
    now: datetime | str | None = None,
    stall_hours: int = 48,
) -> dict[str, Any]:
    """
    Checks whether the case has been silent for too long.

    If there has been no update for stall_hours, the case is stalled.
    """
    last_dt = _parse_time(last_event_at)
    now_dt = _parse_time(now) if now is not None else datetime.now()

    silent = now_dt - last_dt
    silent_hours = silent.total_seconds() / 3600

    if silent_hours >= stall_hours:
        state = "stalled"
        alert = True
        reason = f"No update for {silent_hours:.1f} hours."
    else:
        state = "active"
        alert = False
        reason = f"Last update {silent_hours:.1f} hours ago."

    return {
        "state": state,
        "alert": alert,
        "reason": reason,
        "last_event_at": last_dt.isoformat(),
        "now": now_dt.isoformat(),
        "stall_hours": stall_hours,
        "silent_hours": round(silent_hours, 2),
    }


def _led_state(clock_state: str, stall_state: str) -> str:
    """
    Simple LED mapping for the later ESP32 exhibit.

    green: everything is on track
    amber: due soon or stalled
    red: overdue
    """
    if clock_state == "overdue":
        return "red"

    if clock_state == "due_soon" or stall_state == "stalled":
        return "amber"

    return "green"


def evaluate_case_clocks(
    case: dict[str, Any],
    now: datetime | str | None = None,
    rulepack_dir: Path | str | None = None,
    alert_hours_before: int = 24,
    stall_hours: int = 48,
) -> dict[str, Any]:
    """
    Evaluate one case.

    Expected case format:

    {
        "route": "crop_loss",
        "opened_at": "2026-10-08T09:00:00",
        "last_event_at": "2026-10-09T09:00:00"
    }

    If last_event_at is missing, opened_at is used.
    """
    route = case.get("route") or case.get("scheme")
    opened_at = case.get("opened_at")

    if not route:
        return {"error": "Case needs a 'route' field."}

    if not opened_at:
        return {"error": "Case needs an 'opened_at' field."}

    clocks = load_route_clocks(rulepack_dir)

    if route not in clocks:
        return {
            "error": f"No route clock found for '{route}'.",
            "known_routes": sorted(clocks.keys()),
        }

    clock = clocks[route]
    now_dt = _parse_time(now) if now is not None else datetime.now()

    last_event_at = case.get("last_event_at") or opened_at

    clock_report = clock_status(
        opened_at=opened_at,
        now=now_dt,
        clock_hours=clock.clock_hours,
        alert_hours_before=alert_hours_before,
    )

    stall_report = stall_status(
        last_event_at=last_event_at,
        now=now_dt,
        stall_hours=stall_hours,
    )

    return {
        "route": route,
        "clock_hours": clock.clock_hours,
        "contact": clock.contact,
        "desk": clock.desk,
        "opened_at": clock_report["opened_at"],
        "now": clock_report["now"],
        "deadline": clock_report["deadline"],
        "clock": clock_report,
        "stall": stall_report,
        "alert": clock_report["alert"] or stall_report["alert"],
        "led": _led_state(clock_report["state"], stall_report["state"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HaqSetu clock and stall timer checker."
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all route clocks loaded from rulepack/routes.",
    )

    parser.add_argument(
        "--route",
        help="Route name, e.g. crop_loss, wage_work, grievance.",
    )

    parser.add_argument(
        "--opened-at",
        help="Case opened time, e.g. 2026-10-08T09:00:00",
    )

    parser.add_argument(
        "--last-event-at",
        help="Last update time, e.g. 2026-10-09T09:00:00",
    )

    parser.add_argument(
        "--now",
        help="Optional current time override, e.g. 2026-10-11T09:00:00",
    )

    parser.add_argument(
        "--stall-hours",
        type=int,
        default=48,
        help="Number of silent hours before a case is considered stalled.",
    )

    parser.add_argument(
        "--alert-hours-before",
        type=int,
        default=24,
        help="Raise a due_soon alert this many hours before the deadline.",
    )

    parser.add_argument(
        "--rulepack-dir",
        help="Optional path to rulepack folder.",
    )

    args = parser.parse_args()

    if args.list:
        clocks = load_route_clocks(args.rulepack_dir)
        output = {name: asdict(clock) for name, clock in clocks.items()}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if not args.route or not args.opened_at:
        parser.error("Provide --route and --opened-at, or use --list.")

    case = {
        "route": args.route,
        "opened_at": args.opened_at,
        "last_event_at": args.last_event_at,
    }

    report = evaluate_case_clocks(
        case,
        now=args.now,
        rulepack_dir=args.rulepack_dir,
        alert_hours_before=args.alert_hours_before,
        stall_hours=args.stall_hours,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()