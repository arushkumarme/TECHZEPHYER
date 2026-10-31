"""End-to-end scenario suite (T-SCN-*), reproducibility (T-REPRO-*), CLI (DLV-5)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from netcoop.core.log_store import LogStore
from netcoop.orchestrator.trace import render_trace
from netcoop.report.builder import OFFICIAL_KEYS
from netcoop.report.validate import validate_report
from netcoop.scenarios.catalog import SCENARIOS, build_input, dumps, metadata
from netcoop.scenarios.runner import (
    SCENARIO_DIR,
    check_expectations,
    list_scenarios,
    load_scenario,
    run_scenario,
)

pytestmark = pytest.mark.e2e
REPO = Path(__file__).resolve().parents[2]


def test_every_catalogued_scenario_is_committed() -> None:
    assert list_scenarios() == sorted(SCENARIOS)


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_committed_scenarios_are_reproducible(sid: str) -> None:  # T-REPRO-03
    folder = SCENARIO_DIR / sid
    assert (folder / "input.json").read_text(encoding="utf-8") == dumps(build_input(sid))
    assert (folder / "scenario.json").read_text(encoding="utf-8") == dumps(metadata(sid))


@pytest.mark.parametrize("sid", sorted(SCENARIOS))
def test_scenario_outcome(sid: str, tmp_path: Path) -> None:  # T-SCN-nn
    store = LogStore(tmp_path / "log.sqlite3")
    reference: dict[str, float] = {}
    sc = load_scenario(sid)
    ref = sc.meta["expected"].get("confidence_below_scenario")
    if ref:
        reference[ref] = run_scenario(load_scenario(ref), store).report["confidence"]
    result = run_scenario(sc, store)
    assert check_expectations(result, sc.meta["expected"], reference_confidence=reference) == []
    report = result.report
    assert list(report)[: len(OFFICIAL_KEYS)] == list(OFFICIAL_KEYS)
    obs = {o.observation_id for f in result.findings.values() for o in f.observations}
    assert validate_report(report, observation_ids=obs, finding_agents=set(result.findings)) == []
    assert report["netcoop_extensions"]["mode"] == "simulation"
    assert "Simulated data" in result.markdown


def test_scenario_runs_are_deterministic(tmp_path: Path) -> None:  # T-REPRO-01 (in-process)
    def run(db: Path) -> dict[str, object]:
        r = run_scenario(load_scenario("S-09"), LogStore(db)).report
        r["netcoop_extensions"].pop("generated_at")
        return r

    assert run(tmp_path / "a.sqlite3") == run(tmp_path / "b.sqlite3")


def test_trace_shows_agent_behaviour(tmp_path: Path) -> None:  # Demo-2 evidence
    store = LogStore(tmp_path / "log.sqlite3")
    r = run_scenario(load_scenario("S-09"), store)
    trace = render_trace(store, r.incident_id)
    for needle in (
        "[state] - -> RECEIVED",
        "task_request",
        "tool calls=",
        "clarification_request",
        "decision: insufficient_evidence",
        "report_ready",
    ):
        assert needle in trace, needle


def _cli(*args: str, db: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "netcoop.cli.main", "--db", str(db), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
        check=False,
    )


def test_cli_run_and_validate(tmp_path: Path) -> None:  # DLV-5, M-06
    out = tmp_path / "report.json"
    md = tmp_path / "report.md"
    p = _cli(
        "run",
        "--scenario",
        "S-02",
        "--json-out",
        str(out),
        "--md-out",
        str(md),
        "--strict",
        db=tmp_path / "log.sqlite3",
    )
    assert p.returncode == 0, p.stderr
    assert "SIMULATED DATA" in p.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert list(report) == list(OFFICIAL_KEYS)
    assert report["status"] == "diagnosed"
    assert "Simulated data" in md.read_text(encoding="utf-8")
    v = _cli("validate-report", str(out), db=tmp_path / "log.sqlite3")
    assert v.returncode == 0 and "valid" in v.stdout


def test_cli_rejects_bad_input_with_exit_code(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    p = _cli("run", str(bad), db=tmp_path / "log.sqlite3")
    assert p.returncode == 2
    assert json.loads(p.stdout)["status"] == "failed"


def test_cli_fault_injection_and_trace(tmp_path: Path) -> None:
    db = tmp_path / "log.sqlite3"
    p = _cli(
        "run",
        "--scenario",
        "S-02",
        "--inject-fault",
        "infrastructure_agent:invalid",
        "--trace",
        db=db,
    )
    assert p.returncode == 0, p.stderr
    assert "INVALID: MESSAGE_INVALID" in p.stderr
    t = _cli("trace", "INC-0001", db=db)
    assert "agent_error" in t.stdout
