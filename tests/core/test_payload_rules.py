"""Payload models and the seven semantic rules (protocol upgrade, Prompt 3)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from netcoop.core.blocks import (
    Abstention,
    EntityRef,
    EvidenceRef,
    Hypothesis,
    Observation,
    Recommendation,
    ScoredHypothesis,
    TimeWindow,
)
from netcoop.core.messages import (
    AgentError,
    ClarificationRequest,
    ClarificationResponse,
    Decision,
    ReportReady,
    TaskRequest,
    make_message,
)
from netcoop.core.parse import try_parse
from netcoop.report.official import OfficialReport

T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)
W = TimeWindow(start=T0, end=T0)
REPO = Path(__file__).resolve().parents[2]


def obs(**over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "observation_id": "OBS-PERF-000001-001",
        "entity": "SW_CAMPUS_1",
        "metric": "latency_ms",
        "metric_category": "Latency",
        "value": 12.5,
        "unit": "millisecond",
        "window": W.model_dump(mode="json"),
        "severity": "normal",
        "assessability": "assessed",
        "agent": "performance_agent",
    }
    d.update(over)
    return d


def hyp(**over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "hypothesis_id": "HYP-PERF-000001-001",
        "cause_type": "link_congestion",
        "entities": ["SW_CAMPUS_1"],
        "supporting_observation_ids": ["OBS-PERF-000001-001"],
        "local_score": 0.7,
        "rationale_code": "HIGH_UTIL_WITH_DROPS",
    }
    d.update(over)
    return d


def code_of(exc: ValidationError) -> str:
    return str(exc.errors()[0]["type"])


# ------------------------------------------------------------------ rule 1: not assessable


def test_rule1_not_assessable_has_no_value_unknown_severity_and_a_reason() -> None:
    ok = Observation.model_validate(
        obs(
            value=None,
            severity="unknown",
            assessability="not_assessable",
            not_assessable_reason="MISSING",
            unit="none",
            metric="status",
        )
    )
    assert ok.not_assessable_reason == "MISSING"
    for bad in (
        obs(
            value=3,
            severity="unknown",
            assessability="not_assessable",
            not_assessable_reason="MISSING",
        ),
        obs(
            value=None,
            severity="normal",
            assessability="not_assessable",
            not_assessable_reason="MISSING",
        ),
        obs(value=None, severity="unknown", assessability="not_assessable"),
    ):
        with pytest.raises(ValidationError) as exc:
            Observation.model_validate(bad)
        assert code_of(exc.value) == "ASSESSABILITY_VALUE_MISMATCH"


def test_rule1_an_assessed_observation_must_have_a_value() -> None:
    with pytest.raises(ValidationError) as exc:
        Observation.model_validate(obs(value=None))
    assert code_of(exc.value) == "ASSESSABILITY_VALUE_MISMATCH"


# ------------------------------------------------------------------ rule 2: units


def test_rule2_declared_unit_must_exist_and_fit_the_metric() -> None:
    Observation.model_validate(obs(unit="millisecond"))
    Observation.model_validate(obs(unit=""))  # no unit declared: not checked
    for unit in ("percent", "furlong"):
        with pytest.raises(ValidationError) as exc:
            Observation.model_validate(obs(unit=unit))
        assert code_of(exc.value) == "UNIT_INCOMPATIBLE"
    Observation.model_validate(obs(metric="cpu_pct", unit="percent", value=40))


def test_new_observation_fields_are_vocabulary_checked() -> None:
    o = Observation.model_validate(
        obs(aggregation="worst_by_severity", sample_count=3, baseline_ref="performance.latency_ms")
    )
    assert o.sample_count == 3
    with pytest.raises(ValidationError):
        Observation.model_validate(obs(aggregation="median"))
    with pytest.raises(ValidationError):
        Observation.model_validate(obs(sample_count=-1))


# ------------------------------------------------------------------ rule 3: hypotheses


def test_rule3_hypothesis_needs_support_or_missing_evidence() -> None:
    Hypothesis.model_validate(hyp())
    Hypothesis.model_validate(
        hyp(supporting_observation_ids=[], missing_expected_evidence=["egress_queue_drops"])
    )
    with pytest.raises(ValidationError) as exc:
        Hypothesis.model_validate(hyp(supporting_observation_ids=[]))
    assert code_of(exc.value) == "HYPOTHESIS_WITHOUT_EVIDENCE"


def test_rule3_stances_must_match_their_list() -> None:
    wrong = [
        {
            "evidence_type": "observation",
            "evidence_id": "OBS-PERF-000001-001",
            "stance": "contradicts",
        }
    ]
    with pytest.raises(ValidationError) as exc:
        Hypothesis.model_validate(hyp(supporting=wrong))
    assert code_of(exc.value) == "EVIDENCE_STANCE_MISMATCH"


def test_evidence_refs_are_derived_from_1_0_id_lists_and_must_agree() -> None:
    h = Hypothesis.model_validate(hyp(contradicting_observation_ids=["OBS-INFRA-000002-001"]))
    assert [(r.evidence_type, r.evidence_id, r.stance) for r in h.supporting] == [
        ("observation", "OBS-PERF-000001-001", "supports")
    ]
    assert h.contradicting[0].stance == "contradicts"
    # refs only (a 1.1 sender): the id lists are filled from them
    h2 = Hypothesis.model_validate(
        hyp(
            supporting_observation_ids=[],
            supporting=[
                {
                    "evidence_type": "observation",
                    "evidence_id": "OBS-X-000001-001",
                    "stance": "supports",
                }
            ],
        )
    )
    assert h2.supporting_observation_ids == ["OBS-X-000001-001"]
    with pytest.raises(ValidationError) as exc:
        Hypothesis.model_validate(
            hyp(
                supporting=[
                    {
                        "evidence_type": "observation",
                        "evidence_id": "OBS-OTHER-000001-001",
                        "stance": "supports",
                    }
                ]
            )
        )
    assert code_of(exc.value) == "EVIDENCE_REFS_DISAGREE"


# ------------------------------------------------------------------ rule 4: score methods


def test_rule4_scores_carry_their_method_and_calibrated_is_blocked() -> None:
    assert Hypothesis.model_validate(hyp()).score_method == "agent_local_heuristic"
    assert Decision(decision="diagnosed", ranked=[], margin=None).score_method == "heuristic"
    sh = ScoredHypothesis(
        cause_type="link_congestion",
        entities=[],
        score=0.5,
        support=0.5,
        contradiction=0,
        corroboration=0,
        ceiling=1,
    )
    assert sh.score_method == "heuristic"
    with pytest.raises(ValidationError) as exc:
        Hypothesis.model_validate(hyp(score_method="calibrated"))
    assert "is blocked" in str(exc.value)
    with pytest.raises(ValidationError):
        Decision(decision="diagnosed", ranked=[], margin=None, score_method="calibrated")


# ------------------------------------------------------------------ rule 5: evidence prefixes


@pytest.mark.parametrize(
    ("etype", "eid", "ok"),
    [
        ("observation", "OBS-PERF-000001-001", True),
        ("observation", "HYP-1", False),
        ("hypothesis", "HYP-INFRA-000002-001", True),
        ("normalized_record", "REC-0004", True),
        ("normalized_record", "RCM-0001", False),
        ("community_report", "CAND-0001", True),
        ("tool_result", "anything", True),
    ],
)
def test_rule5_evidence_id_prefix_matches_type(etype: str, eid: str, ok: bool) -> None:
    data = {"evidence_type": etype, "evidence_id": eid, "stance": "supports"}
    if ok:
        EvidenceRef.model_validate(data)
    else:
        with pytest.raises(ValidationError) as exc:
            EvidenceRef.model_validate(data)
        assert code_of(exc.value) == "EVIDENCE_PREFIX_MISMATCH"


def test_evidence_strength_bounds_and_entity_ref() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(
            evidence_type="observation", evidence_id="OBS-1", stance="supports", strength=1.5
        )
    assert EntityRef(entity_type="device", entity_id="SW_CAMPUS_1").entity_id == "SW_CAMPUS_1"
    with pytest.raises(ValidationError):
        EntityRef(entity_type="router", entity_id="SW_CAMPUS_1")
    with pytest.raises(ValidationError):
        EntityRef(entity_type="device", entity_id="")


# ------------------------------------------------------------------ rule 6: recommendations


def rcm(**over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "recommendation_id": "RCM-0001",
        "action_text": "Inspect the uplink",
        "kind": "corrective",
        "target_entities": ["SW_CAMPUS_4"],
        "reason": "Likely link congestion",
        "priority": "high",
        "verification_step": "Re-run the diagnosis on fresh simulated data",
    }
    d.update(over)
    return d


def test_rule6_recommendations_are_always_simulated_and_need_approval() -> None:
    r = Recommendation.model_validate(rcm())
    assert r.requires_human_approval is True and r.simulated is True
    for field in ("requires_human_approval", "simulated"):
        with pytest.raises(ValidationError) as exc:
            Recommendation.model_validate(rcm(**{field: False}))
        assert code_of(exc.value) == "RECOMMENDATION_SAFETY_VIOLATION"
    with pytest.raises(ValidationError):
        Recommendation.model_validate(rcm(recommendation_id="REC-0001"))
    with pytest.raises(ValidationError):
        Recommendation.model_validate(rcm(priority="urgent"))


# ------------------------------------------------------------------ rule 7: official report


def pdf_example() -> dict[str, Any]:
    text = (REPO / "docs" / "07-report-spec.md").read_text(encoding="utf-8")
    block = re.search(r"## 1\. The official report.*?```json\n(.*?)```", text, re.S)
    assert block is not None
    return dict(json.loads(block.group(1)))


def test_rule7_the_pdf_example_validates_and_an_eleventh_key_does_not() -> None:
    example = pdf_example()
    report = OfficialReport.model_validate(example)
    assert list(report.model_dump()) == list(example)
    with pytest.raises(ValidationError) as exc:
        OfficialReport.model_validate({**example, "severity": "high"})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"
    for key in example:
        with pytest.raises(ValidationError):
            OfficialReport.model_validate({k: v for k, v in example.items() if k != key})
    with pytest.raises(ValidationError):
        OfficialReport.model_validate({**example, "confidence": True})
    with pytest.raises(ValidationError):
        OfficialReport.model_validate({**example, "confidence": 1.2})


def test_validate_report_uses_the_official_model() -> None:
    from netcoop.report.validate import validate_report

    bad = {**pdf_example(), "affected_devices": "SW_1"}
    errors = validate_report(
        bad, observation_ids=set(), finding_agents={"performance_agent", "infrastructure_agent"}
    )
    assert any("affected_devices" in e for e in errors)


# ------------------------------------------------------------------ decisions and abstention


def test_abstention_required_for_insufficient_and_forbidden_for_diagnosed() -> None:
    d = Decision(
        decision="insufficient_evidence",
        ranked=[],
        margin=None,
        gate_checks={"score_at_least_tau": False, "diagnosable": True},
    )
    assert d.abstention is not None and d.abstention.reasons == ["below_score_threshold"]
    with pytest.raises(ValidationError) as exc:
        Decision.model_validate(
            {"decision": "insufficient_evidence", "ranked": [], "margin": None, "abstention": None}
        )
    assert code_of(exc.value) == "ABSTENTION_MISMATCH"
    with pytest.raises(ValidationError) as exc:
        Decision(
            decision="diagnosed",
            ranked=[],
            margin=None,
            abstention=Abstention(reasons=["ambiguous_margin"]),
        )
    assert code_of(exc.value) == "ABSTENTION_MISMATCH"
    with pytest.raises(ValidationError):
        Abstention(reasons=["because"])


# ------------------------------------------------------------------ other payloads


def test_task_request_new_fields() -> None:
    t = TaskRequest(
        goal="correlate",
        scope_entities=[],
        window=W,
        tool_budget=0,
        deadline_s=60,
        task_id="TASK-0004",
        task_kind="correlate",
        input_message_ids=["INC-0001-MSG-000002.R"],
        incident_context={"trigger": "telemetry_bundle", "description": "S-02"},
    )
    assert t.incident_context is not None and t.incident_context.trigger == "telemetry_bundle"
    for bad in (
        {"task_id": "T-1"},
        {"task_kind": "dance"},
        {"incident_context": {"trigger": "rumour"}},
    ):
        with pytest.raises(ValidationError):
            TaskRequest.model_validate({**t.model_dump(mode="json"), **bad})


def test_clarification_ids_answerable_and_parameters() -> None:
    req = ClarificationRequest(
        question_type="recheck_metric",
        target="performance_agent",
        parameters={"entity": "SW_1", "metric": "latency_ms"},
        reason="conflict",
        round=1,
        clarification_id="CLR-0101",
    )
    assert req.clarification_id == "CLR-0101"
    with pytest.raises(ValidationError) as exc:
        ClarificationRequest(
            question_type="recheck_metric",
            target="performance_agent",
            parameters={"entity": "SW_1"},
            reason="conflict",
            round=1,
        )
    assert code_of(exc.value) == "CLARIFICATION_PARAMETERS_INVALID"
    assert ClarificationResponse(answered=True).answerable == "yes"
    assert ClarificationResponse(answered=False).answerable == "no"
    assert ClarificationResponse(answered=True, answerable="partial").answerable == "partial"
    with pytest.raises(ValidationError) as exc:
        ClarificationResponse(answered=False, answerable="yes")
    assert code_of(exc.value) == "CLARIFICATION_ANSWER_MISMATCH"


def test_agent_error_and_report_ready_new_fields() -> None:
    e = AgentError(
        code="AGENT_TIMEOUT",
        message="late",
        recoverable=True,
        related_message_id="INC-0001-MSG-000002",
        details={"deadline_s": 5},
    )
    assert e.details["deadline_s"] == 5
    rr = ReportReady(report=pdf_example(), recommendations=[Recommendation.model_validate(rcm())])
    assert rr.recommendations[0].simulated is True


def test_semantic_rule_codes_reach_the_parser_with_paths() -> None:
    from netcoop.core.blocks import SelfAssessment
    from netcoop.core.messages import Finding

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
    d["payload"]["observations"] = [obs(value=None)]
    r = try_parse(d)
    assert r.errors[0].code == "ASSESSABILITY_VALUE_MISMATCH"
    assert r.errors[0].path == "payload.observations.0"
    d["payload"]["observations"] = [obs(unit="percent")]
    assert try_parse(d).errors[0].code == "UNIT_INCOMPATIBLE"


def test_round_trip_of_every_new_model() -> None:
    models = [
        Observation.model_validate(obs(aggregation="max", sample_count=2)),
        Hypothesis.model_validate(hyp()),
        Recommendation.model_validate(rcm()),
        Decision(
            decision="insufficient_evidence",
            ranked=[],
            margin=None,
            gate_checks={"margin_at_least_delta": False},
        ),
        OfficialReport.model_validate(pdf_example()),
    ]
    for m in models:
        again = type(m).model_validate_json(m.model_dump_json())
        assert again == m


def test_official_model_keys_equal_the_builder_keys() -> None:
    from netcoop.report.builder import OFFICIAL_KEYS
    from netcoop.report.official import OFFICIAL_REPORT_KEYS

    assert tuple(OFFICIAL_KEYS) == OFFICIAL_REPORT_KEYS
    assert list(OFFICIAL_REPORT_KEYS) == list(pdf_example())


def test_every_scenario_report_validates_as_official_report() -> None:
    from netcoop.core.log_store import LogStore
    from netcoop.scenarios.runner import list_scenarios, load_scenario, run_scenario

    store = LogStore(":memory:")
    for sid in list_scenarios():
        report = run_scenario(load_scenario(sid), store).report
        OfficialReport.model_validate(
            {k: v for k, v in report.items() if k != "netcoop_extensions"}
        )
