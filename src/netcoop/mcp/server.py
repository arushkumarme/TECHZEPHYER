"""NetCoop AI MCP server (official component 8: "expose diagnostic tools, telemetry or
contextual resources to agents"). Simulation mode only; every tool is read-only.

Tools (``netcoop_*``) wrap the same read-only tool layer the in-process agents use
(:mod:`netcoop.tools.toolbox`), so results are identical whichever path is taken. Each
tool takes a ``source``: a scenario id (``S-02``) or a stored incident id (``INC-0001``).

Resources: ``netcoop://scenarios``, ``netcoop://scenarios/{scenario_id}``,
``netcoop://incidents``, ``netcoop://incidents/{incident_id}/report``,
``netcoop://incidents/{incident_id}/trace``, ``netcoop://field-dictionary``,
``netcoop://topology/{topology_id}``.

Run over stdio::

    uv run python -m netcoop.mcp.server --db var/netcoop.sqlite3
"""

from __future__ import annotations

import argparse
import base64
import json
import threading
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from netcoop.config.fields import load_field_dictionary
from netcoop.core.ids import Clock, SystemClock
from netcoop.core.log_store import LogStore
from netcoop.ingestion.normalize import ingest
from netcoop.orchestrator.trace import render_trace
from netcoop.scenarios.generator import REPO_ROOT
from netcoop.scenarios.runner import list_scenarios, load_scenario
from netcoop.tools.toolbox import ToolBox, ToolSession
from netcoop.tools.topology import TopologyError, load_topology

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
GATEWAY = "mcp_gateway"
INSTRUCTIONS = (
    "NetCoop AI diagnostic tools over SIMULATED network telemetry (scenario playback; no "
    "access to any real network). All tools are read-only. Call netcoop_list_sources first "
    "to get a valid `source` (scenario id like S-02 or incident id like INC-0001)."
)


class SourceError(ToolError):
    """A deliberate, client-visible error: its message (with a recovery hint) reaches the
    MCP caller. Unexpected crashes stay generic, as the SDK intends."""


def _raw_input(store: LogStore, source: str) -> bytes:
    if source in list_scenarios():
        return load_scenario(source).input_bytes
    for cp in store.checkpoints(source):
        if cp["kind"] == "input":
            return base64.b64decode(cp["data"]["raw_b64"])
    raise SourceError(
        f"unknown source {source!r}: call netcoop_list_sources for valid scenario and incident ids"
    )


def load_source(store: LogStore, source: str, *, clock: Clock | None = None) -> ToolBox:
    """Build the read-only tool layer for a scenario or stored incident."""
    result = ingest(_raw_input(store, source))
    if result.bundle is None:
        raise SourceError(f"source {source!r} was rejected by validation ({result.rejection_code})")
    topology = None
    if result.bundle.topology_ref:
        try:
            topology = load_topology(result.bundle.topology_ref)
        except (TopologyError, ValueError):
            topology = None
    return ToolBox(result.bundle, topology, clock=clock or SystemClock())


