"""Read-only tool layer (doc 02 C-TOOL, doc 03 §1 items 2-3, doc 12 §3).

Agents read data only through a :class:`ToolSession`: it checks the agent's permissions,
enforces the per-task call budget, and records every call as a
:class:`~netcoop.core.blocks.ToolCallRecord` that goes into the agent's finding. The
whole layer is read-only — there is no tool that writes, configures or changes anything
(``T-SAFE-01``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict

from netcoop.core.blocks import TimeWindow, ToolCallRecord
from netcoop.core.ids import Clock
from netcoop.core.vocab import AgentId
from netcoop.ingestion.models import (
    STATUS_ITEM,
    DataQualityNote,
    MetricState,
    NormalizedBundle,
    ProbeResult,
)
from netcoop.tools.topology import Topology, WhatIfResult

T = TypeVar("T")

TOOL_NAMES: tuple[str, ...] = (
    "list_entities",
    "telemetry_query",
    "coverage_query",
    "data_quality",
    "topology_info",
    "neighbors",
    "topology_path",
    "what_if_failure",
    "zone_entities",
    "probe_query",
)
_METRIC_TOOLS = ("list_entities", "telemetry_query", "coverage_query", "data_quality")
TOOL_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "performance_agent": _METRIC_TOOLS,
    "infrastructure_agent": _METRIC_TOOLS,
    "connectivity_agent": (
        *_METRIC_TOOLS,
        "topology_info",
        "neighbors",
        "topology_path",
        "what_if_failure",
        "zone_entities",
        "probe_query",
    ),
    "correlation_agent": ("data_quality", "topology_info"),
    "reporting_agent": ("data_quality",),
    # The MCP server (component 8) exposes every read-only tool to MCP clients.
    "mcp_gateway": TOOL_NAMES,
}


class ToolError(RuntimeError):
    pass


class ToolNotAllowed(ToolError):
    pass


class ToolBudgetExceeded(ToolError):
    pass


class Sample(BaseModel):
    """One value of one item at one time, traceable to a normalized record."""

    model_config = ConfigDict(frozen=True)
    record_id: str
    entity: str
    timestamp: datetime
    metric: str
    value: float | str
    flags: tuple[str, ...] = ()


class TopologyInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    available: bool
    topology_id: str | None = None
    provenance: str | None = None
    entities_not_in_topology: list[str] = []
    core_nodes: list[str] = []
    zones: dict[str, str] = {}


class ToolBox:
    """Read-only view over one normalized bundle and (optionally) a topology."""

    def __init__(self, bundle: NormalizedBundle, topology: Topology | None, *, clock: Clock):
        self._bundle = bundle
        self._topology = topology
        self._clock = clock

    @property
    def bundle(self) -> NormalizedBundle:
        return self._bundle

    @property
    def topology(self) -> Topology | None:
        return self._topology

    @property
    def window(self) -> TimeWindow:
        """Time span of the whole bundle (used when a clarification widens the window)."""
        return self._bundle.window

    def session(self, agent: AgentId | str, budget: int) -> ToolSession:
        return ToolSession(self._bundle, self._topology, self._clock, agent=agent, budget=budget)


class ToolSession:
    """One agent's access for one task: permissions + budget + call records."""

    def __init__(
        self,
        bundle: NormalizedBundle,
        topology: Topology | None,
        clock: Clock,
        *,
        agent: AgentId | str,
        budget: int,
    ) -> None:
        self._bundle = bundle
        self._topology = topology
        self._clock = clock
        self.agent = agent
        self.budget = budget
        self.allowed = set(TOOL_PERMISSIONS.get(agent, ()))
        self.records: list[ToolCallRecord] = []

    @property
    def remaining(self) -> int:
        return self.budget - len(self.records)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def can_call(self, tool: str) -> bool:
        return tool in self.allowed and not self.exhausted

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
        result = fn()
        self.records.append(
            ToolCallRecord(
                tool=tool,
                arguments=arguments,
                result_summary=summarize(result),
                at=self._clock.now(),
            )
        )
        return result

    # ------------------------------------------------------------------ telemetry tools
    def list_entities(self) -> list[str]:
        return self._call(
            "list_entities", {}, lambda: list(self._bundle.entities), lambda r: f"{len(r)} entities"
        )

    def telemetry_query(
        self, entities: Iterable[str], metrics: Iterable[str] | None = None
    ) -> list[Sample]:
        ents, mets = sorted(set(entities)), None if metrics is None else list(metrics)

        def run() -> list[Sample]:
            wanted = set(mets) if mets is not None else None
            out: list[Sample] = []
            for r in sorted(self._bundle.records, key=lambda r: (r.timestamp, r.record_id)):
                if r.entity not in ents:
                    continue
                items: list[tuple[str, float | str]] = list(r.metrics.items())
                if r.status is not None:
                    items.append((STATUS_ITEM, r.status))
                for metric, value in items:
                    if wanted is None or metric in wanted:
                        out.append(
                            Sample(
                                record_id=r.record_id,
                                entity=r.entity,
                                timestamp=r.timestamp,
                                metric=metric,
                                value=value,
                                flags=tuple(r.flags),
                            )
                        )
            if mets is not None:
                order = {m: i for i, m in enumerate(mets)}
                out.sort(key=lambda s: (s.timestamp, s.record_id, order.get(s.metric, 99)))
            return out

        args: dict[str, Any] = {"entities": ents}
        if mets is not None:
            args["metrics"] = mets
        return self._call("telemetry_query", args, run, lambda r: f"{len(r)} samples")

    def coverage_query(
        self, entities: Iterable[str], items: Iterable[str] | None = None
    ) -> dict[tuple[str, str], MetricState]:
        ents = sorted(set(entities))
        its = list(items) if items is not None else list(self._bundle.assessable_items)

        def run() -> dict[tuple[str, str], MetricState]:
            out = {}
            for e in ents:
                for i in its:
                    out[(e, i)] = self._bundle.metric_states.get(
                        (e, i),
                        MetricState(
                            assessability="not_assessable",
                            reason="OUT_OF_SCOPE",
                            detail="entity or item not in this bundle",
                        ),
                    )
            return out

        def summary(r: dict[tuple[str, str], MetricState]) -> str:
            n = sum(1 for s in r.values() if s.assessability != "not_assessable")
            return f"{n}/{len(r)} pairs assessable"

        return self._call("coverage_query", {"entities": ents, "items": its}, run, summary)

    def data_quality(self) -> DataQualityNote:
        return self._call(
            "data_quality",
            {},
            lambda: self._bundle.data_quality,
            lambda q: f"Q={q.q:.2f} ({q.acceptance})",
        )

    # ------------------------------------------------------------------ topology tools
    def topology_info(self) -> TopologyInfo:
        def run() -> TopologyInfo:
            t = self._topology
            if t is None:
                return TopologyInfo(available=False)
            return TopologyInfo(
                available=True,
                topology_id=t.topology_id,
                provenance=t.provenance,
                entities_not_in_topology=[e for e in self._bundle.entities if not t.has(e)],
                core_nodes=list(t.core_nodes),
                zones={e: z for e in self._bundle.entities if (z := t.zone_of(e)) is not None},
            )

        return self._call(
            "topology_info",
            {},
            run,
            lambda i: f"{i.topology_id} ({i.provenance})" if i.available else "no topology",
        )

    def neighbors(self, entity: str) -> list[str] | None:
        return self._call(
            "neighbors",
            {"entity": entity},
            lambda: None if self._topology is None else self._topology.neighbors(entity),
            lambda r: "unknown" if r is None else f"{len(r)} neighbours",
        )

    def topology_path(self, entity: str) -> list[str] | None:
        return self._call(
            "topology_path",
            {"entity": entity},
            lambda: None if self._topology is None else self._topology.path_to_core(entity),
            lambda r: "unknown" if r is None else " > ".join(r) or "no path",
        )

    def what_if_failure(self, entity: str) -> WhatIfResult:
        def run() -> WhatIfResult:
            if self._topology is None:
                return WhatIfResult(failed=entity, unknown=[entity])
            return self._topology.what_if_failure(entity)

        return self._call(
            "what_if_failure",
            {"entity": entity},
            run,
            lambda r: (
                f"isolated={len(r.isolated)} degraded={len(r.degraded)} unknown={len(r.unknown)}"
            ),
        )

    def zone_entities(self, zone: str) -> list[str] | None:
        return self._call(
            "zone_entities",
            {"zone": zone},
            lambda: None if self._topology is None else self._topology.entities_in_zone(zone),
            lambda r: "unknown" if r is None else f"{len(r)} entities",
        )

    def probe_query(self, service: str | None = None) -> list[ProbeResult]:
        return self._call(
            "probe_query",
            {} if service is None else {"service": service},
            lambda: [p for p in self._bundle.probes if service is None or p.service == service],
            lambda r: f"{len(r)} team-authored probe results",
        )
