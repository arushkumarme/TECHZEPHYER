"""Append-only SQLite log of messages and incident state transitions (doc 02 C-BUS, doc 04 §7).

Append-only is enforced by the database itself: triggers abort any UPDATE or DELETE on
the log tables, so no code path can rewrite history.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id    TEXT,
    message_id     TEXT,
    in_reply_to    TEXT,
    sender         TEXT,
    recipient      TEXT,
    message_type   TEXT,
    sent_at        TEXT,
    valid          INTEGER NOT NULL,
    error_code     TEXT,
    error_detail   TEXT,
    ignored_fields TEXT NOT NULL,
    raw_json       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_incident ON messages(incident_id, seq);
CREATE TABLE IF NOT EXISTS transitions (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    from_state  TEXT,
    to_state    TEXT NOT NULL,
    trigger     TEXT NOT NULL,
    message_id  TEXT,
    at          TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_transitions_incident ON transitions(incident_id, seq);
CREATE TABLE IF NOT EXISTS incidents (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    meta        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    report_json TEXT NOT NULL,
    markdown    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_incident ON reports(incident_id, seq);
"""
_APPEND_ONLY = [
    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} BEFORE {op} ON {table} "
    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"
    for table in ("messages", "transitions", "incidents", "reports")
    for op in ("UPDATE", "DELETE")
]


@dataclass(frozen=True)
class LoggedMessage:
    seq: int
    incident_id: str | None
    message_id: str | None
    in_reply_to: str | None
    sender: str | None
    recipient: str | None
    message_type: str | None
    sent_at: str | None
    valid: bool
    error_code: str | None
    error_detail: str | None
    ignored_fields: list[str]
    raw_json: str


@dataclass(frozen=True)
class Transition:
    seq: int
    incident_id: str
    from_state: str | None
    to_state: str
    trigger: str
    message_id: str | None
    at: str
    detail: dict[str, Any]


class LogStore:
    """Thread-safe append-only store. ``path=":memory:"`` for ephemeral use."""

    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            for stmt in _APPEND_ONLY:
                self._conn.execute(stmt)

    # ------------------------------------------------------------------ writes
    def append_message(
        self,
        *,
        raw_json: str,
        header: dict[str, Any],
        valid: bool,
        ignored_fields: list[str] | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> int:
        """Append one wire message. ``header`` holds whatever envelope fields were readable."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (incident_id, message_id, in_reply_to, sender, recipient,"
                " message_type, sent_at, valid, error_code, error_detail, ignored_fields,"
                " raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    _s(header.get("incident_id")),
                    _s(header.get("message_id")),
                    _s(header.get("in_reply_to")),
                    _s(header.get("sender")),
                    _s(header.get("recipient")),
                    _s(header.get("message_type")),
                    _s(header.get("sent_at")),
                    int(valid),
                    error_code,
                    error_detail,
                    json.dumps(ignored_fields or []),
                    raw_json,
                ),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    def append_transition(
        self,
        incident_id: str,
        from_state: str | None,
        to_state: str,
        *,
        trigger: str,
        at: datetime,
        message_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO transitions (incident_id, from_state, to_state, trigger, message_id,"
                " at, detail) VALUES (?,?,?,?,?,?,?)",
                (
                    incident_id,
                    from_state,
                    to_state,
                    trigger,
                    message_id,
                    at.isoformat(),
                    json.dumps(detail or {}, sort_keys=True, default=str),
                ),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    # ------------------------------------------------------------------ reads
    def messages(self, incident_id: str | None = None) -> list[LoggedMessage]:
        with self._lock:
            if incident_id is None:
                rows = self._conn.execute("SELECT * FROM messages ORDER BY seq").fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE incident_id=? ORDER BY seq", (incident_id,)
                ).fetchall()
        return [
            LoggedMessage(
                seq=r[0],
                incident_id=r[1],
                message_id=r[2],
                in_reply_to=r[3],
                sender=r[4],
                recipient=r[5],
                message_type=r[6],
                sent_at=r[7],
                valid=bool(r[8]),
                error_code=r[9],
                error_detail=r[10],
                ignored_fields=json.loads(r[11]),
                raw_json=r[12],
            )
            for r in rows
        ]

    def transitions(self, incident_id: str) -> list[Transition]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM transitions WHERE incident_id=? ORDER BY seq", (incident_id,)
            ).fetchall()
        return [
            Transition(
                seq=r[0],
                incident_id=r[1],
                from_state=r[2],
                to_state=r[3],
                trigger=r[4],
                message_id=r[5],
                at=r[6],
                detail=json.loads(r[7]),
            )
            for r in rows
        ]

    def incident_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT incident_id FROM transitions GROUP BY incident_id ORDER BY MIN(seq)"
            ).fetchall()
        return [r[0] for r in rows]

    def register_incident(self, meta: dict[str, Any], *, at: datetime) -> str:
        """Allocate the next sequential incident id (``INC-0001``...) and record it."""
        with self._lock:
            (count,) = self._conn.execute("SELECT COUNT(*) FROM incidents").fetchone()
            incident_id = f"INC-{count + 1:04d}"
            self._conn.execute(
                "INSERT INTO incidents (incident_id, created_at, meta) VALUES (?,?,?)",
                (incident_id, at.isoformat(), json.dumps(meta, sort_keys=True, default=str)),
            )
            return incident_id

    def incident_meta(self, incident_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT meta, created_at FROM incidents WHERE incident_id=?", (incident_id,)
            ).fetchone()
        if row is None:
            return None
        meta: dict[str, Any] = json.loads(row[0])
        meta["created_at"] = row[1]
        return meta

    def list_incidents(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT incident_id FROM incidents ORDER BY seq").fetchall()
        return [r[0] for r in rows]

    def append_report(
        self, incident_id: str, report: dict[str, Any], markdown: str, *, at: datetime
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO reports (incident_id, created_at, report_json, markdown)"
                " VALUES (?,?,?,?)",
                (incident_id, at.isoformat(), json.dumps(report), markdown),
            )

    def latest_report(self, incident_id: str) -> tuple[dict[str, Any], str] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT report_json, markdown FROM reports WHERE incident_id=?"
                " ORDER BY seq DESC LIMIT 1",
                (incident_id,),
            ).fetchone()
        if row is None:
            return None
        report: dict[str, Any] = json.loads(row[0])
        return report, row[1]

    def execute_unsafe_for_tests(self, sql: str) -> None:
        """Run raw SQL (tests use it to prove the append-only triggers fire)."""
        with self._lock:
            self._conn.execute(sql)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _s(value: Any) -> str | None:
    return None if value is None else str(value)