def build_server(store: LogStore) -> MCPServer:
    mcp = MCPServer("netcoop", instructions=INSTRUCTIONS)
    cache: dict[str, ToolBox] = {}
    lock = threading.Lock()

    def toolbox(source: str) -> ToolBox:
        with lock:
            if source not in cache:
                cache[source] = load_source(store, source)
            return cache[source]

    def session(source: str) -> ToolSession:
        return toolbox(source).session(GATEWAY, 1)

    # ------------------------------------------------------------------ tools
    @mcp.tool(annotations=READ_ONLY)
    def netcoop_list_sources() -> dict[str, Any]:
        """List valid `source` values: frozen scenario ids and stored incident ids."""
        return {"scenarios": list_scenarios(), "incidents": store.list_incidents()}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_bundle_info(source: str) -> dict[str, Any]:
        """Entities, time window and data provenance of a source's normalized telemetry."""
        b = toolbox(source).bundle
        return {
            "entities": b.entities,
            "window": {"start": b.window.start.isoformat(), "end": b.window.end.isoformat()},
            "provenance": b.provenance,
            "topology_ref": b.topology_ref,
        }

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_list_entities(source: str) -> dict[str, Any]:
        """Device ids present in the source's telemetry."""
        return {"entities": session(source).list_entities()}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_telemetry_query(
        source: str, entities: list[str], metrics: list[str] | None = None
    ) -> dict[str, Any]:
        """Time-ordered samples (record id, entity, timestamp, metric, value) for devices.
        Metric names are the generator's (e.g. latency_ms) plus `status`; omit to get all."""
        samples = session(source).telemetry_query(entities, metrics)
        return {"samples": [s.model_dump(mode="json") for s in samples]}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_coverage_query(
        source: str, entities: list[str], items: list[str] | None = None
    ) -> dict[str, Any]:
        """Assessability of each device-item pair: assessed / assessed_with_caveat /
        not_assessable with a reason. Missing data is never reported as healthy."""
        cov = session(source).coverage_query(entities, items)
        return {
            "pairs": [
                {"entity": e, "item": i, **state.model_dump(mode="json")}
                for (e, i), state in cov.items()
            ]
        }

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_data_quality(source: str) -> dict[str, Any]:
        """Data-quality note: completeness, freshness, consistency, acceptance, warnings."""
        note = session(source).data_quality()
        return {"note": {**note.model_dump(mode="json"), "q": note.q}}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_topology_info(source: str) -> dict[str, Any]:
        """Whether a (SIMULATED) topology is available, its id, core nodes and device zones."""
        return session(source).topology_info().model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_neighbors(source: str, entity: str) -> dict[str, Any]:
        """Directly linked devices; null if topology or device is unknown."""
        return {"result": session(source).neighbors(entity)}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_topology_path(source: str, entity: str) -> dict[str, Any]:
        """Upstream path from a device to the core; null if unknown."""
        return {"result": session(source).topology_path(entity)}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_what_if_failure(source: str, entity: str) -> dict[str, Any]:
        """Structural blast radius if `entity` failed: isolated / degraded / unaffected /
        unknown devices (structure only, not measured impact)."""
        return session(source).what_if_failure(entity).model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_zone_entities(source: str, zone: str) -> dict[str, Any]:
        """Devices serving a (placeholder) zone such as ZONE_HOSTEL_A; null if unknown."""
        return {"result": session(source).zone_entities(zone)}

    @mcp.tool(annotations=READ_ONLY)
    def netcoop_probe_query(source: str, service: str | None = None) -> dict[str, Any]:
        """Team-authored DNS/DHCP probe results (labelled; never generator telemetry)."""
        probes = session(source).probe_query(service)
        return {"probes": [p.model_dump(mode="json") for p in probes]}

    # ------------------------------------------------------------------ resources
    @mcp.resource("netcoop://scenarios", mime_type="application/json")
    def scenarios() -> str:
        """Frozen scenario packages with titles and provenance."""
        return json.dumps(
            [
                {k: load_scenario(s).meta[k] for k in ("id", "title", "provenance")}
                for s in list_scenarios()
            ]
        )

    @mcp.resource("netcoop://scenarios/{scenario_id}", mime_type="application/json")
    def scenario(scenario_id: str) -> str:
        """Metadata and expected outcome of one scenario."""
        return json.dumps(load_scenario(scenario_id).meta)

    @mcp.resource("netcoop://incidents", mime_type="application/json")
    def incidents() -> str:
        """Stored incidents with their latest state."""
        out = []
        for inc in store.list_incidents():
            t = store.transitions(inc)
            out.append({"incident_id": inc, "state": t[-1].to_state if t else None})
        return json.dumps(out)

    @mcp.resource("netcoop://incidents/{incident_id}/report", mime_type="application/json")
    def report(incident_id: str) -> str:
        """Latest report version of an incident (official keys + netcoop_extensions)."""
        stored = store.latest_report(incident_id)
        if stored is None:
            raise SourceError(f"{incident_id} has no report yet")
        return json.dumps(stored[0])

    @mcp.resource("netcoop://incidents/{incident_id}/trace", mime_type="text/plain")
    def trace(incident_id: str) -> str:
        """Ordered state transitions and agent messages of an incident."""
        return render_trace(store, incident_id)

    @mcp.resource("netcoop://field-dictionary", mime_type="application/json")
    def field_dictionary() -> str:
        """Telemetry fields observed in the organizer generator (doc 06)."""
        return load_field_dictionary().model_dump_json(by_alias=True)

    @mcp.resource("netcoop://topology/{topology_id}", mime_type="application/json")
    def topology(topology_id: str) -> str:
        """A SIMULATED topology file."""
        return load_topology(topology_id).model_dump_json()

    return mcp


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="NetCoop AI MCP server (stdio, read-only)")
    p.add_argument("--db", default=str(REPO_ROOT / "var" / "netcoop.sqlite3"))
    args = p.parse_args(argv)
    build_server(LogStore(Path(args.db))).run()


if __name__ == "__main__":
    main()
