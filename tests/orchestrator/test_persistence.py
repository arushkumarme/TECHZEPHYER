"""Persistent workflow state, pause/resume and crash recovery (component 10, T-PERSIST-*).

A "restart" is simulated by building a brand-new Orchestrator on the same SQLite file:
nothing survives in memory, only what was checkpointed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from netcoop.core.log_store import LogStore
from netcoop.orchestrator.workflow import Orchestrator, SimulatedCrash
from netcoop.scenarios.runner import load_scenario

from .test_workflow import orch, states


def _essence(report: dict[str, Any]) -> dict[str, Any]:
    """Report content that must not depend on interruption (ids/timestamps may)."""
    return {
        "status": report["status"],
        "cause": report["suspected_root_cause"],
        "confidence": report["confidence"],
        "affected": report["affected_devices"],
        "evidence": [(e["metric"], e["value"]) for e in report["supporting_evidence"]],
        "sources": report["evidence_sources"],
        "actions": report["recommended_actions"],
    }


def _fresh(tmp_path: Path) -> Orchestrator:
    return orch(tmp_path)  # same db file name under tmp_path -> same store


@pytest.mark.parametrize("pause_at", ["VALIDATING", "COLLECTING", "CORRELATING", "DECIDED"])
def test_pause_then_resume_after_restart(tmp_path: Path, pause_at: str) -> None:
    raw = load_scenario("S-02").input_bytes
    reference = orch(tmp_path / "ref").run(raw).report

    first = _fresh(tmp_path)
    paused = first.run(raw, pause_after=pause_at)
    assert paused.paused and paused.final_state == pause_at
    assert first.store.latest_report(paused.incident_id) is None

    second = _fresh(tmp_path)  # "process restart"
    assert second.resumable() == [paused.incident_id]
    done = second.resume(paused.incident_id)
    assert not done.paused and done.final_state == "AWAITING_REVIEW"
    assert _essence(done.report) == _essence(reference)
    seq = states(second, paused.incident_id)
    assert seq.count("RECEIVED") == 1  # one incident, continued - not restarted
    assert any(t.trigger == "resume" for t in second.store.transitions(paused.incident_id))


def test_resume_does_not_redo_completed_findings(tmp_path: Path) -> None:
    raw = load_scenario("S-02").input_bytes
    first = _fresh(tmp_path)
    paused = first.run(raw, pause_after="CORRELATING")
    tasks_before = _tasks(first.store, paused.incident_id)
    second = _fresh(tmp_path)
    second.resume(paused.incident_id)
    tasks_after = _tasks(second.store, paused.incident_id)
    new = [t for t in tasks_after if t not in tasks_before]
    assert all(r == "correlation_agent" or r == "reporting_agent" for r in new)


def _tasks(store: LogStore, incident: str) -> list[str]:
    return [f"{m.recipient}" for m in store.messages(incident) if m.message_type == "task_request"]


def test_crash_mid_correlation_is_recovered(tmp_path: Path) -> None:
    raw = load_scenario("S-09").input_bytes  # has clarification rounds
    crashing = orch(tmp_path, fault_injection={"correlation_agent": "crash"})
    with pytest.raises(SimulatedCrash):
        crashing.run(raw)
    incident = crashing.store.list_incidents()[-1]
    survivor = _fresh(tmp_path)
    assert incident in survivor.resumable()
    done = survivor.resume(incident)
    assert done.report["status"] == "insufficient_evidence"
    ref = orch(tmp_path / "ref").run(raw).report
    assert _essence(done.report) == _essence(ref)


def test_partial_findings_survive_a_crash(tmp_path: Path) -> None:
    raw = load_scenario("S-02").input_bytes
    crashing = orch(
        tmp_path,
        fault_injection={"connectivity_agent": "crash"},
        orchestration={"parallel_specialists": False},
    )
    with pytest.raises(SimulatedCrash):
        crashing.run(raw)
    incident = crashing.store.list_incidents()[-1]
    kinds = [c["kind"] for c in crashing.store.checkpoints(incident)]
    assert "finding:performance_agent" in kinds and "finding:infrastructure_agent" in kinds
    survivor = _fresh(tmp_path)
    done = survivor.resume(incident)
    assert done.report["status"] == "diagnosed"
    redone = [
        m.recipient
        for m in survivor.store.messages(incident)
        if m.message_type == "task_request"
        and m.recipient in ("performance_agent", "infrastructure_agent")
    ]
    assert len(redone) == 2  # only the original two; neither was re-run


def test_terminal_and_review_states_are_not_resumable(tmp_path: Path) -> None:
    o = _fresh(tmp_path)
    r1 = o.run("{bad json")  # REJECTED
    r2 = o.run(load_scenario("S-01").input_bytes)  # AWAITING_REVIEW (human step, M11)
    assert o.resumable() == []
    again = o.resume(r1.incident_id)
    assert again.report["status"] == "failed" and again.final_state == "REJECTED"
    assert o.resume(r2.incident_id).final_state == "AWAITING_REVIEW"


def test_checkpoints_are_append_only(tmp_path: Path) -> None:
    import sqlite3

    o = _fresh(tmp_path)
    o.run(load_scenario("S-01").input_bytes, pause_after="COLLECTING")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        o.store._execute_raw_for_tests("DELETE FROM checkpoints")


def test_unknown_incident(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        _fresh(tmp_path).resume("INC-9999")


def test_cli_pause_and_resume(tmp_path: Path) -> None:
    import subprocess
    import sys

    db = str(tmp_path / "cli.sqlite3")
    repo = Path(__file__).resolve().parents[2]

    def cli(*a: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "netcoop.cli.main", "--db", db, *a],
            capture_output=True,
            text=True,
            cwd=repo,
            timeout=120,
            check=False,
        )

    p = cli("run", "--scenario", "S-04", "--pause-after", "COLLECTING")
    assert p.returncode == 0, p.stderr
    assert "paused" in p.stderr.lower()
    lst = cli("incidents")
    assert "INC-0001" in lst.stdout and "COLLECTING" in lst.stdout and "resumable" in lst.stdout
    r = cli("resume", "INC-0001")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["status"] == "diagnosed"
