"""Diagnosis knowledge: catalog, scoring, ceiling, gate, conflicts (T-DIAG-*, doc 08).

Observations here are SYNTHETIC TEST FIXTURES expressed as severities; end-to-end runs on
generator data come in M9.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from netcoop.config.fields import load_field_dictionary
from netcoop.core.blocks import Observation, TimeWindow
from netcoop.core.messages import Decision
from netcoop.diagnosis.catalog import CATALOG, availability
from netcoop.diagnosis.evidence import build_view
from netcoop.diagnosis.params import load_diagnosis_params
from netcoop.diagnosis.scoring import (
    CommunityContext,
    DiagnosisContext,
    decide,
    score_hypotheses,
)
from netcoop.diagnosis.severity import grade

P = load_diagnosis_params()
T0 = datetime(2026, 10, 31, 12, tzinfo=UTC)
W = TimeWindow(start=T0, end=T0 + timedelta(minutes=5))
ITEMS = [
    "cpu_utilization_pct",
    "link_utilization_pct",
    "packet_loss_pct",
    "latency_ms",
    "jitter_ms",
    "queue_drops",
    "interface_errors",
    "status",
]
AGENT = {
    "latency_ms": "performance_agent",
    "jitter_ms": "performance_agent",
    "packet_loss_pct": "performance_agent",
    "link_utilization_pct": "performance_agent",
    "cpu_utilization_pct": "infrastructure_agent",
    "queue_drops": "infrastructure_agent",
    "interface_errors": "infrastructure_agent",
    "status": "infrastructure_agent",
    "probe_dns": "connectivity_agent",
}
ENTITIES = [f"SW_CAMPUS_{i}" for i in range(1, 11)]
NORMAL = {i: "normal" for i in ITEMS if i != "interface_errors"}  # generator normal profile
HW = {i: "critical" for i in ITEMS if i != "jitter_ms"}  # generator hardware_failure profile
SPIKE = {
    "cpu_utilization_pct": "elevated",
    "link_utilization_pct": "elevated",
    "packet_loss_pct": "elevated",
    "latency_ms": "critical",
    "jitter_ms": "critical",
    "queue_drops": "elevated",
    "status": "elevated",
}  # generator latency_spike profile (typical draw)
TOPO_FACTS: dict[str, Any] = {
    "topology_available": True,
    "paths": {
        "SW_CAMPUS_4": ["SW_CAMPUS_4", "SW_CAMPUS_2", "SW_CAMPUS_1"],
        "SW_CAMPUS_2": ["SW_CAMPUS_2", "SW_CAMPUS_1"],
    },
    "what_if": {"SW_CAMPUS_4": {"isolated": [], "degraded": []}},
}


def scenario(
    special: dict[str, dict[str, str]],
    *,
    entities: list[str] = ENTITIES,
    q: float = 0.875,
    facts: dict[str, Any] | None = None,
    missing_agents: list[str] | None = None,
    probes: dict[str, list[str]] | None = None,
    community: list[CommunityContext] | None = None,
    extra_obs: list[Observation] | None = None,
) -> Decision:
    obs: list[Observation] = []
    n = 0
    for e in entities:
        for item, sev in special.get(e, NORMAL).items():
            n += 1
            obs.append(_obs(f"OBS-{n:04d}", e, item, sev))
    for e, outcomes in (probes or {}).items():
        for sev in outcomes:
            n += 1
            obs.append(_obs(f"OBS-{n:04d}", e, "probe_dns", sev))
    obs += extra_obs or []
    probes_present = bool(probes)
    view = build_view(
        obs,
        [],
        facts=facts if facts is not None else TOPO_FACTS,
        params=P,
        entities=entities,
        items_per_entity=ITEMS,
    )
    ctx = DiagnosisContext(
        q=q,
        topology_available=(facts if facts is not None else TOPO_FACTS).get(
            "topology_available", False
        ),
        available=availability(load_field_dictionary(), probes_present=probes_present),
        missing_agents=missing_agents or [],
        window_start=W.start,
        window_end=W.end,
        community=community or [],
    )
    ranked = score_hypotheses(view, ctx, P, problem_agents=set())
    assessed = sum(1 for (e, i) in view.items if i in ITEMS)
    return decide(ranked, view, ctx, P, coverage=assessed / (len(entities) * len(ITEMS)))


def _obs(oid: str, e: str, item: str, sev: str, **kw: Any) -> Observation:
    return Observation(
        observation_id=oid,
        entity=e,
        metric=item,
        metric_category=item,
        value=None,
        unit="",
        window=kw.pop("window", W),
        severity=sev,  # type: ignore[arg-type]
        assessability="assessed",
        agent=kw.pop("agent", AGENT[item]),  # type: ignore[arg-type]
        **kw,
    )


def top(d: Decision) -> str:
    return next(h.cause_type for h in d.ranked if h.diagnosable)


# ------------------------------------------------------------------ severity grading


@pytest.mark.parametrize(
    ("item", "value", "expected"),
    [
        ("latency_ms", 20, "normal"),
        ("latency_ms", 20.01, "elevated"),
        ("latency_ms", 100, "critical"),
        ("packet_loss_pct", 0.0, "normal"),
        ("packet_loss_pct", 0.1, "elevated"),
        ("queue_drops", 0, "normal"),
        ("status", "Warning", "elevated"),
        ("status", "Critical", "critical"),
        ("status", "UP", "unknown"),
        ("wireless_signal", 3, "unknown"),
    ],
)
def test_grade(item: str, value: Any, expected: str) -> None:
    assert grade(item, value, P) == expected


# ------------------------------------------------------------------ outcomes


def test_normal_operation_gives_no_fault() -> None:  # T-DIAG-01 / S-01 shape
    d = scenario({})
    assert top(d) == "normal_operation"
    assert d.decision == "no_fault_detected"
    assert d.affected_entities == []
    assert d.gate_checks["coverage_at_least_min"]


def test_congestion_is_diagnosed_from_two_agents() -> None:  # T-DIAG-MULTI-01
    d = scenario(
        {
            "SW_CAMPUS_4": {
                **NORMAL,
                "link_utilization_pct": "critical",
                "queue_drops": "critical",
                "latency_ms": "critical",
                "status": "elevated",
            }
        }
    )
    assert top(d) == "link_congestion"
    assert d.decision == "diagnosed"
    best = d.ranked[0]
    assert best.entities == ["SW_CAMPUS_4"]
    assert best.supporting_sources == ["infrastructure_agent", "performance_agent"]
    assert best.corroboration == P.scoring.beta
    assert d.confidence == best.score and d.confidence_category in ("high", "medium")


def test_hardware_failure_profile_prefers_device_failure() -> None:
    d = scenario({"SW_CAMPUS_4": HW})
    assert top(d) == "device_failure"
    assert d.decision == "diagnosed", d.gate_checks
    alts = [h.cause_type for h in d.ranked[1:4]]
    assert "interface_fault" in alts


def test_latency_spike_profile_points_to_congestion() -> None:
    d = scenario({"SW_CAMPUS_4": SPIKE})
    assert top(d) == "link_congestion"


def test_interface_fault() -> None:  # S-04 shape (team-authored variant)
    d = scenario(
        {
            "SW_CAMPUS_6": {
                **NORMAL,
                "interface_errors": "critical",
                "packet_loss_pct": "critical",
                "status": "elevated",
            }
        }
    )
    assert top(d) == "interface_fault" and d.decision == "diagnosed"


def test_single_weak_symptom_is_insufficient() -> None:  # T-DIAG-INSUF-01 / R-07
    d = scenario({"SW_CAMPUS_4": {**NORMAL, "latency_ms": "elevated"}})
    assert d.decision == "insufficient_evidence"
    assert d.confidence <= P.gate.c_insuff_cap
    assert d.confidence_category == "insufficient"
    assert any(lim.code == "GATE_NOT_MET" for lim in d.limitations)


def test_upstream_congestion_needs_topology() -> None:
    upstream = {
        "SW_CAMPUS_2": {
            **NORMAL,
            "link_utilization_pct": "critical",
            "queue_drops": "critical",
            "latency_ms": "critical",
        },
        "SW_CAMPUS_4": {**NORMAL, "latency_ms": "critical", "jitter_ms": "elevated"},
    }
    with_topo = scenario(upstream)
    up = next(h for h in with_topo.ranked if h.cause_type == "upstream_congestion")
    assert up.entities == ["SW_CAMPUS_4"] and up.score > 0.5
    no_topo = scenario(upstream, facts={"topology_available": False})
    up2 = next(h for h in no_topo.ranked if h.cause_type == "upstream_congestion")
    assert up2.score < up.score
    assert any(lim.code == "TOPOLOGY_MISSING" for lim in no_topo.limitations)


def test_weak_wifi_is_never_output() -> None:  # ID-06
    d = scenario({"SW_CAMPUS_4": SPIKE})
    wifi = next(h for h in d.ranked if h.cause_type == "weak_wifi")
    assert not wifi.diagnosable and wifi.score == 0
    assert top(d) != "weak_wifi"
    assert any("Weak Wi-Fi" in lim.text for lim in d.limitations)


def test_dns_not_diagnosable_without_probes() -> None:  # T-DNS-01
    d = scenario({})
    dns = next(h for h in d.ranked if h.cause_type == "dns_dhcp_failure")
    assert not dns.diagnosable


def test_dns_failure_from_probes_with_healthy_network() -> None:  # T-DNS-03
    d = scenario({}, probes={"SW_CAMPUS_4": ["critical", "critical", "critical"]})
    assert top(d) == "dns_dhcp_failure"
    assert d.decision == "diagnosed", d.gate_checks
    assert d.affected_entities == ["SW_CAMPUS_4"]


def test_ambiguity_is_reported_not_resolved_by_guessing() -> None:  # S-09 shape
    # Two near-equal explanations on two devices: interface fault vs CPU overload.
    d = scenario(
        {
            "SW_CAMPUS_4": {
                **NORMAL,
                "interface_errors": "critical",
                "packet_loss_pct": "critical",
            },
            "SW_CAMPUS_6": {
                **NORMAL,
                "cpu_utilization_pct": "critical",
                "latency_ms": "critical",
                "queue_drops": "elevated",
            },
        }
    )
    assert d.decision == "insufficient_evidence"
    assert d.margin is not None and d.margin < P.gate.delta
    assert not d.gate_checks["margin_at_least_delta"]
    assert {h.cause_type for h in d.ranked[:2]} == {"interface_fault", "device_overload"}


def test_partial_explanation_still_names_best_cause() -> None:
    # Interface fault explains errors + loss; the CPU anomaly stays unexplained (U > 0).
    d = scenario(
        {
            "SW_CAMPUS_4": {
                **NORMAL,
                "cpu_utilization_pct": "critical",
                "interface_errors": "critical",
                "packet_loss_pct": "critical",
            }
        }
    )
    assert top(d) == "interface_fault"
    assert d.ranked[0].unexplained == pytest.approx(1 / 3, abs=1e-3)


def test_symptomless_devices_are_not_candidates() -> None:
    d = scenario({})
    up = next(h for h in d.ranked if h.cause_type == "upstream_congestion")
    assert up.entities == [] and up.score == 0


def test_low_data_quality_caps_confidence() -> None:
    congested = {
        "SW_CAMPUS_4": {
            **NORMAL,
            "link_utilization_pct": "critical",
            "queue_drops": "critical",
            "latency_ms": "critical",
        }
    }
    good = scenario(congested, q=0.9)
    poor = scenario(congested, q=0.4)
    assert poor.ranked[0].ceiling == 0.5
    assert poor.confidence < good.confidence


def test_missing_agent_lowers_ceiling_and_is_a_limitation() -> None:
    d = scenario({}, missing_agents=["connectivity_agent"])
    assert d.ranked[0].ceiling == pytest.approx(0.95 - P.ceiling.missing_agent_penalty)
    assert any(lim.code == "AGENT_MISSING" for lim in d.limitations)


# ------------------------------------------------------------------ conflicts (doc 08 §5)


def test_conflict_freshness_rule() -> None:
    old = TimeWindow(start=T0 - timedelta(hours=1), end=T0 - timedelta(minutes=50))
    d = scenario(
        {"SW_CAMPUS_4": {k: v for k, v in NORMAL.items() if k != "latency_ms"}},
        extra_obs=[
            _obs("OBS-OLD", "SW_CAMPUS_4", "latency_ms", "critical", window=old),
            _obs("OBS-NEW", "SW_CAMPUS_4", "latency_ms", "normal"),
        ],
    )
    (c,) = d.conflicts
    assert c.rule == "freshness" and "OBS-OLD" in c.disregarded


def test_conflict_evidence_class_rule() -> None:
    d = scenario(
        {"SW_CAMPUS_4": {k: v for k, v in NORMAL.items() if k != "latency_ms"}},
        extra_obs=[
            _obs("OBS-A", "SW_CAMPUS_4", "latency_ms", "critical", evidence_class="derived"),
            _obs("OBS-B", "SW_CAMPUS_4", "latency_ms", "normal"),
        ],
    )
    assert d.conflicts[0].rule == "evidence_class"
    assert d.conflicts[0].disregarded == {"OBS-A": "weaker evidence class than direct measurement"}


def test_unresolved_conflict_keeps_both_and_is_stated() -> None:
    d = scenario(
        {"SW_CAMPUS_4": {k: v for k, v in NORMAL.items() if k != "latency_ms"}},
        extra_obs=[
            _obs("OBS-A", "SW_CAMPUS_4", "latency_ms", "critical"),
            _obs("OBS-B", "SW_CAMPUS_4", "latency_ms", "normal"),
        ],
    )
    assert d.conflicts[0].rule == "unresolved"
    assert any(lim.code == "CONFLICT_UNRESOLVED" for lim in d.limitations)


# ------------------------------------------------------------------ community (doc 08 §6)


def test_community_alone_never_diagnoses() -> None:  # T-CSI-COR-01
    cand = CommunityContext("CAND-1", ("SW_CAMPUS_4",), W.start, W.end)
    d = scenario({}, community=[cand])
    assert d.decision != "diagnosed"


def test_community_bonus_is_bounded_and_excluded_from_sources() -> None:
    congested = {
        "SW_CAMPUS_4": {
            **NORMAL,
            "link_utilization_pct": "elevated",
            "queue_drops": "elevated",
            "latency_ms": "elevated",
        }
    }
    cand = CommunityContext("CAND-1", ("SW_CAMPUS_4",), W.start, W.end)
    with_c = scenario(congested, community=[cand])
    without = scenario(congested)
    h1 = next(h for h in with_c.ranked if h.cause_type == "link_congestion")
    h0 = next(h for h in without.ranked if h.cause_type == "link_congestion")
    assert h1.community_bonus == P.scoring.gamma_max
    assert h1.base - h0.base == pytest.approx(P.scoring.gamma_max, abs=1e-4)
    assert "community_module" not in h1.supporting_sources


# ------------------------------------------------------------------ property tests (doc 08 §9)

_SEV = st.sampled_from(["normal", "elevated", "critical"])
_PROFILE = st.dictionaries(st.sampled_from(ITEMS), _SEV, min_size=1)


@settings(max_examples=80, deadline=None)
@given(profile=_PROFILE, drop=st.sampled_from(ITEMS))
def test_removing_evidence_never_raises_support(profile: dict[str, str], drop: str) -> None:
    full = scenario({"SW_CAMPUS_4": profile}, entities=["SW_CAMPUS_4"])
    reduced = scenario(
        {"SW_CAMPUS_4": {k: v for k, v in profile.items() if k != drop}},
        entities=["SW_CAMPUS_4"],
    )
    for cause in CATALOG:
        a = next(h for h in full.ranked if h.cause_type == cause)
        b = next(h for h in reduced.ranked if h.cause_type == cause)
        if cause in ("normal_operation", "telemetry_unreliable"):
            continue
        if a.entities and b.entities:
            assert b.support <= a.support + 1e-9, (cause, profile, drop)


@settings(max_examples=60, deadline=None)
@given(profile=_PROFILE)
def test_community_never_changes_the_decision(profile: dict[str, str]) -> None:
    """Complaints may raise displayed confidence but never the decision (doc 08 §6)."""
    cand = CommunityContext("CAND-1", ("SW_CAMPUS_4",), W.start, W.end)
    plain = scenario({"SW_CAMPUS_4": profile}, entities=["SW_CAMPUS_4", "SW_CAMPUS_5"])
    boosted = scenario(
        {"SW_CAMPUS_4": profile}, entities=["SW_CAMPUS_4", "SW_CAMPUS_5"], community=[cand]
    )
    assert boosted.decision == plain.decision
    assert boosted.gate_checks == plain.gate_checks


def test_determinism() -> None:  # T-REPRO (unit level)
    a = scenario({"SW_CAMPUS_4": HW})
    b = scenario({"SW_CAMPUS_4": HW})
    assert a.model_dump() == b.model_dump()


def test_unresolved_conflict_with_critical_reading_blocks_no_fault() -> None:  # S-12 shape
    d = scenario(
        {"SW_CAMPUS_4": {k: v for k, v in NORMAL.items() if k != "latency_ms"}},
        extra_obs=[
            _obs("OBS-A", "SW_CAMPUS_4", "latency_ms", "critical"),
            _obs("OBS-B", "SW_CAMPUS_4", "latency_ms", "normal"),
        ],
    )
    assert d.decision == "insufficient_evidence"
    assert not d.gate_checks["no_abnormal_measurements"]
