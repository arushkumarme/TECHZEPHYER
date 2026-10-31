"""Correlation + reporting agents and the report contract (T-AGT-CORR-*, T-RPT-*, doc 07).

The pipeline here is wired by hand (the orchestrator arrives in M8) but every message goes
through the real bus, and all data is real generator output ingested through M3.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from netcoop.agents.connectivity import ConnectivityAgent
from netcoop.agents.correlation import CorrelationAgent, correlation_context
from netcoop.agents.infrastructure import InfrastructureAgent
from netcoop.agents.performance import PerformanceAgent
from netcoop.agents.reporting import ReportingAgent, reporting_context
from netcoop.core.blocks import TimeWindow
from netcoop.core.bus import MessageBus
from netcoop.core.messages import (
    ClarificationRequest,
    Decision,
    Finding,
    ReportReady,
    TaskRequest,
    payload_as,
)
from netcoop.diagnosis.params import load_diagnosis_params
from netcoop.ingestion.models import NormalizedBundle
from netcoop.report.builder import OFFICIAL_KEYS, build_failure_report, strict_official
from netcoop.report.validate import validate_report

from .conftest import T0, generator_bundle, toolbox_for

P = load_diagnosis_params()
ALL = [f"SW_CAMPUS_{i}" for i in range(1, 11)]
WINDOW = TimeWindow(start=T0, end=T0 + timedelta(minutes=10))
SPECIALISTS = (PerformanceAgent, InfrastructureAgent, ConnectivityAgent)


def pipeline(
    bundle: NormalizedBundle,
    bus: MessageBus,
    *,
    skip: tuple[str, ...] = (),
    max_rounds: int = 2,
) -> tuple[Decision, dict[str, Any], str, dict[str, Finding]]:
    box = toolbox_for(bundle)
    agents = [cls(bus, lambda _i: box, P) for cls in SPECIALISTS]
    corr, rept = CorrelationAgent(bus, P), ReportingAgent(bus)
    for a in [*agents, corr, rept]:
        bus.register(a.agent_id, a.handle)
    findings: dict[str, Finding] = {}
    for a in agents:
        if a.agent_id in skip:
            continue
        r = bus.request(
            sender="orchestrator",
            recipient=a.agent_id,
            message_type="task_request",
            payload=TaskRequest(
                goal=a.goal, scope_entities=ALL, window=WINDOW, tool_budget=30, deadline_s=5
            ),
            incident_id="INC-0001",
        )
        findings[a.agent_id] = payload_as(r, Finding)
    clarifications: list[dict[str, Any]] = []
    for rnd in range(1, max_rounds + 2):
        ctx = correlation_context(
            bundle,
            findings,
            missing_agents=[
                a
                for a in ("performance_agent", "infrastructure_agent", "connectivity_agent")
                if a in skip
            ],
            clarifications=clarifications,
            round_no=rnd,
            max_rounds=max_rounds,
        )
        r = bus.request(
            sender="orchestrator",
            recipient="correlation_agent",
            message_type="task_request",
            payload=TaskRequest(
                goal="correlate",
                scope_entities=ALL,
                window=WINDOW,
                tool_budget=0,
                deadline_s=5,
                context=ctx,
            ),
            incident_id="INC-0001",
        )
        if r.envelope.message_type == "decision":
            decision = payload_as(r, Decision)
            break
        q = payload_as(r, ClarificationRequest)
        ans = bus.request(
            sender="orchestrator",
            recipient=q.target,
            message_type="clarification_request",
            payload=q,
            incident_id="INC-0001",
        )
        clarifications.append(
            {"request": q.model_dump(mode="json"), "response": ans.envelope.payload}
        )
    else:  # pragma: no cover
        pytest.fail("correlation never decided")
    rep = bus.request(
        sender="orchestrator",
        recipient="reporting_agent",
        message_type="task_request",
        payload=TaskRequest(
            goal="report",
            scope_entities=ALL,
            window=WINDOW,
            tool_budget=0,
            deadline_s=5,
            context=reporting_context("INC-0001", bundle, decision, findings, mode="simulation"),
        ),
        incident_id="INC-0001",
    )
    ready = payload_as(rep, ReportReady)
    return decision, ready.report, ready.markdown or "", findings


def obs_ids(findings: dict[str, Finding]) -> set[str]:
    return {o.observation_id for f in findings.values() for o in f.observations}


# ------------------------------------------------------------------ correlation


def test_hardware_failure_end_to_end(make_bus: Callable[[], MessageBus]) -> None:
    d, report, md, findings = pipeline(
        generator_bundle({"SW_CAMPUS_4": "hardware_failure"}), make_bus()
    )
    assert d.decision == "diagnosed"
    assert report["status"] == "diagnosed"
    assert report["affected_devices"] == ["SW_CAMPUS_4"]
    assert report["suspected_root_cause"].startswith("Likely device / hardware failure")
    assert set(report["evidence_sources"]) >= {"infrastructure_agent", "performance_agent"}
    assert (
        validate_report(report, observation_ids=obs_ids(findings), finding_agents=set(findings))
        == []
    )
    assert "Simulated data" in md


def test_latency_spike_end_to_end(make_bus: Callable[[], MessageBus]) -> None:
    d, report, _, _ = pipeline(generator_bundle({"SW_CAMPUS_4": "latency_spike"}), make_bus())
    top = next(h for h in d.ranked if h.diagnosable)
    assert top.cause_type == "link_congestion"
    assert report["status"] in ("diagnosed", "insufficient_evidence")


def test_normal_end_to_end(make_bus: Callable[[], MessageBus]) -> None:
    _, report, _, _ = pipeline(generator_bundle(), make_bus())
    assert report["status"] == "no_fault_detected"
    assert report["affected_devices"] == []
    assert report["suspected_root_cause"].startswith("No fault detected")
    ext = report["netcoop_extensions"]
    assert any(n["metric"] == "interface_errors" for n in ext["not_assessable"])


def test_missing_specialist_is_a_limitation(make_bus: Callable[[], MessageBus]) -> None:
    d, report, _, _ = pipeline(
        generator_bundle({"SW_CAMPUS_4": "hardware_failure"}),
        make_bus(),
        skip=("connectivity_agent",),
    )
    assert any("connectivity_agent" in lim for lim in report["limitations"])
    assert d.ranked[0].ceiling < 0.95


# ------------------------------------------------------------------ report contract (doc 07)


def test_official_keys_exact_and_typed(make_bus: Callable[[], MessageBus]) -> None:  # T-RPT-SCHEMA
    _, report, _, _ = pipeline(generator_bundle({"SW_CAMPUS_4": "latency_spike"}), make_bus())
    assert list(report)[:10] == list(OFFICIAL_KEYS)
    assert set(report) == {*OFFICIAL_KEYS, "netcoop_extensions"}
    strict = strict_official(report)
    assert list(strict) == list(OFFICIAL_KEYS)
    assert isinstance(strict["confidence"], float)
    for e in strict["supporting_evidence"]:
        assert set(e) == {"metric", "value", "interpretation"}
        assert isinstance(e["value"], int | float | str)
    json.dumps(strict)  # serializable


def test_evidence_traces_to_observations(make_bus: Callable[[], MessageBus]) -> None:  # T-RPT-EVID
    _, report, _, findings = pipeline(
        generator_bundle({"SW_CAMPUS_4": "hardware_failure"}), make_bus()
    )
    trace = report["netcoop_extensions"]["evidence_trace"]
    assert len(trace) == len(report["supporting_evidence"])
    assert {t["observation_id"] for t in trace} <= obs_ids(findings)
    assert all(t["source_ref"] for t in trace)


def test_actions_adapt_to_uncertainty(make_bus: Callable[[], MessageBus]) -> None:  # T-RPT-ACT
    _, diag, _, _ = pipeline(generator_bundle({"SW_CAMPUS_4": "hardware_failure"}), make_bus())
    bundle = generator_bundle({"SW_CAMPUS_4": "hardware_failure", "SW_CAMPUS_6": "latency_spike"})
    _, other, _, _ = pipeline(bundle, make_bus(), max_rounds=0)
    status = diag["netcoop_extensions"]["recommendation_status"]
    assert all(r["requires_human_approval"] and r["simulated"] for r in status)
    assert all(r["approval_state"] == "pending" for r in status)
    assert diag["netcoop_extensions"]["recommendation_mode"] == "corrective"
    if other["status"] == "insufficient_evidence":
        assert other["netcoop_extensions"]["recommendation_mode"] == "diagnostic_next_steps"
        assert other["suspected_root_cause"].startswith("Undetermined")


def test_no_forbidden_wording(make_bus: Callable[[], MessageBus]) -> None:  # doc 12 §1
    _, report, md, _ = pipeline(generator_bundle({"SW_CAMPUS_4": "latency_spike"}), make_bus())
    text = (json.dumps(report) + md).lower()
    for word in ("calibrated", "exact root cause", "real-time", "live monitoring", "remediated"):
        assert word not in text, word
    assert report["netcoop_extensions"]["confidence_method"] == "heuristic"
    assert report["netcoop_extensions"]["mode"] == "simulation"


def test_failure_report_for_rejected_input() -> None:
    r = build_failure_report(
        "INC-0009",
        ["INPUT_UNPARSEABLE: not valid JSON"],
        mode="simulation",
        provenance="unspecified",
    )
    assert r["status"] == "failed" and r["confidence"] == 0.0
    assert r["affected_devices"] == [] and r["supporting_evidence"] == []
    assert any("INPUT_UNPARSEABLE" in lim for lim in r["limitations"])
    assert validate_report(r, observation_ids=set(), finding_agents=set()) == []


def test_validator_catches_violations() -> None:
    r = build_failure_report("INC-1", ["x"], mode="simulation", provenance="p")
    bad = dict(r)
    bad["extra_key"] = 1
    bad["evidence_sources"] = ["community_module"]
    errors = validate_report(bad, observation_ids=set(), finding_agents=set())
    assert any("extra_key" in e for e in errors)
    assert any("community_module" in e for e in errors)
    del bad["status"]
    assert any(
        "status" in e for e in validate_report(bad, observation_ids=set(), finding_agents=set())
    )


def _two_candidate_bundle() -> NormalizedBundle:
    """TEAM-AUTHORED variant (doc 05 §6.4): generator `normal` records, mutated so that
    SW_CAMPUS_4 shows an interface-fault signature and SW_CAMPUS_6 a CPU-overload one."""
    from netcoop.ingestion.normalize import ingest

    from .conftest import GEN

    records = []
    for k in range(3):
        for n in range(1, 11):
            rec = GEN.generate("normal", seed=100 + 10 * k + n, at=T0 + timedelta(minutes=5 * k))
            rec["device_id"] = f"SW_CAMPUS_{n}"
            if n == 4:
                rec["metrics"].update(interface_errors=250, packet_loss_pct=12.0)
            if n == 6:
                rec["metrics"].update(cpu_utilization_pct=97.0, latency_ms=180.0, queue_drops=40)
            records.append(rec)
    raw = {"records": records, "provenance": "team-authored", "topology_ref": "campus_v1"}
    bundle = ingest(json.dumps(raw)).bundle
    assert bundle is not None
    return bundle


def test_narrow_margin_triggers_bounded_clarification(make_bus: Callable[[], MessageBus]) -> None:
    bus = make_bus()
    d, report, _, _ = pipeline(_two_candidate_bundle(), bus, max_rounds=2)
    asked = [m for m in bus.store.messages("INC-0001") if m.message_type == "clarification_request"]
    assert asked, "a narrow margin must trigger at least one clarification"
    assert 1 <= len(d.clarifications) <= 2
    signatures = {(c.question_type, c.target, c.summary) for c in d.clarifications}
    assert len(signatures) == len(d.clarifications)  # never the same question twice
    assert report["status"] == "insufficient_evidence"
    assert report["suspected_root_cause"].startswith("Undetermined")
    assert report["netcoop_extensions"]["clarifications"]


def test_round_limit_zero_records_unanswered_question(make_bus: Callable[[], MessageBus]) -> None:
    d, report, _, _ = pipeline(_two_candidate_bundle(), make_bus(), max_rounds=0)
    assert d.clarifications == []
    assert any("Clarification limit" in lim for lim in report["limitations"])


def test_separate_issue_is_not_silently_dropped(make_bus: Callable[[], MessageBus]) -> None:
    bundle = generator_bundle({"SW_CAMPUS_4": "hardware_failure", "SW_CAMPUS_6": "latency_spike"})
    _, report, _, _ = pipeline(bundle, make_bus())
    assert report["affected_devices"] == ["SW_CAMPUS_4"]
    assert any("SW_CAMPUS_6" in lim and "separate" in lim for lim in report["limitations"])
