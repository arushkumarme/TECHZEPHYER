"""Extension B - Geospatial Network Intelligence backend (doc 11; T-GEO-*)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netcoop.api.app import create_app
from netcoop.community.pipeline import CommunityPipeline
from netcoop.config.settings import load_settings
from netcoop.core.log_store import LogStore
from netcoop.geo.layers import blast_radius, campus_layers, incident_overlay, load_layout
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.runner import load_scenario

from ..community.test_community import T


def test_every_layer_carries_provenance() -> None:  # T-GEO-PROV-01
    layers = campus_layers("campus_v1")
    assert layers["banner"].startswith("SIMULATED")
    assert layers["crs"] == "schematic"
    for name in ("zones", "devices", "links"):
        assert layers[name], name
        assert all(f["provenance"] == "SIMULATED" for f in layers[name]), name
    assert {d["id"] for d in layers["devices"]} == {f"SW_CAMPUS_{i}" for i in range(1, 11)}
    assert all("(placeholder)" in z["label"] for z in layers["zones"])


def test_layout_matches_topology() -> None:
    layout = load_layout("campus_v1")
    assert layout.topology_id == "campus_v1"


@pytest.mark.parametrize(
    ("failed", "isolated", "degraded"),
    [
        (
            "SW_CAMPUS_2",
            ["SW_CAMPUS_10", "SW_CAMPUS_4", "SW_CAMPUS_5"],
            ["SW_CAMPUS_3", "SW_CAMPUS_8"],
        ),
        ("SW_CAMPUS_4", [], []),
    ],
)
def test_blast_radius_states(failed: str, isolated: list[str], degraded: list[str]) -> None:  # S-16
    br = blast_radius("campus_v1", failed)
    assert br["isolated"] == isolated and br["degraded"] == degraded
    assert "structural" in br["basis"]
    assert br["zones_isolated"] == sorted({z for z in br["zones_isolated"]})


def test_blast_radius_unknown_without_topology() -> None:  # T-GEO-BLAST-02
    br = blast_radius(None, "SW_CAMPUS_2")
    assert br["unknown"] == ["SW_CAMPUS_2"] and br["isolated"] == []


def _incident(tmp_path: Path, scenario: str, community: bool) -> tuple[LogStore, str]:
    store = LogStore(tmp_path / "g.sqlite3")
    raw = load_scenario(scenario).input_bytes
    if not community:
        return store, Orchestrator(store).run(raw).incident_id
    pipe = CommunityPipeline(store)
    pipe.submit("Hostel A Wi-Fi is disconnecting.", channel="web_form", reporter="a", received_at=T)
    pipe.submit("hostel a wifi keeps dropping", channel="web_form", reporter="b", received_at=T)
    cand = pipe.candidates()[0]
    # Setup (P4): community input needs the community_signals extension switched on.
    s = load_settings()
    on = s.model_copy(
        update={"features": s.features.model_copy(update={"community_signals": True})}
    )
    return store, pipe.investigate(
        cand.candidate_id, Orchestrator(store, settings=on), raw
    ).incident_id


def test_reported_and_detected_layers_are_separate(tmp_path: Path) -> None:  # T-GEO-LAYER
    store, inc = _incident(tmp_path, "S-01", community=True)  # complaints, healthy telemetry
    ov = incident_overlay(store, inc)
    assert [a["zone"] for a in ov["reported_areas"]] == ["ZONE_HOSTEL_A"]
    assert ov["reported_areas"][0]["trust_label"] == "reported_unverified"
    assert ov["reported_areas"][0]["style"] == "reported"
    assert ov["detected_faults"] == [] and ov["corroborated"] == []


def test_corroborated_layer(tmp_path: Path) -> None:
    store, inc = _incident(tmp_path, "S-02", community=True)
    ov = incident_overlay(store, inc)
    assert [d["entity"] for d in ov["detected_faults"]] == ["SW_CAMPUS_4"]
    assert ov["detected_faults"][0]["style"] == "detected"
    assert [c["zone"] for c in ov["corroborated"]] == ["ZONE_HOSTEL_A"]


def test_incident_panel(tmp_path: Path) -> None:  # T-GEO-PANEL-01
    store, inc = _incident(tmp_path, "S-02", community=False)
    panel = incident_overlay(store, inc)["panel"]
    for key in (
        "status",
        "suspected_root_cause",
        "confidence",
        "confidence_method",
        "affected_devices",
        "supporting_evidence",
        "alternative_causes",
        "limitations",
        "not_assessable",
        "recommendations",
        "blast_radius",
        "community_summary",
        "trace_url",
    ):
        assert key in panel, key
    assert panel["confidence_method"] == "heuristic"
    assert all(r["simulated"] and r["requires_human_approval"] for r in panel["recommendations"])


def test_geo_api_behind_flag(tmp_path: Path) -> None:
    off = TestClient(create_app(db_path=tmp_path / "a.sqlite3"))
    assert off.get("/api/geo/layers").status_code == 404
    s = load_settings()
    on_settings = s.model_copy(
        update={"features": s.features.model_copy(update={"geospatial": True})}
    )
    on = TestClient(create_app(db_path=tmp_path / "b.sqlite3", settings=on_settings))
    assert on.get("/api/geo/layers").json()["crs"] == "schematic"
    br = on.get("/api/geo/blast-radius/SW_CAMPUS_2").json()
    assert br["degraded"] == ["SW_CAMPUS_3", "SW_CAMPUS_8"]
    inc = on.post("/api/scenarios/S-02/run", json={}).json()["incident_id"]
    ov = on.get(f"/api/geo/incidents/{inc}").json()
    assert ov["detected_faults"][0]["entity"] == "SW_CAMPUS_4"
    assert on.get("/api/geo/incidents/INC-9999").status_code == 404


def test_blast_radius_zones_are_concrete() -> None:
    br = blast_radius("campus_v1", "SW_CAMPUS_2")
    assert br["zones_isolated"] == ["ZONE_ADMIN", "ZONE_HOSTEL_A", "ZONE_HOSTEL_B"]
    assert br["zones_degraded"] == ["ZONE_DATA_CENTRE", "ZONE_LECTURE_HALLS"]
