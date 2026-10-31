"""Authority matrix and conversation rules (protocol upgrade, Prompt 4). Table-driven."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from netcoop.config.settings import load_settings
from netcoop.core.blocks import SelfAssessment, TimeWindow
from netcoop.core.guard import ConversationGuard, ConversationState, load_rules, rebuild_state
from netcoop.core.log_store import LogStore
from netcoop.core.messages import (
    AgentError,
    ClarificationRequest,
    ClarificationResponse,
    CommunityCandidate,
    Decision,
    Envelope,
    Finding,
    ReportReady,
    TaskRequest,
    make_message,
)
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.runner import load_scenario

T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)
W = TimeWindow(start=T0, end=T0)
INC = "INC-0001"
GUARD = ConversationGuard(max_clarification_rounds=2)
EMPTY_FINDING = Finding(
    observations=[], self_assessment=SelfAssessment(assessed_fraction=1, budget_exhausted=False)
)
REPORT = {
    "incident_id": INC,
    "status": "diagnosed",
    "suspected_root_cause": "x",
    "confidence": 0.5,
    "affected_devices": [],
    "supporting_evidence": [],
    "alternative_causes": [],
    "recommended_actions": [],
    "evidence_sources": [],
    "limitations": [],
}


def task(kind: str) -> TaskRequest:
    return TaskRequest(
        goal=kind, scope_entities=[], window=W, tool_budget=1, deadline_s=5, task_kind=kind
    )


def question(target: str = "performance_agent") -> ClarificationRequest:
    return ClarificationRequest(
        question_type="recheck_metric",
        target=target,  # type: ignore[arg-type]
        parameters={"entity": "SW_1", "metric": "latency_ms"},
        reason="conflict",
        round=1,
    )


def m(
    mid: str, sender: str, recipient: str, mtype: str, payload: Any, irt: str | None = None
) -> Envelope:
    return make_message(
        message_id=mid,
        incident_id=INC,
        sender=sender,  # type: ignore[arg-type]
        recipient=recipient,
        message_type=mtype,  # type: ignore[arg-type]
        payload=payload,
        sent_at=T0,
        in_reply_to=irt,
    )


# A complete, legal conversation in the app's real order, with the state at each step.
HAPPY: list[tuple[str, Envelope]] = [
    ("READY", m("M1", "orchestrator", "performance_agent", "task_request", task("investigate"))),
    ("COLLECTING", m("M1.R", "performance_agent", "orchestrator", "finding", EMPTY_FINDING, "M1")),
    (
        "CORRELATING",
        m("M2", "orchestrator", "correlation_agent", "task_request", task("correlate")),
    ),
    (
        "CORRELATING",
        m("M2.R", "correlation_agent", "orchestrator", "clarification_request", question(), "M2"),
    ),
    (
        "CLARIFYING",
        m("M3", "orchestrator", "performance_agent", "clarification_request", question(), "M2.R"),
    ),
    (
        "CLARIFYING",
        m(
            "M3.R",
            "performance_agent",
            "orchestrator",
            "clarification_response",
            ClarificationResponse(answered=True),
            "M3",
        ),
    ),
    (
        "CORRELATING",
        m("M4", "orchestrator", "correlation_agent", "task_request", task("correlate")),
    ),
    (
        "CORRELATING",
        m(
            "M4.R",
            "correlation_agent",
            "orchestrator",
            "decision",
            Decision(decision="diagnosed", ranked=[], margin=None),
            "M4",
        ),
    ),
    ("REPORTING", m("M5", "orchestrator", "reporting_agent", "task_request", task("report"))),
    (
        "REPORTING",
        m(
            "M5.R",
            "reporting_agent",
            "orchestrator",
            "report_ready",
            ReportReady(report=REPORT),
            "M5",
        ),
    ),
]


def run_until(n: int) -> ConversationState:
    """State after the first ``n`` HAPPY messages, each checked and accepted."""
    state = ConversationState()
    for incident_state, msg in HAPPY[:n]:
        state = state.with_incident_state(incident_state)
        result = GUARD.check(msg, state)
        assert result.allowed, (msg.message_id, result.violations)
        state = state.apply(msg)
    return state


def test_the_real_flow_is_accepted_end_to_end() -> None:
    final = run_until(len(HAPPY))
    assert final.decision_sent and final.report_sent and final.clarification_rounds == 1
    assert final.open_tasks == {} and final.relayed_questions == {}


# (description, accepted prefix length, incident state, message, extra guard kwargs, code)
REJECTED = [
    (
        "demo: performance_agent sends a decision",
        2,
        "CORRELATING",
        m(
            "X1",
            "performance_agent",
            "orchestrator",
            "decision",
            Decision(decision="diagnosed", ranked=[], margin=None),
            "M1",
        ),
        "SENDER_NOT_AUTHORIZED",
    ),
    (
        "task to a participant that takes another kind",
        0,
        "READY",
        m("X2", "orchestrator", "reporting_agent", "task_request", task("investigate")),
        "RECIPIENT_NOT_ALLOWED",
    ),
    (
        "finding addressed to another agent",
        1,
        "COLLECTING",
        m("X3", "performance_agent", "correlation_agent", "finding", EMPTY_FINDING, "M1"),
        "DIRECT_AGENT_MESSAGE_FORBIDDEN",
    ),
    (
        "finding that replies to an unknown message",
        1,
        "COLLECTING",
        m("X4", "performance_agent", "orchestrator", "finding", EMPTY_FINDING, "NOPE"),
        "REPLY_MISMATCH",
    ),
    (
        "finding to a task addressed to someone else",
        1,
        "COLLECTING",
        m("X5", "infrastructure_agent", "orchestrator", "finding", EMPTY_FINDING, "M1"),
        "REPLY_MISMATCH",
    ),
    (
        "second finding for an answered task",
        2,
        "COLLECTING",
        m("X6", "performance_agent", "orchestrator", "finding", EMPTY_FINDING, "M1"),
        "REPLY_MISMATCH",
    ),
    (
        "investigate task while correlating",
        2,
        "CORRELATING",
        m("X7", "orchestrator", "performance_agent", "task_request", task("investigate")),
        "MESSAGE_OUT_OF_SEQUENCE",
    ),
    (
        "decision while collecting",
        3,
        "COLLECTING",
        m(
            "X8",
            "correlation_agent",
            "orchestrator",
            "decision",
            Decision(decision="diagnosed", ranked=[], margin=None),
            "M2",
        ),
        "MESSAGE_OUT_OF_SEQUENCE",
    ),
    (
        "second decision",
        8,
        "CORRELATING",
        m(
            "X9",
            "correlation_agent",
            "orchestrator",
            "decision",
            Decision(decision="diagnosed", ranked=[], margin=None),
            "M4",
        ),
        "MESSAGE_OUT_OF_SEQUENCE",
    ),
    (
        "report before any decision",
        3,
        "REPORTING",
        m(
            "X10",
            "reporting_agent",
            "orchestrator",
            "report_ready",
            ReportReady(report=REPORT),
            "M2",
        ),
        "MESSAGE_OUT_OF_SEQUENCE",
    ),
    (
        "relay to an agent the question did not name",
        4,
        "CLARIFYING",
        m(
            "X11",
            "orchestrator",
            "infrastructure_agent",
            "clarification_request",
            question(),
            "M2.R",
        ),
        "REPLY_MISMATCH",
    ),
    (
        "answer from an agent that was not asked",
        5,
        "CLARIFYING",
        m(
            "X12",
            "infrastructure_agent",
            "orchestrator",
            "clarification_response",
            ClarificationResponse(answered=True),
            "M3",
        ),
        "REPLY_MISMATCH",
    ),
    (
        "a specialist asks a question",
        1,
        "COLLECTING",
        m("X13", "performance_agent", "orchestrator", "clarification_request", question(), "M1"),
        "SENDER_NOT_AUTHORIZED",
    ),
    (
        "duplicate message id",
        2,
        "COLLECTING",
        m(
            "M1.R",
            "performance_agent",
            "orchestrator",
            "agent_error",
            AgentError(code="AGENT_FAILED", message="x", recoverable=False),
            "M1",
        ),
        "DUPLICATE_MESSAGE",
    ),
    (
        "agent error about an unknown message",
        1,
        "COLLECTING",
        m(
            "X15",
            "performance_agent",
            "orchestrator",
            "agent_error",
            AgentError(code="AGENT_FAILED", message="x", recoverable=False),
            "NOPE",
        ),
        "REPLY_MISMATCH",
    ),
    (
        "message after the incident is closed",
        10,
        "COMPLETE",
        m(
            "X16",
            "orchestrator",
            "reporting_agent",
            "agent_error",
            AgentError(code="AGENT_FAILED", message="x", recoverable=False),
        ),
        "INCIDENT_CLOSED",
    ),
    (
        "community candidate with the extension off",
        0,
        "READY",
        m(
            "X17",
            "community_module",
            "orchestrator",
            "community_candidate",
            CommunityCandidate(
                candidate_id="CAND-0001",
                zone="Z",
                symptom_categories=[],
                window=W,
                complaint_count=1,
                distinct_reporters=1,
            ),
        ),
        "EXTENSION_DISABLED",
    ),
    (
        "self message",
        0,
        "READY",
        m(
            "X18",
            "orchestrator",
            "orchestrator",
            "agent_error",
            AgentError(code="AGENT_FAILED", message="x", recoverable=False),
        ),
        "RECIPIENT_NOT_ALLOWED",
    ),
]


@pytest.mark.parametrize(
    ("desc", "n", "state", "msg", "code"), REJECTED, ids=[r[0] for r in REJECTED]
)
def test_rejections(desc: str, n: int, state: str, msg: Envelope, code: str) -> None:
    before = run_until(n).with_incident_state(state)
    frozen_state, frozen_msg = before.model_dump_json(), msg.model_dump_json()
    result = GUARD.check(msg, before)
    assert not result.allowed
    assert result.violations[0].code == code, result.violations
    assert result.violations[0].reason.startswith("Rejected: ")
    # the guard never mutates its inputs
    assert before.model_dump_json() == frozen_state and msg.model_dump_json() == frozen_msg


def test_demo_sentence() -> None:
    msg = REJECTED[0][3]
    reason = GUARD.check(msg, run_until(2).with_incident_state("CORRELATING")).violations[0].reason
    assert (
        reason == "Rejected: only correlation_agent may send a decision; performance_agent tried."
    )


def test_every_rule_has_an_accepted_case() -> None:
    accepted = {(msg.message_type, msg.sender in ("orchestrator",)) for _, msg in HAPPY}
    extra = [
        m(
            "E1",
            "community_module",
            "orchestrator",
            "community_candidate",
            CommunityCandidate(
                candidate_id="CAND-0001",
                zone="Z",
                symptom_categories=[],
                window=W,
                complaint_count=1,
                distinct_reporters=1,
            ),
        ),
        m(
            "E2",
            "orchestrator",
            "performance_agent",
            "agent_error",
            AgentError(code="AGENT_TIMEOUT", message="late", recoverable=True),
            "M1",
        ),
        m(
            "E3",
            "performance_agent",
            "orchestrator",
            "agent_error",
            AgentError(code="AGENT_FAILED", message="x", recoverable=False),
            "M1",
        ),
    ]
    guard = ConversationGuard(extensions=["community_signals"])
    state = run_until(1).with_incident_state("COLLECTING")
    for msg in extra:
        assert guard.check(msg, state).allowed, msg.message_id
        accepted.add((msg.message_type, msg.sender == "orchestrator"))
    rules = load_rules()
    for row in rules.rows:
        assert (row.message_type, row.senders == ("orchestrator",)) in accepted, row


def test_clarification_round_limit() -> None:
    guard = ConversationGuard(max_clarification_rounds=1)
    state = run_until(6).with_incident_state("CORRELATING")  # one round used
    state = state.apply(HAPPY[6][1])  # a new correlate task (M4)
    q = m("Q2", "correlation_agent", "orchestrator", "clarification_request", question(), "M4")
    result = guard.check(q, state)
    assert [v.code for v in result.violations] == ["CLARIFICATION_LIMIT_EXCEEDED"]
    assert GUARD.check(q, state).allowed  # the default limit (2) allows a second round


def test_replay_is_deterministic_and_serializable() -> None:
    a = rebuild_state((msg for _, msg in HAPPY), incident_state="COMPLETE")
    b = rebuild_state((msg for _, msg in HAPPY), incident_state="COMPLETE")
    assert a == b and a.closed
    assert ConversationState.model_validate_json(a.model_dump_json()) == a


# ------------------------------------------------------------------ in real runs


def test_every_real_scenario_run_passes_the_guard(tmp_path: Path) -> None:
    from netcoop.scenarios.runner import list_scenarios

    store = LogStore(tmp_path / "all.sqlite3")
    for sid in list_scenarios():
        r = Orchestrator(store).run(load_scenario(sid).input_bytes)
        guard_codes = {msg.error_code for msg in store.messages(r.incident_id) if not msg.valid}
        assert not guard_codes & {
            "SENDER_NOT_AUTHORIZED",
            "RECIPIENT_NOT_ALLOWED",
            "MESSAGE_OUT_OF_SEQUENCE",
            "REPLY_MISMATCH",
            "DUPLICATE_MESSAGE",
            "INCIDENT_CLOSED",
            "CLARIFICATION_LIMIT_EXCEEDED",
        }, (sid, guard_codes)


def test_community_message_is_rejected_when_the_flag_is_off(tmp_path: Path) -> None:
    """Owner decision (Conflict 16, option a): with community_signals off, community input is
    rejected by the guard (EXTENSION_DISABLED), logged, and has no effect on the report."""
    assert load_settings().features.community_signals is False
    raw = load_scenario("S-02").input_bytes
    cand = {
        "candidate_id": "CAND-0001",
        "zone": "ZONE_HOSTEL_A",
        "entities": ["SW_CAMPUS_4"],
        "start": "2026-10-01T00:00:00Z",
        "end": "2026-12-01T00:00:00Z",
        "symptom_categories": ["disconnects"],
        "complaint_count": 2,
        "distinct_reporters": 2,
    }
    store = LogStore(tmp_path / "off.sqlite3")
    r = Orchestrator(store).run(raw, community=[cand])
    (rejected,) = [
        x for x in store.messages(r.incident_id) if x.message_type == "community_candidate"
    ]
    assert not rejected.valid and rejected.error_code == "EXTENSION_DISABLED"
    assert "community_signals extension, which is switched off" in (rejected.error_detail or "")
    ext = r.report["netcoop_extensions"]
    assert ext["community_signals"] == []
    assert any("EXTENSION_DISABLED" in lim for lim in r.report["limitations"])
    plain = Orchestrator(LogStore(tmp_path / "plain.sqlite3")).run(raw).report
    for key in ("status", "suspected_root_cause", "confidence", "affected_devices"):
        assert r.report[key] == plain[key]


def test_guard_rejection_in_a_real_run_is_logged_with_its_reason(tmp_path: Path) -> None:
    """Demo moment: inject a decision from performance_agent into a real incident's bus."""
    from netcoop.core.bus import GuardViolationError

    store = LogStore(tmp_path / "demo.sqlite3")
    o = Orchestrator(store)
    r = o.run(load_scenario("S-02").input_bytes, pause_after="CORRELATING")
    bus = o.last_bus
    assert bus is not None
    task_id = next(
        x.message_id
        for x in store.messages(r.incident_id)
        if x.message_type == "task_request" and x.recipient == "performance_agent"
    )
    forged = bus.build(
        sender="performance_agent",
        recipient="orchestrator",
        message_type="decision",
        incident_id=r.incident_id,
        in_reply_to=task_id,
        payload=Decision(decision="diagnosed", ranked=[], margin=None, abstention=None),
    )
    with pytest.raises(GuardViolationError) as exc:
        bus.transmit(forged)
    assert exc.value.code == "SENDER_NOT_AUTHORIZED"
    last = store.messages(r.incident_id)[-1]
    assert (last.valid, last.error_code) == (False, "SENDER_NOT_AUTHORIZED")
    assert "only correlation_agent may send a decision; performance_agent tried" in (
        last.error_detail or ""
    )
