"""Simulated topology: paths, neighbours, what-if blast radius (T-AGT-CONN prerequisites,
T-GEO-BLAST-* semantics: isolated vs degraded vs unknown)."""

import json
from pathlib import Path

import pytest

from netcoop.tools.topology import TopologyError, load_topology


@pytest.fixture(scope="module")
def topo():  # type: ignore[no-untyped-def]
    return load_topology("campus_v1")


def test_loads_with_simulated_provenance(topo) -> None:  # type: ignore[no-untyped-def]
    assert topo.provenance == "SIMULATED"
    assert len(topo.nodes) == 10
    assert topo.zone_of("SW_CAMPUS_4") == "ZONE_HOSTEL_A"
    assert topo.entities_in_zone("ZONE_HOSTEL_A") == ["SW_CAMPUS_4"]


def test_upstream_path(topo) -> None:  # type: ignore[no-untyped-def]
    assert topo.path_to_core("SW_CAMPUS_4") == ["SW_CAMPUS_4", "SW_CAMPUS_2", "SW_CAMPUS_1"]
    assert topo.upstream_of("SW_CAMPUS_4") == ["SW_CAMPUS_2", "SW_CAMPUS_1"]
    assert topo.path_to_core("SW_CAMPUS_1") == ["SW_CAMPUS_1"]


def test_neighbors(topo) -> None:  # type: ignore[no-untyped-def]
    assert topo.neighbors("SW_CAMPUS_8") == ["SW_CAMPUS_2", "SW_CAMPUS_3"]


def test_what_if_distribution_failure(topo) -> None:  # type: ignore[no-untyped-def]
    r = topo.what_if_failure("SW_CAMPUS_2")
    assert r.isolated == ["SW_CAMPUS_10", "SW_CAMPUS_4", "SW_CAMPUS_5"]
    assert r.degraded == ["SW_CAMPUS_3", "SW_CAMPUS_8"]  # redundancy remains
    assert "SW_CAMPUS_6" in r.unaffected
    assert r.unknown == []


def test_what_if_core_failure_isolates_everything(topo) -> None:  # type: ignore[no-untyped-def]
    r = topo.what_if_failure("SW_CAMPUS_1")
    assert len(r.isolated) == 9 and r.degraded == []


def test_what_if_access_failure_affects_nothing_else(topo) -> None:  # type: ignore[no-untyped-def]
    r = topo.what_if_failure("SW_CAMPUS_4")
    assert r.isolated == [] and r.degraded == []


def test_unknown_entity(topo) -> None:  # type: ignore[no-untyped-def]
    assert topo.path_to_core("ROUTER_X") is None
    r = topo.what_if_failure("ROUTER_X")
    assert r.unknown == ["ROUTER_X"]


def test_invalid_topology_rejected(tmp_path: Path) -> None:
    bad = json.loads((Path("sample_data/topology/campus_v1.json")).read_text())
    bad["links"].append({"id": "L-x", "a": "SW_CAMPUS_1", "b": "GHOST"})
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(TopologyError, match="GHOST"):
        load_topology(p)
    with pytest.raises(TopologyError):
        load_topology("does_not_exist")
