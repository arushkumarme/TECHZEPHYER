"""Orchestrator state machine (doc 04): T-ORCH-*, T-ORCH-COLLAB-*, T-REPRO (unit level)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from netcoop.config.settings import OrchestrationSettings, Settings, load_settings
from netcoop.core.log_store import LogStore
from netcoop.orchestrator.states import IllegalTransition, check_transition
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.generator import load_generator

T0 = datetime(2026, 10, 31, 12, tzinfo=UTC)
GEN = load_generator()
HAPPY = [
    "RECEIVED",
    "VALIDATING",
    "READY",
    "DISPATCHED",
    "COLLECTING",
    "CORRELATING",
    "DECIDED",
    "REPORTING",
    "AWAITING_REVIEW",
]


def bundle(faults: dict[str, str] | None = None, *, topology: str | None = "campus_v1") -> str:
    faults = faults or {}
    records = []
    seed = 0
    for k in range(3):
        for n in range(1, 11):
            seed += 1
            rec = GEN.generate(
                faults.get(f"SW_CAMPUS_{n}", "normal"), seed=seed, at=T0 + timedelta(minutes=5 * k)
            )
            rec["device_id"] = f"SW_CAMPUS_{n}"
            records.append(rec)
    raw: dict[str, Any] = {"records": records, "provenance": "synthetic-generator"}
    if topology:
        raw["topology_ref"] = topology
    return json.dumps(raw)


def orch(tmp_path: Path, **overrides: Any) -> Orchestrator:
    base = load_settings()
    o = base.orchestration.model_copy(
        update={"specialist_deadline_s": 3.0, **overrides.pop("orchestration", {})}
    )
    settings = Settings(
        mode="simulation", features=base.features, ingestion=base.ingestion, orchestration=o
    )
    return Orchestrator(LogStore(tmp_path / "log.sqlite3"), settings=settings, **overrides)


def states(o: Orchestrator, incident: str) -> list[str]:
    return [t.to_state for t in o.store.transitions(incident)]


def test_transition_table() -> None:
    check_transition(None, "RECEIVED")
    check_transition("CORRELATING", "CLARIFYING")
    with pytest.raises(IllegalTransition):
        check_transition("RECEIVED", "DECIDED")
    with pytest.raises(IllegalTransition):
        check_transition("REJECTED", "VALIDATING")


def test_full_run(tmp_path: Path) -> None:  # T-ORCH-01, T-ORCH-COLLAB-01
    o = orch(tmp_path)
    r = o.run(bundle({"SW_CAMPUS_4": "hardware_failure"}))
    assert r.incident_id == "INC-0001"
    # The generator's hardware_failure profile omits jitter_ms, so ingestion correctly
    # accepts the bundle WITH WARNINGS (METRIC_MISSING) instead of READY.
    seq = states(o, r.incident_id)
    assert seq == [*HAPPY[:2], "READY_WITH_WARNINGS", *HAPPY[3:]]
    accepted = o.store.transitions(r.incident_id)[2]
    assert "METRIC_MISSING" in accepted.detail["warnings"]
    assert r.report["status"] == "diagnosed"
    assert len(r.report["evidence_sources"]) >= 2
    stored = o.store.latest_report(r.incident_id)
    assert stored is not None and stored[0]["incident_id"] == "INC-0001"
    types = [m.message_type for m in o.store.messages(r.incident_id)]
    assert types.count("task_request") == 5  # 3 specialists + correlation + reporting
    assert types.count("finding") == 3
    assert "decision" in types and "report_ready" in types
    assert all(m.valid for m in o.store.messages(r.incident_id))


def test_normal_run_is_ready_without_warnings(tmp_path: Path) -> None:
    o = orch(tmp_path)
    r = o.run(bundle())
    assert states(o, r.incident_id) == HAPPY
    assert r.report["status"] == "no_fault_detected"


def test_rejected_input(tmp_path: Path) -> None:  # T-ERR-01 through the orchestrator
    o = orch(tmp_path)
    r = o.run("{garbage")
    assert states(o, r.incident_id) == ["RECEIVED", "VALIDATING", "REJECTED"]
    assert r.report["status"] == "failed"
    assert any("INPUT_UNPARSEABLE" in lim for lim in r.report["limitations"])
    assert o.store.messages(r.incident_id) == []  # no agent was involved


def test_warnings_path_and_missing_topology(tmp_path: Path) -> None:
    o = orch(tmp_path)
    r = o.run(bundle(topology="no_such_topology"))
    assert "READY_WITH_WARNINGS" in states(o, r.incident_id)
    assert any("topology" in lim.lower() for lim in r.report["limitations"])


def _timeout_handler(*_: Any) -> Any:
    import time

    time.sleep(10)


@pytest.mark.parametrize(
    ("fault", "code"),
    [("timeout", "AGENT_TIMEOUT"), ("error", "AGENT_FAILED"), ("invalid", "MESSAGE_INVALID")],
)
def test_specialist_failure_degrades_run(tmp_path: Path, fault: str, code: str) -> None:
    o = orch(
        tmp_path,
        orchestration={"specialist_deadline_s": 0.5},
        fault_injection={"performance_agent": fault},
    )
    r = o.run(bundle({"SW_CAMPUS_4": "hardware_failure"}))
    assert states(o, r.incident_id)[-1] == "AWAITING_REVIEW"
    ext = r.report["netcoop_extensions"]
    assert ext["agent_contributions"]["performance_agent"] == {"status": "missing"}
    assert any("performance_agent" in lim for lim in r.report["limitations"])
    tasks = [
        m
        for m in o.store.messages(r.incident_id)
        if m.message_type == "task_request" and m.recipient == "performance_agent"
    ]
    assert len(tasks) == 2  # retried once (agent_retries = 1)
    errors = [t.detail for t in o.store.transitions(r.incident_id) if t.detail.get("agent_error")]
    assert any(e["agent_error"] == code for e in errors)


def test_all_specialists_fail(tmp_path: Path) -> None:
    o = orch(
        tmp_path,
        orchestration={"specialist_deadline_s": 0.5, "agent_retries": 0},
        fault_injection={
            a: "error" for a in ("performance_agent", "infrastructure_agent", "connectivity_agent")
        },
    )
    r = o.run(bundle({"SW_CAMPUS_4": "hardware_failure"}))
    assert r.report["status"] == "insufficient_evidence"
    assert r.report["evidence_sources"] == []


def test_correlation_failure_gives_failed_report(tmp_path: Path) -> None:
    o = orch(tmp_path, fault_injection={"correlation_agent": "error"})
    r = o.run(bundle({"SW_CAMPUS_4": "hardware_failure"}))
    assert states(o, r.incident_id)[-1] == "FAILED"
    assert r.report["status"] == "failed"
    assert (
        r.report["netcoop_extensions"]["agent_contributions"]["infrastructure_agent"]["status"]
        == "ok"
    )  # specialist findings still attached


def test_reporting_failure_uses_deterministic_fallback(tmp_path: Path) -> None:
    o = orch(tmp_path, fault_injection={"reporting_agent": "error"})
    r = o.run(bundle({"SW_CAMPUS_4": "hardware_failure"}))
    assert r.report["status"] == "diagnosed"
    assert any(t.trigger == "fallback_report" for t in o.store.transitions(r.incident_id))


def test_sequential_and_parallel_runs_are_identical(tmp_path: Path) -> None:  # T-REPRO-02
    a = orch(tmp_path / "a", orchestration={"parallel_specialists": True})
    b = orch(tmp_path / "b", orchestration={"parallel_specialists": False})
    ra = a.run(bundle({"SW_CAMPUS_4": "latency_spike"}))
    rb = b.run(bundle({"SW_CAMPUS_4": "latency_spike"}))

    def strip(r: dict[str, Any]) -> dict[str, Any]:
        out = json.loads(json.dumps(r))
        out["netcoop_extensions"].pop("generated_at")
        return out

    assert strip(ra.report) == strip(rb.report)
    assert states(a, ra.incident_id) == states(b, rb.incident_id)
    ids_a = sorted(m.message_id or "" for m in a.store.messages(ra.incident_id))
    ids_b = sorted(m.message_id or "" for m in b.store.messages(rb.incident_id))
    assert ids_a == ids_b


def test_incident_ids_increment_and_are_namespaced(tmp_path: Path) -> None:
    o = orch(tmp_path)
    r1 = o.run(bundle())
    r2 = o.run(bundle())
    assert (r1.incident_id, r2.incident_id) == ("INC-0001", "INC-0002")
    ids = {m.message_id for m in o.store.messages()}
    assert len(ids) == len(o.store.messages())  # globally unique across incidents


def test_clarifying_state_is_recorded(tmp_path: Path) -> None:
    # Team-authored variant: two devices with near-equal competing explanations (S-09 shape)
    raw = json.loads(bundle())
    for rec in raw["records"]:
        if rec["device_id"] == "SW_CAMPUS_4":
            rec["metrics"].update(interface_errors=250, packet_loss_pct=12.0)
        if rec["device_id"] == "SW_CAMPUS_6":
            rec["metrics"].update(cpu_utilization_pct=97.0, latency_ms=180.0, queue_drops=40)
    raw["provenance"] = "team-authored"
    o = orch(tmp_path)
    r = o.run(json.dumps(raw))
    seq = states(o, r.incident_id)
    assert "CLARIFYING" in seq
    assert seq.count("CLARIFYING") <= OrchestrationSettings().max_clarification_rounds
    assert r.report["status"] == "insufficient_evidence"
