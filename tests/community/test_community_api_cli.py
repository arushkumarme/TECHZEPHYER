"""Extension A over the API and CLI, and isolation when the flag is off (T-ISO-01)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

import netcoop.api.community  # noqa: F401  (registers the extension)
from netcoop.api.app import create_app
from netcoop.community.pipeline import CommunityPipeline
from netcoop.config.settings import load_settings
from netcoop.core.log_store import LogStore
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.generator import REPO_ROOT
from netcoop.scenarios.runner import load_scenario

DEMO = REPO_ROOT / "sample_data" / "complaints" / "hostel_a_demo.json"


def _on() -> object:
    s = load_settings()
    return s.model_copy(
        update={"features": s.features.model_copy(update={"community_signals": True})}
    )


def test_flag_off_means_no_community_routes(tmp_path: Path) -> None:  # T-ISO-01
    client = TestClient(create_app(db_path=tmp_path / "a.sqlite3"))
    assert (
        client.post("/api/community/complaints", json={"text": "x", "reporter": "y"}).status_code
        == 404
    )


def test_api_flow(tmp_path: Path) -> None:
    client = TestClient(create_app(db_path=tmp_path / "a.sqlite3", settings=_on()))  # type: ignore[arg-type]
    for i, text in enumerate(["Hostel A Wi-Fi is disconnecting.", "hostel a wifi keeps dropping"]):
        r = client.post("/api/community/complaints", json={"text": text, "reporter": f"r{i}"})
        assert r.status_code == 201 and r.json()["zone"] == "ZONE_HOSTEL_A"
        assert "reporter" not in r.json()
    cands = client.get("/api/community/candidates").json()
    assert len(cands) == 1 and cands[0]["distinct_reporters"] == 2
    inc = client.post(
        f"/api/community/candidates/{cands[0]['candidate_id']}/investigate",
        json={"scenario_id": "S-02"},
    )
    assert inc.status_code == 201
    report = client.get(f"/api/incidents/{inc.json()['incident_id']}/report").json()
    # Wall-clock complaints do not overlap the scenario's playback window, but the
    # device match still applies: the trust label is computed on devices.
    assert report["netcoop_extensions"]["community_signals"][0]["trust_label"] == "corroborated"
    assert client.get("/api/community/stats").json()["accepted"] == 2


def test_demo_file_end_to_end(tmp_path: Path) -> None:  # S-14 / S-15 with the demo file
    store = LogStore(tmp_path / "d.sqlite3")
    pipe = CommunityPipeline(store)
    for c in json.loads(DEMO.read_text(encoding="utf-8"))["complaints"]:
        pipe.submit(
            c["text"],
            channel=c["channel"],
            reporter=c["reporter"],
            received_at=datetime.fromisoformat(c["received_at"].replace("Z", "+00:00")),
        )
    stats = pipe.stats()
    assert (stats["duplicate"], stats["rejected"]) == (1, 1)  # duplicate merged, spam ignored
    flagged = [c for c in pipe.complaints() if "injection_suspected" in c.flags]
    assert len(flagged) == 1 and flagged[0].zone == "ZONE_HOSTEL_A"
    (cand,) = pipe.candidates()
    assert cand.distinct_reporters == 3  # reporters 1, 2 and 4; duplicate/spam not counted
    r = pipe.investigate(
        cand.candidate_id,
        Orchestrator(store, settings=_on()),  # type: ignore[arg-type]
        load_scenario("S-02").input_bytes,
    ).report
    assert r["netcoop_extensions"]["community_signals"][0]["trust_label"] == "corroborated"


def test_cli_community(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.sqlite3")

    def cli(*a: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "netcoop.cli.main", "--db", db, *a],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=120,
            check=False,
            # Setup (P4): the community extension must be on to admit community input.
            env={**os.environ, "NETCOOP_ENABLE": "community_signals"},
        )

    load = cli("community", "load", str(DEMO))
    assert load.returncode == 0, load.stderr
    cands = cli("community", "candidates")
    assert "ZONE_HOSTEL_A" in cands.stdout and "CAND-0001" in cands.stdout
    inv = cli("community", "investigate", "CAND-0001", "--scenario", "S-01")
    assert inv.returncode == 0, inv.stderr
    assert "reported_unverified" in inv.stdout
