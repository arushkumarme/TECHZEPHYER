# 16 — Model Context Protocol interface (component 8)

> Version 0.1 · 2026-10-31 · `IMPLEMENTED`, `TESTED` · Owner scope decision ID-01 brought MCP into scope (it was "not used at this stage" in doc 00 CD-2).

`SRC-1 p3 §4`: MCP is optional and "may be used to expose diagnostic tools, telemetry or contextual resources to agents". NetCoop AI does both directions:

1. **Server** — `src/netcoop/mcp/server.py` exposes the read-only tool layer and project resources to any MCP client (e.g. a desktop LLM host).
2. **Agents as MCP clients** — with `[orchestration] tool_transport = "mcp"`, the three specialist agents read telemetry and topology *through* the MCP server (`src/netcoop/mcp/adapter.py`). The in-process message bus stays the agent-to-agent protocol (doc 05); MCP is the agent-to-tool interface.

## Tools (all `read_only_hint = true`, `open_world_hint = false`)

`netcoop_list_sources`, `netcoop_bundle_info`, `netcoop_list_entities`, `netcoop_telemetry_query`, `netcoop_coverage_query`, `netcoop_data_quality`, `netcoop_topology_info`, `netcoop_neighbors`, `netcoop_topology_path`, `netcoop_what_if_failure`, `netcoop_zone_entities`, `netcoop_probe_query`. Every tool takes `source` = a scenario id (`S-02`) or a stored incident id (`INC-0001`). An unknown source returns an error that names `netcoop_list_sources` as the way to recover. There are no write tools.

## Resources

`netcoop://scenarios`, `netcoop://scenarios/{scenario_id}`, `netcoop://incidents`, `netcoop://incidents/{incident_id}/report`, `netcoop://incidents/{incident_id}/trace`, `netcoop://field-dictionary`, `netcoop://topology/{topology_id}`.

## Running

```bash
uv run netcoop-mcp --db var/netcoop.sqlite3        # stdio server
```

Host configuration example (any MCP host that launches stdio servers):

```json
{ "mcpServers": { "netcoop": {
    "command": "uv",
    "args": ["run", "--directory", "<path-to>/netcoop-ai", "netcoop-mcp"] } } }
```

## Evidence (`tests/mcp/test_mcp.py`)

- every tool is listed, prefixed, described and annotated read-only (T-MCP-01);
- an MCP tool result equals the direct tool-layer result (T-MCP-02);
- resources serve scenarios, a stored report, the field dictionary and the SIMULATED topology (T-MCP-03);
- **each specialist agent produces an identical finding — observations, hypotheses, facts and the same tool-call trail — whether it reads directly or through MCP** (T-MCP-04);
- a full orchestrated run with `tool_transport = "mcp"` (verified in the dispatch record) yields the same report content as the direct run (T-MCP-05);
- the stdio server works as a real subprocess (T-MCP-06).

SDK: `mcp` 2.3.0 (Python SDK v2, `MCPServer`), API checked against the v2.3.0 documentation on 2026-10-31.
