"""Message bus and append-only log store (T-PROTO-BUS-*, T-LOG-*)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from netcoop.core.blocks import SelfAssessment, TimeWindow
from netcoop.core.bus import BusRoutingError, MessageBus
from netcoop.core.ids import FixedClock, IdFactory
from netcoop.core.log_store import LogStore
from netcoop.core.messages import (
    AgentError,
    Envelope,
    Finding,
    MessageValidationError,
    ParsedMessage,
    TaskRequest,
)

T0 = datetime(2026, 10, 31, 12, tzinfo=UTC)
TASK = TaskRequest(
    goal="assess_performance",
    scope_entities=["SW_CAMPUS_1"],
    window=TimeWindow(start=T0, end=T0 + timedelta(minutes=5)),
    tool_budget=5,
    deadline_s=2.0,
)
EMPTY_FINDING = Finding(
    observations=[], self_assessment=SelfAssessment(assessed_fraction=0, budget_exhausted=False)
)


@pytest.fixture
def bus(tmp_path: Path) -> MessageBus:
    store = LogStore(tmp_path / "log.sqlite3")
    return MessageBus(store, clock=FixedClock(T0, timedelta(seconds=1)), ids=IdFactory())


def _echo_finding(bus: MessageBus) -> Callable[[ParsedMessage], Envelope]:
    def handler(msg: ParsedMessage) -> Envelope:
        return bus.reply(msg, message_type="finding", payload=EMPTY_FINDING)

    return handler


def _ask(bus: MessageBus, recipient: str = "performance_agent") -> ParsedMessage:
    return bus.request(
        sender="orchestrator",
        recipient=recipient,  # type: ignore[arg-type]
        message_type="task_request",
        payload=TASK,
        incident_id="INC-0001",
    )


def test_request_response_is_validated_logged_and_delivered(bus: MessageBus) -> None:
    bus.register("performance_agent", _echo_finding(bus))
    reply = _ask(bus)
    assert reply.envelope.message_type == "finding"
    logged = bus.store.messages("INC-0001")
    assert [m.message_type for m in logged] == ["task_request", "finding"]
    assert logged[0].seq < logged[1].seq
    assert logged[1].in_reply_to == logged[0].message_id
    assert all(m.valid for m in logged)
    # The log holds the exact wire JSON, re-parseable for replay.
    assert json.loads(logged[0].raw_json)["payload"]["goal"] == "assess_performance"


def test_invalid_reply_is_logged_and_rejected(bus: MessageBus) -> None:
    bus.register("performance_agent", lambda msg: '{"protocol_version": "1.0"}')
    with pytest.raises(MessageValidationError) as exc:
        _ask(bus)
    assert exc.value.code == "MESSAGE_INVALID"
    last = bus.store.messages()[-1]
    assert last.valid is False
    assert last.error_code == "MESSAGE_INVALID"


def test_reply_must_reference_the_request(bus: MessageBus) -> None:
    def wrong_ref(msg: ParsedMessage) -> Envelope:
        env = bus.reply(msg, message_type="finding", payload=EMPTY_FINDING)
        return env.model_copy(update={"in_reply_to": "MSG-999999"})

    bus.register("performance_agent", wrong_ref)
    with pytest.raises(MessageValidationError, match="in_reply_to"):
        _ask(bus)
    assert bus.store.messages("INC-0001")[-1].valid is False


def test_agents_cannot_message_each_other_directly(bus: MessageBus) -> None:
    bus.register("performance_agent", _echo_finding(bus))
    with pytest.raises(BusRoutingError):
        bus.request(
            sender="correlation_agent",
            recipient="performance_agent",
            message_type="task_request",
            payload=TASK,
            incident_id="INC-0001",
        )


def test_unregistered_recipient(bus: MessageBus) -> None:
    with pytest.raises(BusRoutingError, match="no handler"):
        _ask(bus, recipient="reporting_agent")


def test_ignored_fields_are_recorded(bus: MessageBus) -> None:
    def extra(msg: ParsedMessage) -> str:
        raw = json.loads(bus.reply(msg, message_type="finding", payload=EMPTY_FINDING).to_json())
        raw["payload"]["x_debug"] = True
        return json.dumps(raw)

    bus.register("performance_agent", extra)
    reply = _ask(bus)
    assert reply.ignored_fields == ["payload.x_debug"]
    assert bus.store.messages("INC-0001")[-1].ignored_fields == ["payload.x_debug"]


def test_log_is_append_only(bus: MessageBus) -> None:
    bus.register("performance_agent", _echo_finding(bus))
    _ask(bus)
    bus.store.append_transition("INC-0001", None, "RECEIVED", trigger="test", at=T0)
    for stmt in (
        "UPDATE messages SET sender='x'",
        "DELETE FROM messages",
        "UPDATE transitions SET to_state='x'",
        "DELETE FROM transitions",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            bus.store._execute_raw_for_tests(stmt)


def test_transitions_and_persistence_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "log.sqlite3"
    store = LogStore(path)
    store.append_transition("INC-0001", None, "RECEIVED", trigger="cli", at=T0)
    store.append_transition("INC-0001", "RECEIVED", "VALIDATING", trigger="auto", at=T0)
    store.close()
    reopened = LogStore(path)
    states = [(t.from_state, t.to_state) for t in reopened.transitions("INC-0001")]
    assert states == [(None, "RECEIVED"), ("RECEIVED", "VALIDATING")]
    assert reopened.incident_ids() == ["INC-0001"]


def test_notify_one_way_message(bus: MessageBus) -> None:
    received: list[str] = []
    bus.register_listener("orchestrator", lambda m: received.append(m.envelope.message_type))
    bus.notify(
        sender="performance_agent",
        recipient="orchestrator",
        message_type="agent_error",
        payload=AgentError(code="AGENT_FAILED", message="boom", recoverable=False),
        incident_id="INC-0001",
    )
    assert received == ["agent_error"]
    assert bus.store.messages("INC-0001")[0].message_type == "agent_error"


def test_unparseable_wire_text_is_logged(bus: MessageBus) -> None:
    with pytest.raises(MessageValidationError):
        bus.transmit("{broken")
    last = bus.store.messages()[-1]
    assert (last.valid, last.raw_json) == (False, "{broken")


def test_malformed_reply_is_attributed_to_the_request(bus: MessageBus) -> None:
    bus.register("performance_agent", lambda msg: '{"protocol_version": "1.0"}')
    with pytest.raises(MessageValidationError):
        _ask(bus)
    bad = bus.store.messages("INC-0001")[-1]
    assert (bad.valid, bad.sender, bad.recipient) == (False, "performance_agent", "orchestrator")
    assert bad.in_reply_to == bus.store.messages("INC-0001")[0].message_id
