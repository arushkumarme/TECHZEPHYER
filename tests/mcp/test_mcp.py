"""MCP server and MCP-backed agent tools (component 8; T-MCP-*)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mcp import Client, StdioServerParameters
from netcoop.agents.connectivity import ConnectivityAgent
from netcoop.agents.infrastructure import InfrastructureAgent
from netcoop.agents.performance import PerformanceAgent
from netcoop.core.bus import MessageBus
from netcoop.core.ids import FixedClock, IdFactory
from netcoop.core.log_store import LogStore
from netcoop.core.messages import Finding, TaskRequest, payload_as
from netcoop.diagnosis.params import load_diagnosis_params
from netcoop.mcp.adapter import McpToolBox
from netcoop.mcp.server import build_server, load_source
from netcoop.scenarios.runner import load_scenario
from netcoop.tools.toolbox import TOOL_NAMES

T0 = datetime(2026, 10, 31, 12, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def store(tmp_path: Path) -> LogStore:
    return LogStore(tmp_path / "log.sqlite3")


@pytest.mark.anyio
async def test_tools_are_read_only_and_complete(store: LogStore) -> None:  # T-MCP-01
    async with Client(build_server(store)) as client:
        tools = (await client.list_tools()).tools
    names = {t.name for t in tools}
    assert {f"netcoop_{t}" for t in TOOL_NAMES} <= names
    for t in tools:
        assert t.name.startswith("netcoop_")
        assert t.annotations is not None and t.annotations.read_only_hint is True, t.name
        assert t.annotations.open_world_hint is False
        assert t.description


@pytest.mark.anyio
async def test_tool_matches_direct_tool_layer(store: LogStore) -> None:  # T-MCP-02
    direct = load_source(store, "S-02").session("mcp_gateway", 5)
    expected = [
        s.model_dump(mode="json") for s in direct.telemetry_query(["SW_CAMPUS_4"], ["latency_ms"])
    ]
    async with Client(build_server(store)) as client:
        r = await client.call_tool(
            "netcoop_telemetry_query",
            {"source": "S-02", "entities": ["SW_CAMPUS_4"], "metrics": ["latency_ms"]},
        )
    assert not r.is_error
    assert r.structured_content is not None
    assert r.structured_content["samples"] == expected


@pytest.mark.anyio
async def test_unknown_source_is_an_actionable_error(store: LogStore) -> None:
    async with Client(build_server(store)) as client:
        r = await client.call_tool("netcoop_list_entities", {"source": "NOPE"})
    assert r.is_error
    text = " ".join(getattr(c, "text", "") for c in r.content)
    assert "netcoop_list_sources" in text  # tells the caller how to recover


@pytest.mark.anyio
async def test_resources(store: LogStore) -> None:  # T-MCP-03
    from netcoop.orchestrator.workflow import Orchestrator

    inc = Orchestrator(store).run(load_scenario("S-01").input_bytes).incident_id
    async with Client(build_server(store)) as client:
        scen = await client.read_resource("netcoop://scenarios")
        report = await client.read_resource(f"netcoop://incidents/{inc}/report")
        fields = await client.read_resource("netcoop://field-dictionary")
        topo = await client.read_resource("netcoop://topology/campus_v1")
        sources = await client.call_tool("netcoop_list_sources", {})
    assert "S-02" in json.dumps(json.loads(scen.contents[0].text))  # type: ignore[union-attr]
    assert json.loads(report.contents[0].text)["status"] == "no_fault_detected"  # type: ignore[union-attr]
    assert "latency_ms" in json.loads(fields.contents[0].text)["fields"]  # type: ignore[union-attr]
    assert json.loads(topo.contents[0].text)["provenance"] == "SIMULATED"  # type: ignore[union-attr]
    assert sources.structured_content is not None
    assert inc in sources.structured_content["incidents"]


def _finding(agent_cls: type, box: Any, bus: MessageBus) -> dict[str, Any]:
    agent = agent_cls(bus, lambda _i: box, load_diagnosis_params())
    bus.register(agent.agent_id, agent.handle)
    bundle = load_source(LogStore(":memory:"), "S-02").bundle
    reply = bus.request(
        sender="orchestrator",
        recipient=agent.agent_id,
        message_type="task_request",
        payload=TaskRequest(
            goal=agent.goal,
            scope_entities=list(bundle.entities),
            window=bundle.window,
            tool_budget=40,
            deadline_s=10,
        ),
        incident_id="INC-0001",
    )
    return payload_as(reply, Finding).model_dump(mode="json")


@pytest.mark.parametrize("agent_cls", [PerformanceAgent, InfrastructureAgent, ConnectivityAgent])
def test_agents_through_mcp_equal_direct(store: LogStore, agent_cls: type) -> None:  # T-MCP-04
    clock = FixedClock(T0)
    direct = load_source(store, "S-02", clock=clock)
    a = _finding(agent_cls, direct, MessageBus(LogStore(":memory:"), clock=clock, ids=IdFactory()))
    with McpToolBox(build_server(store), source="S-02", clock=clock) as via_mcp:
        b = _finding(
            agent_cls, via_mcp, MessageBus(LogStore(":memory:"), clock=clock, ids=IdFactory())
        )
    assert a == b  # same observations, hypotheses, facts AND the same tool-call trail
    assert b["tool_calls"], "the agent must have used tools"


def test_orchestrator_with_mcp_transport(tmp_path: Path) -> None:  # T-MCP-05
    from netcoop.config.settings import load_settings
    from netcoop.orchestrator.workflow import Orchestrator

    base = load_settings()
    mcp_settings = base.model_copy(
        update={"orchestration": base.orchestration.model_copy(update={"tool_transport": "mcp"})}
    )
    raw = load_scenario("S-02").input_bytes
    direct = Orchestrator(LogStore(tmp_path / "a.sqlite3")).run(raw).report
    mcp_store = LogStore(tmp_path / "b.sqlite3")
    result = Orchestrator(mcp_store, settings=mcp_settings).run(raw)
    via = result.report
    dispatched = next(
        t for t in mcp_store.transitions(result.incident_id) if t.to_state == "DISPATCHED"
    )
    assert dispatched.detail["tool_transport"] == "mcp"  # the MCP path really ran
    assert result.findings["performance_agent"].tool_calls
    for key in (
        "status",
        "suspected_root_cause",
        "confidence",
        "affected_devices",
        "supporting_evidence",
        "evidence_sources",
    ):
        assert via[key] == direct[key], key


@pytest.mark.anyio
async def test_stdio_server_subprocess(tmp_path: Path) -> None:  # T-MCP-06
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "netcoop.mcp.server", "--db", str(tmp_path / "s.sqlite3")],
        cwd=str(REPO),
    )
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        r = await client.call_tool("netcoop_data_quality", {"source": "S-01"})
    assert len(tools) >= len(TOOL_NAMES)
    assert r.structured_content is not None
    assert r.structured_content["note"]["acceptance"] == "READY"
