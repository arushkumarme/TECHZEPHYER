"""Contract tests for the agent message protocol (doc 05). Families T-PROTO-*."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from netcoop.core.blocks import (
    EvidenceRef,
    Hypothesis,
    NotAssessableItem,
    Observation,
    SelfAssessment,
    TimeWindow,
    ToolCallRecord,
)
from netcoop.core.messages import (
    PAYLOAD_TYPES,
    PROTOCOL_VERSION,
    AgentError,
    ClarificationRequest,
    ClarificationResponse,
    CommunityCandidate,
    ConflictParty,
    ConflictReport,
    ConflictResponse,
    ConflictSide,
    Decision,
    Finding,
    MessageValidationError,
    ReportReady,
    TaskRequest,
    make_message,
    parse_message,
)

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 31, 12, 5, tzinfo=UTC)
WINDOW = TimeWindow(start=T0, end=T1)


def _obs() -> Observation:
    return Observation(
        observation_id="OBS-performance_agent-0001",
        entity="SW_CAMPUS_4",
        metric="latency_ms",
        metric_category="Latency",
        value=280.0,
        unit="millisecond",
        window=WINDOW,
        severity="critical",
        assessability="assessed",
        quality_flags=[],
        source_ref=["REC-0003"],
        agent="performance_agent",
    )


SAMPLE_PAYLOADS: dict[str, Any] = {
    "task_request": TaskRequest(
        goal="assess_performance",
        scope_entities=["SW_CAMPUS_4"],
        window=WINDOW,
        tool_budget=12,
        deadline_s=5.0,
    ),
    "finding": Finding(
        observations=[_obs()],
        hypotheses=[
            Hypothesis(
                hypothesis_id="HYP-performance_agent-0001",
                cause_type="link_congestion",
                entities=["SW_CAMPUS_4"],
                supporting_observation_ids=["OBS-performance_agent-0001"],
                local_score=0.6,
                rationale_code="HIGH_LATENCY_WITH_HIGH_UTILIZATION",
            )
        ],
        not_assessable=[
            NotAssessableItem(
                entity="SW_CAMPUS_4", metric="jitter_ms", reason="MISSING", detail="absent"
            )
        ],
        tool_calls=[
            ToolCallRecord(
                tool="telemetry_query",
                arguments={"entity": "SW_CAMPUS_4"},
                result_summary="5 records",
                at=T0,
            )
        ],
        self_assessment=SelfAssessment(assessed_fraction=0.8, budget_exhausted=False),
    ),
    "clarification_request": ClarificationRequest(
        question_type="what_if_cause",
        target="connectivity_agent",
        parameters={"entity": "SW_CAMPUS_1"},
        reason="narrow_margin",
        round=1,
    ),
    "clarification_response": ClarificationResponse(answered=True, result={"isolated": []}),
    "decision": Decision(decision="insufficient_evidence", ranked=[], margin=None),
    "report_ready": ReportReady(report={"incident_id": "INC-0001"}),
    "agent_error": AgentError(code="AGENT_TIMEOUT", message="late", recoverable=True),
    "community_candidate": CommunityCandidate(
        candidate_id="CAND-0001",
        zone="ZONE_HOSTEL_A",
        symptom_categories=["disconnects"],
        window=WINDOW,
        complaint_count=3,
        distinct_reporters=2,
    ),
    # protocol 1.2 (Prompt 8): sample data for the two new types (setup only)
    "conflict_report": ConflictReport(
        conflict_id="CONF-001",
        conflict_type="observation_contradiction",
        parties=[
            ConflictParty(
                agent="performance_agent",
                observation_ids=["OBS-PERF-000001-001", "OBS-PERF-000001-002"],
            )
        ],
        sides=[
            ConflictSide(
                agent="performance_agent",
                claim="latency_ms critical",
                evidence=[
                    EvidenceRef(
                        evidence_type="observation",
                        evidence_id="OBS-PERF-000001-001",
                        stance="supports",
                    )
                ],
            ),
            ConflictSide(
                agent="performance_agent",
                claim="latency_ms normal",
                evidence=[
                    EvidenceRef(
                        evidence_type="observation",
                        evidence_id="OBS-PERF-000001-002",
                        stance="supports",
                    )
                ],
            ),
        ],
        reason_code="CONFLICTING_READINGS",
        reason_text="SW_CAMPUS_1 latency_ms: readings disagree",
        proposed_rule="unresolved",
        effect_on_confidence="capped",
        target="performance_agent",
        recheck={
            "question_type": "recheck_metric",
            "entity": "SW_CAMPUS_1",
            "metric": "latency_ms",
        },
        round=1,
    ),
    "conflict_response": ConflictResponse(conflict_id="CONF-001", stance="cannot_assess"),
}

# conflict_response added with protocol 1.2 (Prompt 8; setup data)
RESPONSES = {"finding", "clarification_response", "decision", "report_ready", "conflict_response"}


def _build(mtype: str, **overrides: Any) -> dict[str, Any]:
    msg = make_message(
        message_id="MSG-000001",
        incident_id="INC-0001",
        sender="orchestrator" if mtype != "community_candidate" else "community_module",
        recipient="performance_agent" if mtype != "community_candidate" else "orchestrator",
        message_type=mtype,  # type: ignore[arg-type]
        payload=SAMPLE_PAYLOADS[mtype],
        sent_at=T0,
        in_reply_to="MSG-000000" if mtype in RESPONSES else None,
    )
    raw: dict[str, Any] = json.loads(msg.to_json())
    raw.update(overrides)
    return raw


def test_every_message_type_has_a_sample() -> None:
    assert set(SAMPLE_PAYLOADS) == set(PAYLOAD_TYPES)


@pytest.mark.parametrize("mtype", sorted(SAMPLE_PAYLOADS))
def test_round_trip(mtype: str) -> None:  # T-PROTO-01
    raw = _build(mtype)
    parsed = parse_message(json.dumps(raw))
    assert parsed.envelope.message_type == mtype
    assert parsed.payload == SAMPLE_PAYLOADS[mtype]
    assert parsed.ignored_fields == []
    assert json.loads(parsed.envelope.to_json()) == raw
    assert raw["protocol_version"] == PROTOCOL_VERSION


@pytest.mark.parametrize("field", ["message_id", "sender", "recipient", "sent_at", "payload"])
def test_missing_required_envelope_field_rejected(field: str) -> None:  # T-PROTO-02
    raw = _build("task_request")
    del raw[field]
    with pytest.raises(MessageValidationError) as exc:
        parse_message(raw)
    assert exc.value.code == "MESSAGE_INVALID"


def test_missing_required_payload_field_rejected() -> None:  # T-PROTO-03
    raw = _build("task_request")
    del raw["payload"]["scope_entities"]
    with pytest.raises(MessageValidationError, match="scope_entities"):
        parse_message(raw)


def test_unknown_fields_are_ignored_and_reported() -> None:  # T-PROTO-04
    raw = _build("finding", x_vendor="abc")
    raw["payload"]["x_extra"] = 1
    raw["payload"]["observations"][0]["x_note"] = "n"
    parsed = parse_message(raw)
    assert sorted(parsed.ignored_fields) == [
        "payload.observations[0].x_note",
        "payload.x_extra",
        "x_vendor",
    ]
    assert not hasattr(parsed.payload, "x_extra")


def test_payload_must_match_message_type() -> None:  # T-PROTO-05
    raw = _build("finding")
    raw["payload"] = _build("task_request")["payload"]
    with pytest.raises(MessageValidationError):
        parse_message(raw)


def test_naive_timestamp_rejected() -> None:  # T-PROTO-06
    raw = _build("task_request", sent_at="2026-10-31T12:00:00")
    with pytest.raises(MessageValidationError, match="timezone"):
        parse_message(raw)


@pytest.mark.parametrize("mtype", sorted(RESPONSES))
def test_response_requires_in_reply_to(mtype: str) -> None:  # T-PROTO-07
    raw = _build(mtype, in_reply_to=None)
    with pytest.raises(MessageValidationError, match="in_reply_to"):
        parse_message(raw)


def test_version_rules() -> None:  # T-PROTO-08
    minor = _build("task_request", protocol_version="1.7")
    assert parse_message(minor).envelope.protocol_version == "1.7"
    with pytest.raises(MessageValidationError) as exc:
        parse_message(_build("task_request", protocol_version="2.0"))
    assert exc.value.code == "PROTOCOL_VERSION_UNSUPPORTED"
    with pytest.raises(MessageValidationError) as exc2:
        parse_message(_build("task_request", payload_schema_version="3.1"))
    assert exc2.value.code == "PAYLOAD_SCHEMA_VERSION_UNSUPPORTED"
    with pytest.raises(MessageValidationError):
        parse_message(_build("task_request", protocol_version="one"))


def test_unknown_sender_rejected() -> None:  # T-PROTO-09
    with pytest.raises(MessageValidationError):
        parse_message(_build("task_request", sender="rogue_agent"))


def test_closed_enums_enforced() -> None:  # T-PROTO-10
    raw = _build("finding")
    raw["payload"]["observations"][0]["severity"] = "catastrophic"
    with pytest.raises(MessageValidationError):
        parse_message(raw)


def test_unparseable_json_rejected() -> None:
    with pytest.raises(MessageValidationError) as exc:
        parse_message("{not json")
    assert exc.value.code == "MESSAGE_INVALID"


def test_window_end_before_start_rejected() -> None:
    with pytest.raises(ValueError):
        TimeWindow(start=T1, end=T0)
