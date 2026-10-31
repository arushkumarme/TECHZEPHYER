"""End-to-end: every message of a real run carries the snapshot ID, mode, provenance and a
deterministic per-incident seq stamped by the bus (protocol upgrade, Prompt 2)."""

from __future__ import annotations

import json
from pathlib import Path

from netcoop.core.log_store import LogStore
from netcoop.orchestrator.trace import render_trace
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.runner import load_scenario

from .test_workflow import orch


def _envelopes(store: LogStore, incident: str) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(m.raw_json) for m in store.messages(incident) if m.valid]


def test_every_message_is_stamped(tmp_path: Path) -> None:
    o = Orchestrator(LogStore(tmp_path / "s.sqlite3"))
    r = o.run(load_scenario("S-09").input_bytes)  # includes clarification rounds
    snaps = [c["data"] for c in o.store.checkpoints(r.incident_id) if c["kind"] == "snapshot"]
    assert len(snaps) == 1
    snap = snaps[0]
    envs = _envelopes(o.store, r.incident_id)
    assert len(envs) > 10
    for e in envs:
        assert e["protocol_version"] == "1.1"
        assert e["snapshot_id"] == snap["snapshot_id"]
        assert e["mode"] == "simulation"
        assert e["data_provenance"] == "team-authored"
    assert [e["seq"] for e in envs] == list(range(1, len(envs) + 1))
    assert r.report["netcoop_extensions"]["data_snapshot"]["snapshot_id"] == snap["snapshot_id"]


def test_trace_shows_snapshot_and_seq(tmp_path: Path) -> None:
    store = LogStore(tmp_path / "t.sqlite3")
    r = Orchestrator(store).run(load_scenario("S-02").input_bytes)
    trace = render_trace(store, r.incident_id)
    snap = r.report["netcoop_extensions"]["data_snapshot"]["snapshot_id"]
    msg_lines = [line for line in trace.splitlines() if "[msg]" in line]
    assert msg_lines and all(f"{snap} synthetic-generator" in line for line in msg_lines)
    assert "seq=1 " in msg_lines[0]


def test_seq_is_identical_in_parallel_and_sequential_runs(tmp_path: Path) -> None:
    def order(parallel: bool, sub: str) -> list[tuple[int, str]]:
        o = orch(tmp_path / sub, orchestration={"parallel_specialists": parallel})
        r = o.run(load_scenario("S-02").input_bytes)
        return [(e["seq"], e["message_id"]) for e in _envelopes(o.store, r.incident_id)]

    assert order(True, "a") == order(False, "b")


def test_resume_continues_seq_without_gaps(tmp_path: Path) -> None:
    first = orch(tmp_path)
    paused = first.run(load_scenario("S-02").input_bytes, pause_after="CORRELATING")
    orch(tmp_path).resume(paused.incident_id)
    envs = _envelopes(LogStore(tmp_path / "log.sqlite3"), paused.incident_id)
    seqs = [e["seq"] for e in envs]
    assert seqs == list(range(1, len(seqs) + 1))
    assert len({e["snapshot_id"] for e in envs}) == 1


def test_rejected_input_has_no_snapshot(tmp_path: Path) -> None:
    o = Orchestrator(LogStore(tmp_path / "r.sqlite3"))
    r = o.run("{nope")
    assert [c for c in o.store.checkpoints(r.incident_id) if c["kind"] == "snapshot"] == []
