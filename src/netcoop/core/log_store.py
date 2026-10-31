"""Append-only SQLite log of messages and incident state transitions (doc 02 C-BUS, doc 04 §7).

Append-only is enforced by the database itself: triggers abort any UPDATE or DELETE on
the log tables, so no code path can rewrite history.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
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
CREATE TABLE IF NOT EXISTS checkpoints (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    kind        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_checkpoints_incident ON checkpoints(incident_id, seq);
CREATE TABLE IF NOT EXISTS approvals (
    seq               INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id       TEXT NOT NULL,
    action_index      INTEGER NOT NULL,
    action            TEXT NOT NULL,
    decision          TEXT NOT NULL,
    reviewer          TEXT NOT NULL,
    note              TEXT NOT NULL,
    simulated_outcome TEXT,
    decided_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_approvals_incident ON approvals(incident_id, seq);
"""
#: Columns added in protocol 1.1 (Prompt 5). Added by an automatic migration so databases
#: written by earlier versions keep working; their old rows read these as derived/empty.
_MESSAGE_COLUMNS_V2: tuple[tuple[str, str], ...] = (
    ("attempt_seq", "INTEGER"),  # every attempt per incident, accepted or rejected
    ("received_at", "TEXT"),  # bus clock (injected)
    ("snapshot_id", "TEXT"),
    ("mode", "TEXT"),
    ("data_provenance", "TEXT"),
    ("status", "TEXT"),
    ("verdict", "TEXT"),  # accepted | rejected
    ("violations_json", "TEXT"),  # [{code, reason, path}]
    ("warnings_json", "TEXT"),  # [{code, reason, path}]
    ("payload_json", "TEXT"),
    ("protocol_seq", "INTEGER"),  # envelope seq of an accepted message
)
_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    seq  INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
"""
_V1_COLUMNS = (
    "seq",
    "incident_id",
    "message_id",
    "in_reply_to",
    "sender",
    "recipient",
    "message_type",
    "sent_at",
    "valid",
    "error_code",
    "error_detail",
    "ignored_fields",
    "raw_json",
)

_APPEND_ONLY = [
    f"CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} BEFORE {op} ON {table} "
    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"
    for table in (
        "messages",
        "transitions",
        "incidents",
        "reports",
        "checkpoints",
        "approvals",
        "schema_migrations",
    )
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
    # ---- protocol 1.1 log columns ----
    attempt_seq: int = 0
    received_at: str | None = None
    snapshot_id: str | None = None
    mode: str | None = None
    data_provenance: str | None = None
    status: str | None = None
    verdict: str = "accepted"
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    payload_json: str | None = None
    protocol_seq: int | None = None

    def as_record(self) -> dict[str, Any]:
        """Plain-dict form (used by ``iter_trace`` and ``export_jsonl``)."""
        return {
            "incident_id": self.incident_id,
            "seq": self.attempt_seq,
            "protocol_seq": self.protocol_seq,
            "message_id": self.message_id,
            "received_at": self.received_at,
            "sent_at": self.sent_at,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "in_reply_to": self.in_reply_to,
            "snapshot_id": self.snapshot_id,
            "mode": self.mode,
            "data_provenance": self.data_provenance,
            "status": self.status,
            "verdict": self.verdict,
            "error_code": self.error_code,
            "violations": self.violations,
            "warnings": self.warnings,
            "ignored_fields": self.ignored_fields,
            "payload": json.loads(self.payload_json) if self.payload_json else None,
        }


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
        self._extension_tables: set[str] = set()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.executescript(_MIGRATIONS_TABLE)
            self._migrate()
            for stmt in _APPEND_ONLY:
                self._conn.execute(stmt)

    def _migrate(self) -> None:
        """Add the 1.1 message columns to a database written by an earlier version.
        ALTER TABLE ... ADD COLUMN never rewrites existing rows, so the append-only rule
        holds; old rows read the new columns as derived values (see ``messages``)."""
        have = {r[1] for r in self._conn.execute("PRAGMA table_info(messages)")}
        for name, sql_type in _MESSAGE_COLUMNS_V2:
            if name not in have:
                self._conn.execute(f"ALTER TABLE messages ADD COLUMN {name} {sql_type}")
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (name) VALUES ('messages_v2_protocol_1_1')"
        )

    def migrations(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT name FROM schema_migrations ORDER BY seq")
            return [r[0] for r in rows.fetchall()]

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
        received_at: datetime | None = None,
        violations: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> int:
        """Append one message attempt (accepted or rejected). ``header`` holds whatever
        envelope fields were readable. ``attempt_seq`` is assigned here, per incident."""
        incident = _s(header.get("incident_id"))
        if not valid and not violations and error_code:
            violations = [{"code": error_code, "reason": error_detail or "", "path": ""}]
        with self._lock:
            (count,) = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE incident_id IS ?", (incident,)
            ).fetchone()
            cur = self._conn.execute(
                "INSERT INTO messages (incident_id, message_id, in_reply_to, sender, recipient,"
                " message_type, sent_at, valid, error_code, error_detail, ignored_fields,"
                " raw_json, attempt_seq, received_at, snapshot_id, mode, data_provenance,"
                " status, verdict, violations_json, warnings_json, payload_json, protocol_seq)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    incident,
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
                    count + 1,
                    received_at.isoformat() if received_at else None,
                    _s(header.get("snapshot_id")),
                    _s(header.get("mode")),
                    _s(header.get("data_provenance")),
                    _s(header.get("status")),
                    "accepted" if valid else "rejected",
                    json.dumps(violations or []),
                    json.dumps(warnings or []),
                    _payload_json(raw_json),
                    header.get("seq") if valid and isinstance(header.get("seq"), int) else None,
                ),
            )
            assert cur.lastrowid is not None
            return cur.lastrowid

    #: Pack name for :meth:`append_message`.
    append = append_message

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
        cols = ", ".join((*_V1_COLUMNS, *(c for c, _ in _MESSAGE_COLUMNS_V2)))
        with self._lock:
            if incident_id is None:
                rows = self._conn.execute(f"SELECT {cols} FROM messages ORDER BY seq").fetchall()
            else:
                rows = self._conn.execute(
                    f"SELECT {cols} FROM messages WHERE incident_id=? ORDER BY seq",
                    (incident_id,),
                ).fetchall()
        out: list[LoggedMessage] = []
        position: dict[str | None, int] = {}
        for r in rows:
            position[r[1]] = position.get(r[1], 0) + 1
            v = dict(zip((c for c, _ in _MESSAGE_COLUMNS_V2), r[13:], strict=True))
            out.append(
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
                    # rows written before the migration: derive what can be derived
                    attempt_seq=v["attempt_seq"] or position[r[1]],
                    received_at=v["received_at"],
                    snapshot_id=v["snapshot_id"],
                    mode=v["mode"],
                    data_provenance=v["data_provenance"],
                    status=v["status"],
                    verdict=v["verdict"] or ("accepted" if r[8] else "rejected"),
                    violations=json.loads(v["violations_json"])
                    if v["violations_json"]
                    else ([] if r[8] else [{"code": r[9], "reason": r[10] or "", "path": ""}]),
                    warnings=json.loads(v["warnings_json"]) if v["warnings_json"] else [],
                    payload_json=v["payload_json"] or _payload_json(r[12]),
                    protocol_seq=v["protocol_seq"],
                )
            )
        return out

    #: Pack name for :meth:`messages` with an incident.
    def get_incident_messages(self, incident_id: str) -> list[LoggedMessage]:
        return self.messages(incident_id)

    def get_message(self, message_id: str) -> LoggedMessage | None:
        """The accepted message with this id (or the last attempt with it, if none was)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT incident_id FROM messages WHERE message_id=? ORDER BY valid DESC, seq "
                "LIMIT 1",
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        found = [m for m in self.messages(row[0]) if m.message_id == message_id]
        accepted = [m for m in found if m.valid]
        return (accepted or found)[-1] if found else None

    def iter_trace(self, incident_id: str) -> Iterator[dict[str, Any]]:
        """Every attempt of an incident in log order, as plain records."""
        for m in self.messages(incident_id):
            yield m.as_record()

    def export_jsonl(self, incident_id: str | None = None) -> str:
        """One JSON line per message attempt (sorted keys): the shareable log."""
        rows = self.messages(incident_id)
        return "".join(json.dumps(m.as_record(), sort_keys=True) + "\n" for m in rows)

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

    def register_incident(self, meta: dict[str, Any], *, at: datetime, prefix: str = "INC") -> str:
        """Allocate the next sequential incident id (``INC-0001``...) and record it."""
        with self._lock:
            (count,) = self._conn.execute("SELECT COUNT(*) FROM incidents").fetchone()
            incident_id = f"{prefix}-{count + 1:04d}"
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

    def append_checkpoint(
        self, incident_id: str, kind: str, data: dict[str, Any], *, at: datetime
    ) -> None:
        """Durable workflow state (component 10): what a restarted process resumes from."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO checkpoints (incident_id, kind, created_at, data) VALUES (?,?,?,?)",
                (incident_id, kind, at.isoformat(), json.dumps(data, default=str)),
            )

    def checkpoints(self, incident_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind, created_at, data FROM checkpoints WHERE incident_id=? ORDER BY seq",
                (incident_id,),
            ).fetchall()
        return [{"kind": r[0], "at": r[1], "data": json.loads(r[2])} for r in rows]

    def append_approval(self, record: dict[str, Any]) -> None:
        """Record a human review decision (component 9). Append-only: never edited."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO approvals (incident_id, action_index, action, decision, reviewer,"
                " note, simulated_outcome, decided_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    record["incident_id"],
                    record["action_index"],
                    record["action"],
                    record["decision"],
                    record["reviewer"],
                    record["note"],
                    record.get("simulated_outcome"),
                    record["decided_at"],
                ),
            )

    def approvals(self, incident_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT action_index, action, decision, reviewer, note, simulated_outcome,"
                " decided_at FROM approvals WHERE incident_id=? ORDER BY seq",
                (incident_id,),
            ).fetchall()
        keys = (
            "action_index",
            "action",
            "decision",
            "reviewer",
            "note",
            "simulated_outcome",
            "decided_at",
        )
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def max_seq(self, incident_id: str) -> int:
        """Highest protocol ``seq`` stamped on an accepted message of the incident (0 if none)."""
        best = 0
        for m in self.messages(incident_id):
            if not m.valid:
                continue
            try:
                seq = json.loads(m.raw_json).get("seq")
            except (json.JSONDecodeError, AttributeError):
                continue
            if isinstance(seq, int):
                best = max(best, seq)
        return best

    def max_message_seq(self, incident_id: str) -> int:
        """Highest request sequence number used by an incident (to continue after restart)."""
        best = 0
        for m in self.messages(incident_id):
            mid = m.message_id or ""
            tail = mid.rsplit("-MSG-", 1)[-1] if "-MSG-" in mid else ""
            if tail.isdigit():
                best = max(best, int(tail))
        return best

    # ------------------------------------------------------------------ extension tables
    def add_tables(self, schema_sql: str, append_only: tuple[str, ...]) -> None:
        """Let a feature-flagged extension keep its own append-only tables in the same
        database without the core knowing their names (doc 02 §6 isolation)."""
        with self._lock:
            self._conn.executescript(schema_sql)
            for table in append_only:
                for op in ("UPDATE", "DELETE"):
                    self._conn.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} BEFORE {op} ON "
                        f"{table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"
                    )
                self._extension_tables.add(table)

    def insert_row(self, table: str, row: dict[str, Any]) -> None:
        if table not in self._extension_tables:
            raise ValueError(f"{table} is not a registered extension table")
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(row.values())
            )

    def rows(self, table: str) -> list[dict[str, Any]]:
        if table not in self._extension_tables:
            raise ValueError(f"{table} is not a registered extension table")
        with self._lock:
            cur = self._conn.execute(f"SELECT * FROM {table} ORDER BY seq")
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]

    def _execute_raw_for_tests(self, sql: str) -> None:
        """Run raw SQL. Private: tests use it to prove the append-only triggers fire. The
        public API has no update or delete method."""
        with self._lock:
            self._conn.execute(sql)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _payload_json(raw_json: str) -> str | None:
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    payload = data.get("payload") if isinstance(data, dict) else None
    return json.dumps(payload, sort_keys=True) if isinstance(payload, dict) else None
