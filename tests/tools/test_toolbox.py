"""Read-only tool layer: permissions, budgets, call records, no write path (T-TOOL-*, T-SAFE-01)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from netcoop.core.ids import FixedClock
from netcoop.ingestion.normalize import ingest
from netcoop.tools.toolbox import (
    TOOL_NAMES,
    TOOL_PERMISSIONS,
    ToolBox,
    ToolBudgetExceeded,
    ToolNotAllowed,
)
from netcoop.tools.topology import load_topology

T0 = datetime(2026, 10, 31, 12, tzinfo=UTC)


def _rec(device: str, minutes: int, latency: float, status: str = "Healthy") -> dict[str, Any]:
    return {
        "timestamp": (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "device_id": device,
        "status": status,
        "metrics": {
            "cpu_utilization_pct": 20.0,
            "link_utilization_pct": 30.0,
            "packet_loss_pct": 0.0,
            "latency_ms": latency,
            "jitter_ms": 2.0,
            "queue_drops": 0,
        },
    }


@pytest.fixture
def box() -> ToolBox:
    raw = {
        "records": [
            _rec("SW_CAMPUS_4", 0, 10),
            _rec("SW_CAMPUS_4", 5, 300, "Warning"),
            _rec("SW_CAMPUS_2", 5, 12),
            _rec("GHOST_SW", 5, 12),
        ],
        "topology_ref": "campus_v1",
        "probes": [
            {
                "probe_id": "P1",
                "from_entity": "SW_CAMPUS_4",
                "service": "dns",
                "outcome": "failure",
                "timestamp": "2026-10-31T12:05:00Z",
            }
        ],
    }
    bundle = ingest(json.dumps(raw)).bundle
    assert bundle is not None
    return ToolBox(bundle, load_topology("campus_v1"), clock=FixedClock(T0))


def test_telemetry_query_returns_time_ordered_samples(box: ToolBox) -> None:
    s = box.session("performance_agent", budget=5)
    samples = s.telemetry_query(["SW_CAMPUS_4"], ["latency_ms", "status"])
    assert [(x.metric, x.value) for x in samples] == [
        ("latency_ms", 10.0),
        ("status", "Healthy"),
        ("latency_ms", 300.0),
        ("status", "Warning"),
    ]
    assert samples[0].record_id == "REC-0001"
    rec = s.records[0]
    assert rec.tool == "telemetry_query"
    assert rec.arguments == {"entities": ["SW_CAMPUS_4"], "metrics": ["latency_ms", "status"]}
    assert "4 samples" in rec.result_summary


def test_coverage_query(box: ToolBox) -> None:
    s = box.session("infrastructure_agent", budget=5)
    cov = s.coverage_query(["SW_CAMPUS_4"], ["interface_errors", "latency_ms"])
    assert cov[("SW_CAMPUS_4", "interface_errors")].reason == "MISSING"
    assert cov[("SW_CAMPUS_4", "latency_ms")].assessability == "assessed"
    unknown = s.coverage_query(["NOT_THERE"], ["latency_ms"])
    assert unknown[("NOT_THERE", "latency_ms")].reason == "OUT_OF_SCOPE"


def test_budget_is_enforced(box: ToolBox) -> None:
    s = box.session("performance_agent", budget=2)
    s.list_entities()
    s.data_quality()
    assert s.remaining == 0 and s.exhausted
    with pytest.raises(ToolBudgetExceeded):
        s.list_entities()
    assert len(s.records) == 2


def test_permissions_are_enforced(box: ToolBox) -> None:
    s = box.session("performance_agent", budget=5)
    with pytest.raises(ToolNotAllowed):
        s.what_if_failure("SW_CAMPUS_2")
    assert s.records == []


def test_topology_tools(box: ToolBox) -> None:
    s = box.session("connectivity_agent", budget=10)
    info = s.topology_info()
    assert info.available and info.provenance == "SIMULATED"
    assert info.entities_not_in_topology == ["GHOST_SW"]
    assert s.topology_path("SW_CAMPUS_4") == ["SW_CAMPUS_4", "SW_CAMPUS_2", "SW_CAMPUS_1"]
    assert s.zone_entities("ZONE_HOSTEL_A") == ["SW_CAMPUS_4"]
    assert s.what_if_failure("SW_CAMPUS_2").isolated == [
        "SW_CAMPUS_10",
        "SW_CAMPUS_4",
        "SW_CAMPUS_5",
    ]
    assert s.topology_path("GHOST_SW") is None
    assert [p.outcome for p in s.probe_query("dns")] == ["failure"]


def test_missing_topology_means_unknown_not_empty(box: ToolBox) -> None:
    no_topo = ToolBox(box.bundle, None, clock=FixedClock(T0))
    s = no_topo.session("connectivity_agent", budget=10)
    info = s.topology_info()
    assert not info.available
    assert s.topology_path("SW_CAMPUS_4") is None
    assert s.what_if_failure("SW_CAMPUS_2").unknown == ["SW_CAMPUS_2"]
    assert s.neighbors("SW_CAMPUS_4") is None


def test_no_state_changing_tool_exists() -> None:  # T-SAFE-01
    forbidden = re.compile(
        r"set|write|update|delete|apply|exec|restart|reboot|shutdown|config|push|remediat"
    )
    assert not [t for t in TOOL_NAMES if forbidden.search(t)]
    for agent, tools in TOOL_PERMISSIONS.items():
        assert set(tools) <= set(TOOL_NAMES), agent
    public = [m for m in dir(ToolBox) if not m.startswith("_")]
    assert public == ["bundle", "session", "topology", "window"]  # all read-only


def test_results_cannot_mutate_the_bundle(box: ToolBox) -> None:
    s = box.session("performance_agent", budget=5)
    sample = s.telemetry_query(["SW_CAMPUS_4"], ["latency_ms"])[0]
    with pytest.raises(ValidationError):  # frozen model
        sample.value = 0  # type: ignore[misc]
    again = box.session("performance_agent", budget=5).telemetry_query(
        ["SW_CAMPUS_4"], ["latency_ms"]
    )
    assert again[0].value == 10.0
