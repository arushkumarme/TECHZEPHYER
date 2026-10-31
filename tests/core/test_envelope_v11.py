"""Protocol 1.1: optional snapshot/mode/provenance/seq envelope fields, version rules,
never-raising parser, ID validators (protocol upgrade, Prompt 2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from netcoop.core.blocks import SelfAssessment, TimeWindow
from netcoop.core.ids import IdFactory, validate_id
from netcoop.core.messages import (
    PROTOCOL_VERSION,
    Finding,
    MessageValidationError,
    TaskRequest,
    make_message,
    parse_message,
)
from netcoop.core.parse import DEFAULT_MAX_MESSAGE_BYTES, try_parse

T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)
TASK = TaskRequest(
    goal="assess_performance",
    scope_entities=["SW_CAMPUS_1"],
    window=TimeWindow(start=T0, end=T0),
    tool_budget=3,
    deadline_s=1,
)


def raw(**over: Any) -> dict[str, Any]:
    msg = make_message(
        message_id="INC-0001-MSG-000001",
        incident_id="INC-0001",
        sender="orchestrator",
        recipient="performance_agent",
        message_type="task_request",
        payload=TASK,
        sent_at=T0,
    )
    d: dict[str, Any] = json.loads(msg.to_json())
    d.update(over)
    return {k: v for k, v in d.items() if v is not ...}


V11 = {
    "snapshot_id": "SNAP-0123456789ab",
    "mode": "simulation",
    "data_provenance": "synthetic-generator",
    "seq": 7,
}


# ------------------------------------------------------------------ versions and compatibility


def test_current_version_is_1_1() -> None:
    assert PROTOCOL_VERSION == "1.1"


def test_a_1_0_message_without_new_fields_still_parses() -> None:
    old = raw(protocol_version="1.0")
    for k in V11:
        old.pop(k, None)
    p = parse_message(old)
    assert p.envelope.snapshot_id is None and p.envelope.seq is None
    assert p.warnings == []


def test_1_1_fields_round_trip() -> None:
    p = parse_message(raw(**V11))
    assert (
        p.envelope.snapshot_id,
        p.envelope.mode,
        p.envelope.data_provenance,
        p.envelope.seq,
    ) == ("SNAP-0123456789ab", "simulation", "synthetic-generator", 7)
    assert json.loads(p.envelope.to_json())["seq"] == 7


@pytest.mark.parametrize(
    ("version", "accepted", "warned"),
    [
        ("1.1", True, False),
        ("1.0", True, False),
        ("1.9", True, True),
        ("2.0", False, False),
        ("0.9", False, False),
    ],
)
def test_version_matrix(version: str, accepted: bool, warned: bool) -> None:
    r = try_parse(raw(protocol_version=version, x_future_field=1))
    assert (r.message is not None) is accepted
    if accepted:
        codes = {w.code for w in r.warnings}
        assert ("PROTOCOL_MINOR_NEWER" in codes) is warned
        assert "FIELD_IGNORED" in codes
    else:
        assert [e.code for e in r.errors] == ["PROTOCOL_VERSION_UNSUPPORTED"]


# ------------------------------------------------------------------ envelope validation


@pytest.mark.parametrize("mode", ["deployment", "live", "Simulation", ""])
def test_any_mode_but_simulation_is_refused(mode: str) -> None:
    with pytest.raises(MessageValidationError) as exc:
        parse_message(raw(mode=mode))
    assert exc.value.code == "MODE_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("snapshot_id", "SNAP-xyz"),
        ("snapshot_id", "SNAP-0123456789AB"),
        ("seq", 0),
        ("data_provenance", "verified-iitbbs"),
        ("data_provenance", "made-up"),
    ],
)
def test_new_fields_are_validated(field: str, value: Any) -> None:
    r = try_parse(raw(**{field: value}))
    assert r.message is None
    assert r.errors[0].path.startswith(field)


def test_naive_timestamp_and_unknown_participant() -> None:
    r = try_parse(raw(sent_at="2026-11-01T09:00:00"))
    assert r.message is None and r.errors[0].path == "sent_at"
    r2 = try_parse(raw(sender="rogue_agent"))
    assert r2.errors[0].code == "UNKNOWN_TERM" and r2.errors[0].path == "sender"
    assert "rogue_agent" in r2.errors[0].reason


# ------------------------------------------------------------------ never-raising parser


@pytest.mark.parametrize(
    "bad",
    ["{not json", "[1, 2]", "42", b"\xff\xfe", None, 3.5],
)
def test_try_parse_never_raises(bad: Any) -> None:
    r = try_parse(bad)
    assert r.message is None and r.errors
    assert r.errors[0].code == "MESSAGE_INVALID"


def test_oversize_message_rejected() -> None:
    big = raw()
    big["payload"]["goal"] = "x" * (DEFAULT_MAX_MESSAGE_BYTES + 1)
    r = try_parse(json.dumps(big))
    assert [e.code for e in r.errors] == ["MESSAGE_TOO_LARGE"]
    assert try_parse(json.dumps(raw()), max_bytes=100).errors[0].code == "MESSAGE_TOO_LARGE"
    with pytest.raises(MessageValidationError) as exc:
        parse_message(json.dumps(raw()), max_bytes=100)
    assert exc.value.code == "MESSAGE_TOO_LARGE"


def test_payload_errors_carry_the_field_path() -> None:
    d = raw()
    d["payload"]["tool_budget"] = -1
    r = try_parse(d)
    assert r.errors[0].path == "payload.tool_budget"


def test_telemetry_is_never_carried_in_messages() -> None:
    """Design rule (doc 05 §1): agents exchange references, not data. Telemetry-like extra
    fields are ignored and reported, never accepted into the message."""
    finding = Finding(
        observations=[], self_assessment=SelfAssessment(assessed_fraction=1, budget_exhausted=False)
    )
    msg = make_message(
        message_id="M.R",
        in_reply_to="M",
        incident_id="INC-0001",
        sender="performance_agent",
        recipient="orchestrator",
        message_type="finding",
        payload=finding,
        sent_at=T0,
    )
    d = json.loads(msg.to_json())
    d["payload"]["records"] = [{"device_id": "SW_CAMPUS_1", "metrics": {"latency_ms": 9}}]
    d["payload"]["metrics"] = {"latency_ms": 9}
    r = try_parse(d)
    assert r.message is not None
    ignored = {w.path for w in r.warnings if w.code == "FIELD_IGNORED"}
    assert {"payload.records", "payload.metrics"} <= ignored
    assert "records" not in r.message.payload.model_dump()


# ------------------------------------------------------------------ IDs


@pytest.mark.parametrize(
    ("kind", "value", "ok"),
    [
        ("incident", "INC-0001", True),
        ("incident", "INC-1", False),
        ("message", "INC-0001-MSG-000003", True),
        ("message", "INC-0001-MSG-000003.R", True),
        ("message", "MSG-000001", True),
        ("message", "OBS-0001", False),
        ("observation", "OBS-PERF-000003-001", True),
        ("observation", "HYP-1", False),
        ("hypothesis", "HYP-INFRA-000002-001", True),
        ("record", "REC-0001", True),
        ("snapshot", "SNAP-0123456789ab", True),
        ("snapshot", "SNAP-123", False),
        ("candidate", "CAND-0001", True),
        ("conflict", "CONF-001", True),
        ("recommendation", "RCM-0001", True),
        ("task", "TASK-0001", True),
        ("clarification", "CLR-0001", True),
        ("decision", "DEC-0001", True),
    ],
)
def test_id_validators(kind: str, value: str, ok: bool) -> None:
    assert validate_id(kind, value) is ok


def test_ids_are_deterministic_and_unknown_kind_rejected() -> None:
    a, b = IdFactory(namespace="INC-0001"), IdFactory(namespace="INC-0001")
    assert [a.message() for _ in range(3)] == [b.message() for _ in range(3)]
    with pytest.raises(KeyError):
        validate_id("banana", "X-1")


def test_incident_prefix_is_configurable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from netcoop.config.settings import load_settings
    from netcoop.core.log_store import LogStore
    from netcoop.orchestrator.workflow import Orchestrator
    from netcoop.scenarios.runner import load_scenario

    s = load_settings()
    custom = s.model_copy(
        update={"protocol": s.protocol.model_copy(update={"incident_prefix": "NCI"})}
    )
    store = LogStore(tmp_path / "p.sqlite3")
    r = Orchestrator(store, settings=custom).run(load_scenario("S-01").input_bytes)
    assert r.incident_id == "NCI-0001" and validate_id("incident", r.incident_id)
    assert all(validate_id("message", m.message_id or "") for m in store.messages(r.incident_id))
    assert load_settings().protocol.incident_prefix == "INC"
