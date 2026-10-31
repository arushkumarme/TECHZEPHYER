"""Human-in-the-loop review + simulated remediation (components 9 and 12; T-HITL-*, T-SAFE-*)."""

from __future__ import annotations

import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from netcoop.orchestrator.review import ReviewError, ReviewService
from netcoop.remediation.simulator import simulate_action
from netcoop.scenarios.runner import load_scenario

from .test_workflow import orch, states


@pytest.fixture
def awaiting(tmp_path: Path):  # type: ignore[no-untyped-def]
    o = orch(tmp_path)
    r = o.run(load_scenario("S-04").input_bytes)  # diagnosed interface fault
    assert r.final_state == "AWAITING_REVIEW"
    return o, r


def test_pending_lists_every_recommendation(awaiting) -> None:  # type: ignore[no-untyped-def]
    o, r = awaiting
    svc = ReviewService(o.store, clock=o.clock)
    pending = svc.pending(r.incident_id)
    assert [p.action for p in pending] == r.report["recommended_actions"]
    assert all(p.approval_state == "pending" for p in pending)


def test_approval_is_recorded_and_outcome_simulated(awaiting) -> None:  # type: ignore[no-untyped-def]
    o, r = awaiting
    svc = ReviewService(o.store, clock=o.clock)
    rec = svc.decide(r.incident_id, 0, "approve", reviewer="operator-1", note="looks right")
    assert (rec.decision, rec.reviewer, rec.action_index) == ("approve", "operator-1", 0)
    assert rec.simulated_outcome is not None
    assert rec.simulated_outcome.startswith("SIMULATED")
    assert "no device" in rec.simulated_outcome.lower()
    assert svc.state(r.incident_id) == "AWAITING_REVIEW"  # other actions still pending


def test_cannot_decide_twice_or_out_of_range(awaiting) -> None:  # type: ignore[no-untyped-def]
    o, r = awaiting
    svc = ReviewService(o.store, clock=o.clock)
    svc.decide(r.incident_id, 0, "reject", reviewer="op", note="not now")
    with pytest.raises(ReviewError, match="already"):
        svc.decide(r.incident_id, 0, "approve", reviewer="op")
    with pytest.raises(ReviewError, match="no recommendation"):
        svc.decide(r.incident_id, 99, "approve", reviewer="op")
    with pytest.raises(ReviewError, match="reviewer"):
        svc.decide(r.incident_id, 1, "approve", reviewer="  ")


def test_completing_review_closes_incident_and_versions_report(awaiting) -> None:  # type: ignore[no-untyped-def]
    o, r = awaiting
    svc = ReviewService(o.store, clock=o.clock)
    n = len(r.report["recommended_actions"])
    for i in range(n):
        svc.decide(r.incident_id, i, "approve" if i == 0 else "reject", reviewer="op")
    assert states(o, r.incident_id)[-1] == "COMPLETE"
    report, md = o.store.latest_report(r.incident_id)  # type: ignore[misc]
    status = report["netcoop_extensions"]["recommendation_status"]
    assert [s["approval_state"] for s in status] == ["approved"] + ["rejected"] * (n - 1)
    assert status[0]["simulated_outcome"].startswith("SIMULATED")
    assert all(s["simulated"] for s in status)
    assert report["status"] == r.report["status"]  # review never changes the diagnosis
    assert "[approved]" in md
    # the original report version is preserved (append-only)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        o.store.execute_unsafe_for_tests("DELETE FROM approvals")


def test_review_only_in_awaiting_review(tmp_path: Path) -> None:
    o = orch(tmp_path)
    r = o.run("{bad")
    with pytest.raises(ReviewError, match="AWAITING_REVIEW"):
        ReviewService(o.store, clock=o.clock).decide(r.incident_id, 0, "approve", reviewer="op")


def test_approval_never_touches_the_network(awaiting, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """T-SAFE-02: approving and simulating cannot open any connection."""
    o, r = awaiting

    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("network access attempted during remediation")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    svc = ReviewService(o.store, clock=o.clock)
    for i in range(len(r.report["recommended_actions"])):
        svc.decide(r.incident_id, i, "approve", reviewer="op")


def test_simulator_has_no_write_path() -> None:  # T-SAFE-03
    import netcoop.remediation.simulator as sim

    src = Path(sim.__file__).read_text(encoding="utf-8")
    for forbidden in ("netcoop.tools", "subprocess", "socket", "requests", "httpx", "urllib"):
        assert forbidden not in src, forbidden
    out = simulate_action("Inspect interface error counters (SW_CAMPUS_6)", "interface_fault")
    assert out.startswith("SIMULATED") and "SW_CAMPUS_6" in out


def test_cli_review_flow(tmp_path: Path) -> None:
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

    assert cli("run", "--scenario", "S-04", "--json-out", str(tmp_path / "r.json")).returncode == 0
    listing = cli("review", "INC-0001")
    assert listing.returncode == 0 and "[0] pending" in listing.stdout
    ok = cli("approve", "INC-0001", "0", "--reviewer", "operator-1", "--note", "go")
    assert ok.returncode == 0 and "SIMULATED" in ok.stdout
    again = cli("approve", "INC-0001", "0", "--reviewer", "operator-1")
    assert again.returncode == 1 and "already" in again.stderr
