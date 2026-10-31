"""MCP-backed tool layer for the agents (component 8, the agent side).

:class:`McpToolBox` offers the same interface as :class:`~netcoop.tools.toolbox.ToolBox`,
but every data read is an MCP ``tools/call`` to the NetCoop MCP server. The session
subclasses the real :class:`ToolSession`, so permissions, budgets and the recorded
tool-call trail are identical; only *where the data comes from* changes. The agents are
synchronous, so calls cross into the async MCP client through an anyio blocking portal
(thread-safe, so parallel specialists can share one connection).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from datetime import datetime
from typing import Any, Self, TypeVar

from anyio.from_thread import BlockingPortal, start_blocking_portal
from mcp.server.mcpserver import MCPServer

from mcp import Client, StdioServerParameters
from netcoop.core.blocks import TimeWindow, ToolCallRecord
from netcoop.core.ids import Clock, SystemClock
from netcoop.ingestion.models import DataQualityNote, MetricState, ProbeResult
from netcoop.tools.toolbox import (
    Sample,
    ToolBudgetExceeded,
    ToolError,
    ToolNotAllowed,
    ToolSession,
    TopologyInfo,
)
from netcoop.tools.topology import WhatIfResult

T = TypeVar("T")


class McpToolError(ToolError):
    """The MCP server reported an error for a tool call."""


def _coverage(sc: dict[str, Any]) -> dict[tuple[str, str], MetricState]:
    return {
        (p["entity"], p["item"]): MetricState.model_validate(
            {k: v for k, v in p.items() if k not in ("entity", "item")}
        )
        for p in sc["pairs"]
    }


def _note(sc: dict[str, Any]) -> DataQualityNote:
    return DataQualityNote.model_validate({k: v for k, v in sc["note"].items() if k != "q"})


#: How each tool's structured MCP result is turned back into the in-process type.
CONVERT: dict[str, Callable[[dict[str, Any]], Any]] = {
    "list_entities": lambda sc: list(sc["entities"]),
    "telemetry_query": lambda sc: [Sample.model_validate(s) for s in sc["samples"]],
    "coverage_query": _coverage,
    "data_quality": _note,
    "topology_info": TopologyInfo.model_validate,
    "neighbors": lambda sc: sc["result"],
    "topology_path": lambda sc: sc["result"],
    "zone_entities": lambda sc: sc["result"],
    "what_if_failure": WhatIfResult.model_validate,
    "probe_query": lambda sc: [ProbeResult.model_validate(p) for p in sc["probes"]],
}


class McpToolSession(ToolSession):
    def __init__(self, box: McpToolBox, *, agent: str, budget: int) -> None:
        # No local bundle/topology: data only ever arrives over MCP.
        super().__init__(None, None, box.clock, agent=agent, budget=budget)  # type: ignore[arg-type]
        self._box = box

    def _call(
        self,
        tool: str,
        arguments: dict[str, Any],
        fn: Callable[[], T],
        summarize: Callable[[T], str],
    ) -> T:
        if tool not in self.allowed:
            raise ToolNotAllowed(f"{self.agent} may not call {tool}")
        if self.exhausted:
            raise ToolBudgetExceeded(f"{self.agent} used its budget of {self.budget} calls")
        result: T = CONVERT[tool](self._box.call(f"netcoop_{tool}", arguments))
        self.records.append(
            ToolCallRecord(
                tool=tool,
                arguments=arguments,
                result_summary=summarize(result),
                at=self._clock.now(),
            )
        )
        return result


class McpToolBox:
    """Drop-in replacement for ToolBox that reads through an MCP server.

    ``target`` is an in-process :class:`MCPServer` or :class:`StdioServerParameters` for a
    subprocess server. Use as a context manager (opens/closes the MCP session)."""

    def __init__(
        self,
        target: MCPServer | StdioServerParameters,
        *,
        source: str,
        clock: Clock | None = None,
    ) -> None:
        self.target = target
        self.source = source
        self.clock: Clock = clock or SystemClock()
        self._stack = ExitStack()
        self._portal: BlockingPortal | None = None
        self._client: Client | None = None
        self._window: TimeWindow | None = None

    def __enter__(self) -> Self:
        portal_cm: AbstractContextManager[BlockingPortal] = start_blocking_portal()
        self._portal = self._stack.enter_context(portal_cm)
        self._client = self._stack.enter_context(
            self._portal.wrap_async_context_manager(Client(self.target))
        )
        info = self.call("netcoop_bundle_info", {})
        self._window = TimeWindow(
            start=datetime.fromisoformat(info["window"]["start"]),
            end=datetime.fromisoformat(info["window"]["end"]),
        )
        return self

    def __exit__(self, *exc: object) -> None:
        self._stack.close()
        self._portal = self._client = None

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._portal is None or self._client is None:
            raise McpToolError("McpToolBox is not open; use it as a context manager")
        client = self._client
        result = self._portal.call(client.call_tool, name, {"source": self.source, **arguments})
        if result.is_error or result.structured_content is None:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise McpToolError(f"{name} failed over MCP: {text}")
        return dict(result.structured_content)

    @property
    def window(self) -> TimeWindow:
        if self._window is None:
            raise McpToolError("McpToolBox is not open")
        return self._window

    def session(self, agent: str, budget: int) -> McpToolSession:
        return McpToolSession(self, agent=agent, budget=budget)
