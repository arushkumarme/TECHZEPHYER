"""Specialist agents stand-alone (T-AGT-*, T-AGT-BEHAV-*, doc 03 §1 checklist)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from netcoop.agents.connectivity import ConnectivityAgent
from netcoop.agents.infrastructure import InfrastructureAgent
from netcoop.agents.performance import PerformanceAgent
from netcoop.core.blocks import TimeWindow
from netcoop.core.bus import MessageBus
from netcoop.core.messages import (
    ClarificationRequest,
    ClarificationResponse,
    Finding,
    TaskRequest,
    payload_as,
)
from netcoop.diagnosis.params import load_diagnosis_params
from netcoop.ingestion.models import NormalizedBundle

from .conftest import T0, generator_bundle, toolbox_for

P = load_diagnosis_params()
ALL = [f"SW_CAMPUS_{i}" for i in range(1, 11)]
WINDOW = TimeWindow(start=T0, end=T0 + timedelta(minutes=10))


def run(
    agent_cls: type,
    bundle: NormalizedBundle,
    bus: MessageBus,
    *,
    scope: list[str] = ALL,
    budget: int = 30,
    topology: bool = True,
) -> Finding:
    box = toolbox_for(bundle, topology=topology)
    agent = agent_cls(bus, lambda incident: box, P)
    bus.register(agent.agent_id, agent.handle)
    reply = bus.request(
        sender="orchestrator",
        recipient=agent.agent_id,
        message_type="task_request",
        payload=TaskRequest(
            goal=agent.goal,
            scope_entities=scope,
            window=WINDOW,
            tool_budget=budget,
            deadline_s=5,
        ),
        incident_id="INC-0001",
    )
    assert reply.envelope.message_type == "finding"
    return payload_as(reply, Finding)


def obs_for(f: Finding, entity: str, metric: str) -> list[str]:
    return [o.severity for o in f.observations if o.entity == entity and o.metric == metric]


# ------------------------------------------------------------------ performance agent


def test_performance_normal(make_bus: Callable[[], MessageBus]) -> None:
    f = run(PerformanceAgent, generator_bundle(), make_bus())
    assert {o.severity for o in f.observations} == {"normal"}
    assert {o.agent for o in f.observations} == {"performance_agent"}
    assert f.hypotheses == []
    assert f.self_assessment.assessed_fraction == 1.0


def test_performance_spike_finds_anomaly_and_investigates(
    make_bus: Callable[[], MessageBus],
) -> None:
    normal = run(PerformanceAgent, generator_bundle(), make_bus())
    spike = run(PerformanceAgent, generator_bundle({"SW_CAMPUS_4": "latency_spike"}), make_bus())
    assert obs_for(spike, "SW_CAMPUS_4", "latency_ms") == ["critical"]
    assert "link_congestion" in {h.cause_type for h in spike.hypotheses}
    # T-AGT-BEHAV-03: the investigation path differs by scenario (deep dive on anomaly).
    assert len(spike.tool_calls) > len(normal.tool_calls)
    deep = [c for c in spike.tool_calls if c.arguments.get("entities") == ["SW_CAMPUS_4"]]
    assert deep, [c.arguments for c in spike.tool_calls]


def test_performance_pattern_and_traceability(make_bus: Callable[[], MessageBus]) -> None:
    f = run(PerformanceAgent, generator_bundle({"SW_CAMPUS_4": "latency_spike"}), make_bus())
    (o,) = [x for x in f.observations if x.entity == "SW_CAMPUS_4" and x.metric == "latency_ms"]
    assert o.source_ref and all(r.startswith("REC-") for r in o.source_ref)
    assert "pattern:sustained" in o.quality_flags
    assert o.unit == "millisecond"


def test_performance_abstains_on_missing_metric(make_bus: Callable[[], MessageBus]) -> None:
    # hardware_failure records carry no jitter_ms (OBSERVED in the generator).
    f = run(PerformanceAgent, generator_bundle({"SW_CAMPUS_4": "hardware_failure"}), make_bus())
    assert obs_for(f, "SW_CAMPUS_4", "jitter_ms") == []
    na = [n for n in f.not_assessable if n.entity == "SW_CAMPUS_4" and n.metric == "jitter_ms"]
    assert na and na[0].reason == "MISSING"  # never "normal" (T-AGT-BEHAV-05)
    assert f.self_assessment.assessed_fraction < 1.0


def test_performance_respects_scope(make_bus: Callable[[], MessageBus]) -> None:
    f = run(PerformanceAgent, generator_bundle(), make_bus(), scope=["SW_CAMPUS_2"])
    assert {o.entity for o in f.observations} == {"SW_CAMPUS_2"}  # T-AGT-BEHAV-01


def test_budget_exhaustion_is_reported(make_bus: Callable[[], MessageBus]) -> None:
    f = run(
        PerformanceAgent, generator_bundle({"SW_CAMPUS_4": "latency_spike"}), make_bus(), budget=1
    )
    assert len(f.tool_calls) == 1  # T-AGT-BEHAV-02
    assert f.self_assessment.budget_exhausted
    assert any(lim.code == "TOOL_BUDGET_EXHAUSTED" for lim in f.limitations)


def test_independent_finding_is_reproducible(make_bus: Callable[[], MessageBus]) -> None:
    bundle = generator_bundle({"SW_CAMPUS_4": "latency_spike"})
    a = run(PerformanceAgent, bundle, make_bus())
    b = run(PerformanceAgent, bundle, make_bus())
    assert a.model_dump(exclude={"tool_calls"}) == b.model_dump(exclude={"tool_calls"})


# ------------------------------------------------------------------ infrastructure agent


def test_infrastructure_hardware_failure(make_bus: Callable[[], MessageBus]) -> None:
    f = run(InfrastructureAgent, generator_bundle({"SW_CAMPUS_4": "hardware_failure"}), make_bus())
    assert obs_for(f, "SW_CAMPUS_4", "status") == ["critical"]
    assert obs_for(f, "SW_CAMPUS_4", "interface_errors") == ["critical"]
    assert {"device_failure", "interface_fault", "device_overload"} <= {
        h.cause_type for h in f.hypotheses
    }
    # interface_errors is not produced by the normal profile -> not assessable elsewhere
    na = {(n.entity, n.metric) for n in f.not_assessable}
    assert ("SW_CAMPUS_1", "interface_errors") in na


def test_infrastructure_unknown_status_is_not_healthy(make_bus: Callable[[], MessageBus]) -> None:
    bundle = generator_bundle()
    records = [
        r.model_copy(update={"status": None}) if r.entity == "SW_CAMPUS_3" else r
        for r in bundle.records
    ]
    states = dict(bundle.metric_states)
    from netcoop.ingestion.models import MetricState

    states[("SW_CAMPUS_3", "status")] = MetricState(
        assessability="not_assessable", reason="MISSING"
    )
    patched = bundle.model_copy(update={"records": records, "metric_states": states})
    f = run(InfrastructureAgent, patched, make_bus())
    (o,) = [x for x in f.observations if x.entity == "SW_CAMPUS_3" and x.metric == "status"]
    assert (o.severity, o.assessability, o.value) == ("unknown", "not_assessable", None)


# ------------------------------------------------------------------ connectivity agent


def test_connectivity_facts_and_what_if(make_bus: Callable[[], MessageBus]) -> None:
    f = run(ConnectivityAgent, generator_bundle({"SW_CAMPUS_2": "hardware_failure"}), make_bus())
    assert f.facts["topology_available"] is True
    assert f.facts["topology_provenance"] == "SIMULATED"
    assert f.facts["paths"]["SW_CAMPUS_4"] == ["SW_CAMPUS_4", "SW_CAMPUS_2", "SW_CAMPUS_1"]
    wi = f.facts["what_if"]["SW_CAMPUS_2"]
    assert wi["isolated"] == ["SW_CAMPUS_10", "SW_CAMPUS_4", "SW_CAMPUS_5"]
    assert wi["degraded"] == ["SW_CAMPUS_3", "SW_CAMPUS_8"]
    assert f.facts["zones"]["SW_CAMPUS_4"] == "ZONE_HOSTEL_A"
    assert any(t.tool == "what_if_failure" for t in f.tool_calls)
    assert f.self_assessment.assessed_fraction == 1.0


def test_connectivity_without_topology(make_bus: Callable[[], MessageBus]) -> None:
    f = run(ConnectivityAgent, generator_bundle(topology=False), make_bus(), topology=False)
    assert f.facts["topology_available"] is False
    assert f.facts["paths"] == {}
    assert any(n.reason == "NO_TOPOLOGY" for n in f.not_assessable)
    assert any(lim.code == "TOPOLOGY_MISSING" for lim in f.limitations)
    assert f.self_assessment.assessed_fraction == 0.0


# ------------------------------------------------------------------ clarifications


def _clarify(agent_cls: type, bundle: NormalizedBundle, bus: MessageBus, req: ClarificationRequest):  # type: ignore[no-untyped-def]
    box = toolbox_for(bundle)
    agent = agent_cls(bus, lambda incident: box, P)
    bus.register(agent.agent_id, agent.handle)
    reply = bus.request(
        sender="orchestrator",
        recipient=agent.agent_id,
        message_type="clarification_request",
        payload=req,
        incident_id="INC-0001",
    )
    assert reply.envelope.message_type == "clarification_response"
    return payload_as(reply, ClarificationResponse)


def test_connectivity_answers_what_if(make_bus: Callable[[], MessageBus]) -> None:
    r = _clarify(
        ConnectivityAgent,
        generator_bundle(),
        make_bus(),
        ClarificationRequest(
            question_type="what_if_cause",
            target="connectivity_agent",
            parameters={"entity": "SW_CAMPUS_3"},
            reason="narrow_margin",
            round=1,
        ),
    )
    assert r.answered and r.result is not None
    assert r.result["isolated"] == ["SW_CAMPUS_6", "SW_CAMPUS_7", "SW_CAMPUS_9"]


def test_performance_rechecks_metric(make_bus: Callable[[], MessageBus]) -> None:
    r = _clarify(
        PerformanceAgent,
        generator_bundle({"SW_CAMPUS_4": "latency_spike"}),
        make_bus(),
        ClarificationRequest(
            question_type="recheck_metric",
            target="performance_agent",
            parameters={"entity": "SW_CAMPUS_4", "metric": "latency_ms"},
            reason="conflict",
            round=1,
        ),
    )
    assert r.answered and [o.severity for o in r.observations] == ["critical"]


def test_unanswerable_question_is_declined(make_bus: Callable[[], MessageBus]) -> None:
    r = _clarify(
        InfrastructureAgent,
        generator_bundle(),
        make_bus(),
        ClarificationRequest(
            question_type="what_if_cause",
            target="infrastructure_agent",
            parameters={"entity": "SW_CAMPUS_3"},
            reason="narrow_margin",
            round=1,
        ),
    )
    assert not r.answered and r.reason
