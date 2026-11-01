"""Message bus and append-only log, protocol 1.1 (protocol upgrade, Prompt 5)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from netcoop.core.blocks import SelfAssessment, TimeWindow
from netcoop.core.bus import GuardViolationError, MessageBus
from netcoop.core.guard import ConversationGuard
from netcoop.core.ids import FixedClock, IdFactory
from netcoop.core.log_store import LogStore
from netcoop.core.messages import (
    Decision,
    Envelope,
    Finding,
    MessageValidationError,
    ParsedMessage,
    TaskRequest,
)
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.runner import load_scenario

T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)
INC = "INC-0001"
TASK = TaskRequest(
    goal="x",
    scope_entities=[],
    tool_budget=1,
    deadline_s=5,
    window=TimeWindow(start=T0, end=T0),
    task_kind="investigate",
)
FINDING = Finding(
    observations=[], self_assessment=SelfAssessment(assessed_fraction=1, budget_exhausted=False)
)


def make_bus(store: LogStore, state: str = "COLLECTING") -> MessageBus:
    return MessageBus(
        store,
        clock=FixedClock(T0, timedelta(seconds=1)),
        ids=IdFactory(namespace=INC),
        guard=ConversationGuard(),
        incident_state=lambda _: state,
    )


def test_accepted_message_is_delivered_once_in_order_and_logged(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "a.sqlite3")
    bus = make_bus(store)
    got: list[str] = []

    def perf(msg: ParsedMessage) -> Envelope:
        got.append(msg.envelope.message_id)
        return bus.reply(msg, message_type="finding", payload=FINDING)

    bus.register("performance_agent", perf)
    for _ in range(2):
        bus.request(
            sender="orchestrator",
            recipient="performance_agent",
            message_type="task_request",
            payload=TASK,
            incident_id=INC,
        )
    assert got == ["INC-0001-MSG-000001", "INC-0001-MSG-000002"]
    rows = store.get_incident_messages(INC)
    assert [(r.attempt_seq, r.verdict, r.message_type) for r in rows] == [
        (1, "accepted", "task_request"),
        (2, "accepted", "finding"),
        (3, "accepted", "task_request"),
        (4, "accepted", "finding"),
    ]
    # built at T0 (sent_at), received one clock tick later
    assert rows[0].received_at == (T0 + timedelta(seconds=1)).isoformat()
    assert rows[0].payload_json is not None


def test_invalid_and_guard_rejected_messages_are_logged_not_delivered(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "r.sqlite3")
    bus = make_bus(store, state="CORRELATING")
    delivered: list[str] = []
    bus.register_listener("orchestrator", lambda m: delivered.append(m.envelope.message_id))
    with pytest.raises(MessageValidationError):
        bus.transmit(
            '{"protocol_version": "1.1", "payload_schema_version": "1.0", '
            '"incident_id": "INC-0001"}'
        )
    forged = bus.build(
        sender="performance_agent",
        recipient="orchestrator",
        message_type="decision",
        incident_id=INC,
        in_reply_to="NOPE",
        payload=Decision(decision="diagnosed", ranked=[], margin=None),
    )
    with pytest.raises(GuardViolationError):
        bus.transmit(forged)
    assert delivered == []
    bad_parse, bad_guard = store.get_incident_messages(INC)
    assert (bad_parse.attempt_seq, bad_guard.attempt_seq) == (1, 2)
    assert bad_parse.verdict == bad_guard.verdict == "rejected"
    assert bad_parse.violations and all(
        v["code"] == "MESSAGE_INVALID" for v in bad_parse.violations
    )
    assert {v["path"] for v in bad_parse.violations} >= {"message_id", "sender"}
    assert bad_guard.violations[0] == {
        "code": "SENDER_NOT_AUTHORIZED",
        "path": "",
        "reason": "Rejected: only correlation_agent may send a decision; performance_agent tried.",
    }


def test_warnings_are_logged(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "w.sqlite3")
    bus = make_bus(store)
    msg = json.loads(
        bus.build(
            sender="orchestrator",
            recipient="performance_agent",
            message_type="task_request",
            payload=TASK,
            incident_id=INC,
        ).to_json()
    )
    msg["protocol_version"], msg["x_extra"] = "1.4", 1
    bus.transmit(json.dumps(msg))
    (row,) = store.get_incident_messages(INC)
    assert {w["code"] for w in row.warnings} == {"PROTOCOL_MINOR_NEWER", "FIELD_IGNORED"}


def test_seq_is_monotonic_and_duplicates_are_rejected(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "d.sqlite3")
    bus = make_bus(store)
    sent = bus.transmit(
        bus.build(
            sender="orchestrator",
            recipient="performance_agent",
            message_type="task_request",
            payload=TASK,
            incident_id=INC,
        )
    )
    with pytest.raises(GuardViolationError) as exc:
        bus.transmit(sent.envelope.model_copy(update={"seq": None}))
    assert exc.value.code == "DUPLICATE_MESSAGE"
    rows = store.get_incident_messages(INC)
    assert [r.attempt_seq for r in rows] == [1, 2]
    assert [r.protocol_seq for r in rows] == [1, None]


def test_replay_with_the_same_clock_and_ids_gives_an_identical_log(tmp_path: Path) -> None:
    def run(name: str) -> str:
        store = LogStore(tmp_path / name)
        from netcoop.config.settings import load_settings

        s = load_settings()
        seq = s.model_copy(
            update={
                "orchestration": s.orchestration.model_copy(update={"parallel_specialists": False})
            }
        )
        o = Orchestrator(store, settings=seq, clock=FixedClock(T0, timedelta(milliseconds=5)))
        r = o.run(load_scenario("S-09").input_bytes)
        return store.export_jsonl(r.incident_id)

    a, b = run("a.sqlite3"), run("b.sqlite3")
    assert a == b and a.count("\n") > 10
    first = json.loads(a.splitlines()[0])
    assert first["seq"] == 1 and first["verdict"] == "accepted" and first["snapshot_id"]


def test_rebuild_state_from_the_log_equals_the_live_state(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "s.sqlite3")
    o = Orchestrator(store)
    r = o.run(load_scenario("S-09").input_bytes)  # with clarification rounds
    bus = o.last_bus
    assert bus is not None
    live = bus.conversation(r.incident_id)
    rebuilt = bus.rebuild_state(r.incident_id)
    assert rebuilt == live
    assert rebuilt.decision_sent and rebuilt.report_sent and rebuilt.clarification_rounds >= 1
    assert rebuilt.incident_state == "AWAITING_REVIEW" and not rebuilt.closed


def test_read_api_returns_referenced_messages(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "q.sqlite3")
    o = Orchestrator(store)
    r = o.run(load_scenario("S-02").input_bytes)
    bus = o.last_bus
    assert bus is not None
    findings = bus.messages_for(r.incident_id, types=("finding",))
    assert len(findings) == 3
    correlate = next(
        m
        for m in bus.messages_for(r.incident_id, types=["task_request"])
        if m.envelope.recipient == "correlation_agent"
    )
    refs = correlate.envelope.payload["input_message_ids"]
    resolved = [bus.get_message(i) for i in refs]
    assert all(x is not None and x.envelope.message_type == "finding" for x in resolved)
    assert bus.get_message("INC-9999-MSG-000001") is None
    before = store.export_jsonl(r.incident_id)
    bus.messages_for(r.incident_id)
    assert store.export_jsonl(r.incident_id) == before  # reading changes nothing


def test_the_log_store_has_no_update_or_delete(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "n.sqlite3")
    public = [n for n in dir(store) if not n.startswith("_")]
    forbidden = ("update", "delete", "remove", "clear", "drop", "truncate", "edit", "replace")
    assert not [n for n in public if any(w in n.lower() for w in forbidden)], public
    store.append(raw_json="{}", header={"incident_id": INC}, valid=False, error_code="X")
    for sql in (
        "UPDATE messages SET verdict='accepted'",
        "DELETE FROM messages",
        "DELETE FROM schema_migrations",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            store._execute_raw_for_tests(sql)


def test_subscribers_only_receive_messages_addressed_to_them(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "sub.sqlite3")
    bus = make_bus(store)
    seen: dict[str, list[str]] = {"performance_agent": [], "infrastructure_agent": []}
    for agent in seen:

        def handler(msg: ParsedMessage, agent: str = agent) -> Envelope:
            seen[agent].append(msg.envelope.recipient)
            return bus.reply(msg, message_type="finding", payload=FINDING)

        bus.register(agent, handler)  # type: ignore[arg-type]
    bus.request(
        sender="orchestrator",
        recipient="performance_agent",
        message_type="task_request",
        payload=TASK,
        incident_id=INC,
    )
    assert seen == {"performance_agent": ["performance_agent"], "infrastructure_agent": []}


# ------------------------------------------------------------------ migration (#20)

OLD_SCHEMA = """
CREATE TABLE messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT, message_id TEXT,
    in_reply_to TEXT, sender TEXT, recipient TEXT, message_type TEXT, sent_at TEXT,
    valid INTEGER NOT NULL, error_code TEXT, error_detail TEXT,
    ignored_fields TEXT NOT NULL, raw_json TEXT NOT NULL
);
CREATE TRIGGER messages_no_update BEFORE UPDATE ON messages
BEGIN SELECT RAISE(ABORT, 'messages is append-only'); END;
CREATE TRIGGER messages_no_delete BEFORE DELETE ON messages
BEGIN SELECT RAISE(ABORT, 'messages is append-only'); END;
"""


def test_an_old_format_log_database_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    old_msg = {
        "protocol_version": "1.0",
        "message_id": "INC-0001-MSG-000001",
        "payload": {"goal": "x"},
    }
    conn.execute(
        "INSERT INTO messages (incident_id, message_id, sender, recipient, message_type,"
        " valid, ignored_fields, raw_json) VALUES (?,?,?,?,?,?,?,?)",
        (
            INC,
            "INC-0001-MSG-000001",
            "orchestrator",
            "performance_agent",
            "task_request",
            1,
            "[]",
            json.dumps(old_msg),
        ),
    )
    conn.execute(
        "INSERT INTO messages (incident_id, message_id, valid, error_code,"
        " error_detail, ignored_fields, raw_json) VALUES (?,?,?,?,?,?,?)",
        (INC, "BAD", 0, "MESSAGE_INVALID", "not JSON", "[]", "{nope"),
    )
    conn.commit()
    conn.close()

    store = LogStore(path)  # opening migrates
    assert "messages_v2_protocol_1_1" in store.migrations()
    old, bad = store.get_incident_messages(INC)
    assert (old.attempt_seq, old.verdict, old.payload_json) == (1, "accepted", '{"goal": "x"}')
    assert (bad.attempt_seq, bad.verdict) == (2, "rejected")
    assert bad.violations == [{"code": "MESSAGE_INVALID", "reason": "not JSON", "path": ""}]
    store.append(raw_json="{}", header={"incident_id": INC}, valid=False, error_code="X")
    assert store.get_incident_messages(INC)[-1].attempt_seq == 3
    with pytest.raises(sqlite3.IntegrityError):
        store._execute_raw_for_tests("UPDATE messages SET verdict='accepted'")
    store.close()
    again = LogStore(path)  # idempotent
    assert again.migrations() == ["messages_v2_protocol_1_1"]
    assert len(again.get_incident_messages(INC)) == 3
