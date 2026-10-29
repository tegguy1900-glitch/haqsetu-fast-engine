from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parent / "haqsetu.db"

STATUS_EVENT_MAP = {
    "official_pass": "passed",
    "official_reject": "official_rejected",
    "verify_requested": "verify_requested",
    "citizen_contacted": "citizen_contacted",
    "case_closed": "closed",
    "closed": "closed",
    "resolved": "closed",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                route TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                facts_json TEXT NOT NULL DEFAULT '{}',
                outcomes_json TEXT NOT NULL DEFAULT '{}',
                opened_at TEXT NOT NULL,
                last_event_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                role TEXT,
                event_type TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(case_id) REFERENCES cases(case_id)
            );
            """
        )


def _row_to_case(row: sqlite3.Row) -> dict[str, Any]:
    case = dict(row)

    facts_json = case.pop("facts_json", "{}")
    outcomes_json = case.pop("outcomes_json", "{}")

    case["facts"] = json.loads(facts_json or "{}")
    case["outcomes"] = json.loads(outcomes_json or "{}")

    return case


def create_case(
    case_id: str,
    route: str,
    facts: dict[str, Any],
    outcomes: dict[str, Any],
    opened_at: str | None = None,
    last_event_at: str | None = None,
) -> dict[str, Any]:
    now = now_iso()
    opened = opened_at or now
    last_event = last_event_at or opened

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO cases (
                case_id,
                route,
                status,
                facts_json,
                outcomes_json,
                opened_at,
                last_event_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                route,
                "open",
                json.dumps(facts, ensure_ascii=False),
                json.dumps(outcomes, ensure_ascii=False),
                opened,
                last_event,
                now,
                now,
            ),
        )

    return get_case(case_id)


def get_case(case_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_case(row)


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM cases
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_case(row) for row in rows]


def update_evaluation(
    case_id: str,
    facts: dict[str, Any],
    outcomes: dict[str, Any],
    updated_at: str | None = None,
) -> dict[str, Any] | None:
    updated = updated_at or now_iso()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE cases
            SET
                facts_json = ?,
                outcomes_json = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (
                json.dumps(facts, ensure_ascii=False),
                json.dumps(outcomes, ensure_ascii=False),
                updated,
                case_id,
            ),
        )

    return get_case(case_id)


def record_event(
    case_id: str,
    actor: str,
    role: str | None,
    event_type: str,
    data: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any] | None:
    created = created_at or now_iso()
    new_status = STATUS_EVENT_MAP.get(event_type)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO case_events (
                case_id,
                actor,
                role,
                event_type,
                data_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                actor,
                role,
                event_type,
                json.dumps(data, ensure_ascii=False),
                created,
            ),
        )

        if new_status:
            conn.execute(
                """
                UPDATE cases
                SET
                    last_event_at = ?,
                    updated_at = ?,
                    status = ?
                WHERE case_id = ?
                """,
                (created, created, new_status, case_id),
            )
        else:
            conn.execute(
                """
                UPDATE cases
                SET
                    last_event_at = ?,
                    updated_at = ?
                WHERE case_id = ?
                """,
                (created, created, case_id),
            )

    return get_case(case_id)


def get_case_events(case_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM case_events
            WHERE case_id = ?
            ORDER BY id ASC
            """,
            (case_id,),
        ).fetchall()

    events = []

    for row in rows:
        event = dict(row)
        data_json = event.pop("data_json", "{}")
        event["data"] = json.loads(data_json or "{}")
        events.append(event)

    return events