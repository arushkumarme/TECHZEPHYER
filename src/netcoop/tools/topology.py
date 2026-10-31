"""Simulated network topology and deterministic graph analysis (doc 02 C-TOOL, doc 11 §4).

Topology files live in ``sample_data/topology/`` and are TEAM-AUTHORED SYNTHETIC
(``provenance = "SIMULATED"``); the generator provides none (ID-04).

Blast-radius semantics (doc 11 §4) for a failed entity X:

* **isolated** — no remaining path to any core node once X is removed;
* **degraded** — still connected, but with fewer edge-disjoint paths to the core than
  before (redundancy lost); capacity impact is *not* claimed;
* **unaffected** — connectivity to the core unchanged;
* **unknown** — X itself is not in the topology.
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from netcoop.scenarios.generator import REPO_ROOT

TOPOLOGY_DIR = REPO_ROOT / "sample_data" / "topology"
_SINK = "__core__"


class TopologyError(ValueError):
    pass


class Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    role: Literal["core", "distribution", "access"]
    zone: str


class Link(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    a: str
    b: str


class WhatIfResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    failed: str
    isolated: list[str] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list)
    unaffected: list[str] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    basis: str = "structural reach in the SIMULATED topology, not measured impact"


class Topology(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    topology_id: str
    schema_version: str
    provenance: Literal["SIMULATED"]
    provenance_note: str
    core_nodes: list[str]
    nodes: list[Node]
    links: list[Link]

    @cached_property
    def graph(self) -> nx.Graph[str]:
        g: nx.Graph[str] = nx.Graph()
        g.add_nodes_from(n.id for n in self.nodes)
        g.add_edges_from((link.a, link.b, {"id": link.id}) for link in self.links)
        return g

    @cached_property
    def _by_id(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def has(self, entity: str) -> bool:
        return entity in self._by_id

    def node(self, entity: str) -> Node | None:
        return self._by_id.get(entity)

    def zone_of(self, entity: str) -> str | None:
        n = self._by_id.get(entity)
        return n.zone if n else None

    def entities_in_zone(self, zone: str) -> list[str]:
        return sorted(n.id for n in self.nodes if n.zone == zone)

    def zones(self) -> list[str]:
        return sorted({n.zone for n in self.nodes})

    def neighbors(self, entity: str) -> list[str] | None:
        if not self.has(entity):
            return None
        return sorted(self.graph.neighbors(entity))

    def _with_sink(self, graph: nx.Graph[str]) -> nx.Graph[str]:
        g = graph.copy()
        g.add_node(_SINK)
        g.add_edges_from((c, _SINK) for c in self.core_nodes if c in g)
        return g

    def path_to_core(self, entity: str) -> list[str] | None:
        """Shortest path entity → core (lexicographically smallest on ties). None if unknown."""
        if not self.has(entity):
            return None
        g = self._with_sink(self.graph)
        try:
            paths = list(nx.all_shortest_paths(g, entity, _SINK))
        except nx.NetworkXNoPath:
            return []
        best: list[str] = min(paths)
        return best[:-1]

    def upstream_of(self, entity: str) -> list[str] | None:
        path = self.path_to_core(entity)
        return None if path is None else path[1:]

    def _core_connectivity(self, graph: nx.Graph[str], entity: str) -> int:
        if entity in self.core_nodes:
            return 10**6
        # Number of edge-disjoint paths to the core, as a max-flow where every real link
        # has capacity 1 and the virtual core->sink edges are unlimited (otherwise the
        # single sink edge would cap every node at 1 and hide redundancy).
        flow: nx.DiGraph[str] = nx.DiGraph()
        for a, b in graph.edges():
            flow.add_edge(a, b, capacity=1)
            flow.add_edge(b, a, capacity=1)
        flow.add_node(entity)
        for c in self.core_nodes:
            if c in graph:
                flow.add_edge(c, _SINK)  # no capacity attribute = infinite
        if _SINK not in flow or not nx.has_path(flow, entity, _SINK):
            return 0
        return int(nx.maximum_flow_value(flow, entity, _SINK))

    def what_if_failure(self, failed: str) -> WhatIfResult:
        if not self.has(failed):
            return WhatIfResult(failed=failed, unknown=[failed])
        reduced = self.graph.copy()
        reduced.remove_node(failed)
        isolated, degraded, unaffected = [], [], []
        for n in sorted(self._by_id):
            if n == failed:
                continue
            before = self._core_connectivity(self.graph, n)
            after = self._core_connectivity(reduced, n)
            if after == 0:
                isolated.append(n)
            elif after < before:
                degraded.append(n)
            else:
                unaffected.append(n)
        return WhatIfResult(
            failed=failed, isolated=isolated, degraded=degraded, unaffected=unaffected
        )


def load_topology(ref: str | Path) -> Topology:
    """Load by id (``"campus_v1"`` → ``sample_data/topology/campus_v1.json``) or path."""
    path = ref if isinstance(ref, Path) else TOPOLOGY_DIR / f"{ref}.json"
    if not path.is_file():
        raise TopologyError(f"topology {ref!s} not found")
    topo = Topology.model_validate(json.loads(path.read_text(encoding="utf-8")))
    ids = {n.id for n in topo.nodes}
    for link in topo.links:
        for end in (link.a, link.b):
            if end not in ids:
                raise TopologyError(f"link {link.id} references unknown node {end}")
    for c in topo.core_nodes:
        if c not in ids:
            raise TopologyError(f"core node {c} is not a node")
    return topo
