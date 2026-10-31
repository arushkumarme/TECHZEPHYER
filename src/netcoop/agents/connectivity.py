"""Connectivity Analysis Agent — ``connectivity_agent`` (A-CONN, doc 03 §2.3).

Establishes *where* a problem can reach: upstream paths, zones, blast radius (what-if)
for devices that look unhealthy in its own telemetry screen, and team-authored service
probe results (DNS/DHCP, doc 08 §3.3). It does not wait for other agents and never asserts
an entity is faulty from structure alone. Status/latency it reads for prioritising are
kept in ``facts`` (not re-emitted as observations, so one raw metric never counts twice).
"""

from __future__ import annotations

from functools import partial
from typing import Any

from netcoop.agents.base import Investigation, SpecialistAgent
from netcoop.core.blocks import (
    Hypothesis,
    Limitation,
    NotAssessableItem,
    Observation,
    TimeWindow,
)
from netcoop.core.messages import ClarificationRequest, ClarificationResponse, ParsedMessage
from netcoop.diagnosis.severity import grade, rank, worst
from netcoop.tools.toolbox import TopologyInfo

_SCREEN = ("status", "latency_ms", "packet_loss_pct")


class ConnectivityAgent(SpecialistAgent):
    agent_id = "connectivity_agent"
    short = "CONN"
    goal = "assess_connectivity_scope"
    items = ()  # produces facts and probe observations, not metric observations

    def investigate_topology(self, inv: Investigation) -> dict[str, Any]:
        facts: dict[str, Any] = {
            "topology_available": False,
            "topology_id": None,
            "topology_provenance": None,
            "paths": {},
            "what_if": {},
            "zones": {},
            "entities_not_in_topology": [],
            "suspicious": [],
        }
        info: TopologyInfo | None = self._try(inv, inv.session.topology_info)
        screen = self._try(inv, lambda: inv.session.telemetry_query(inv.scope, list(_SCREEN)))
        sev: dict[str, int] = {}
        for s in screen or []:
            if inv.window.start <= s.timestamp <= inv.window.end:
                g = rank(worst([grade(s.metric, s.value, self.params)]))
                if s.metric == "status" or g >= rank("critical"):
                    sev[s.entity] = max(sev.get(s.entity, -1), g)
        suspicious = sorted(
            (e for e, r in sev.items() if r >= rank("elevated")), key=lambda e: (-sev[e], e)
        )
        facts["suspicious"] = suspicious
        if info is None or not info.available:
            inv.limitations.append(
                Limitation(
                    code="TOPOLOGY_MISSING",
                    text="No topology available: affected scope and blast radius are unknown.",
                )
            )
            return facts
        facts.update(
            topology_available=True,
            topology_id=info.topology_id,
            topology_provenance=info.provenance,
            zones={e: z for e, z in info.zones.items() if e in inv.scope},
            entities_not_in_topology=[e for e in info.entities_not_in_topology if e in inv.scope],
        )
        for e in facts["entities_not_in_topology"]:
            inv.limitations.append(
                Limitation(
                    code="ENTITY_NOT_IN_TOPOLOGY",
                    text=f"{e} is not in the topology; its scope is unknown.",
                )
            )
        # What-if first for suspicious devices (most informative), then paths for all.
        for e in suspicious:
            if e in facts["entities_not_in_topology"] or not inv.session.can_call(
                "what_if_failure"
            ):
                continue
            r = self._try(inv, partial(inv.session.what_if_failure, e))
            if r is not None:
                facts["what_if"][e] = {"isolated": r.isolated, "degraded": r.degraded}
        for e in [x for x in inv.scope if x not in facts["entities_not_in_topology"]]:
            if not inv.session.can_call("topology_path"):
                inv.limitations.append(
                    Limitation(
                        code="TOOL_BUDGET_EXHAUSTED",
                        text="Budget exhausted before all upstream paths were traced.",
                    )
                )
                break
            path = self._try(inv, partial(inv.session.topology_path, e))
            if path:
                facts["paths"][e] = path
        return facts

    def assessed_fraction(
        self, inv: Investigation, observations: list[Observation], facts: dict[str, Any]
    ) -> float:
        """Share of the scope whose upstream path could be traced."""
        return len(facts.get("paths", {})) / max(1, len(inv.scope))

    def screen(self, inv: Investigation) -> None:  # no metric screen of its own
        inv.samples = {}

    def check_coverage(self, inv: Investigation) -> None:
        return None

    def deep_dive(self, inv: Investigation) -> None:
        return None

    def build_observations(
        self, inv: Investigation
    ) -> tuple[list[Observation], list[NotAssessableItem]]:
        return [], []

    def extra_facts(
        self,
        inv: Investigation,
        observations: list[Observation],
        not_assessable: list[NotAssessableItem],
    ) -> dict[str, Any]:
        facts = self.investigate_topology(inv)
        if not facts["topology_available"]:
            not_assessable.extend(
                NotAssessableItem(
                    entity=e, metric="topology", reason="NO_TOPOLOGY", detail="no topology"
                )
                for e in inv.scope
            )
        else:
            not_assessable.extend(
                NotAssessableItem(
                    entity=e, metric="topology", reason="NO_TOPOLOGY", detail="not in topology"
                )
                for e in facts["entities_not_in_topology"]
            )
        probes = (
            self._try(inv, inv.session.probe_query) if inv.session.can_call("probe_query") else None
        )
        for p in probes or []:
            if p.from_entity not in inv.scope:
                continue
            observations.append(
                Observation(
                    observation_id=inv.next_id(),
                    entity=p.from_entity,
                    metric=f"probe_{p.service}",
                    metric_category=f"{p.service.upper()} service check (team-authored probe)",
                    value=p.outcome,
                    unit="outcome",
                    window=TimeWindow(start=p.timestamp, end=p.timestamp),
                    severity="normal" if p.outcome == "success" else "critical",
                    assessability="assessed",
                    quality_flags=["team-authored probe", f"probe_id:{p.probe_id}"],
                    source_ref=[p.probe_id],
                    agent=self.agent_id,
                )
            )
        facts["probes_present"] = bool(probes)
        if not probes:
            inv.limitations.append(
                Limitation(
                    code="NO_SERVICE_PROBES",
                    text="No DNS/DHCP service probe data was supplied; "
                    "service failures cannot be assessed.",
                )
            )
        return facts

    def local_hypotheses(
        self, observations: list[Observation], inv: Investigation
    ) -> list[Hypothesis]:
        hyps: list[Hypothesis] = []
        prefix = inv.id_prefix.removeprefix("OBS-")
        failing: dict[str, list[Observation]] = {}
        for o in observations:
            if o.metric.startswith("probe_") and o.severity == "critical":
                failing.setdefault(o.entity, []).append(o)
        for entity, obs in sorted(failing.items()):
            hyps.append(
                self.hypothesis(
                    prefix, len(hyps) + 1, "dns_dhcp_failure", entity, obs, "SERVICE_PROBES_FAIL"
                )
            )
        return hyps

    def clarify(self, req: ClarificationRequest, msg: ParsedMessage) -> ClarificationResponse:
        if req.question_type != "what_if_cause" or "entity" not in req.parameters:
            return ClarificationResponse(
                answered=False,
                reason=f"connectivity_agent answers what_if_cause(entity); got {req.question_type}",
            )
        entity = str(req.parameters["entity"])
        session = self._toolbox(msg).session(self.agent_id, 2)
        r = session.what_if_failure(entity)
        if r.unknown:
            return ClarificationResponse(
                answered=False, reason=f"{entity} unknown: topology missing or entity absent"
            )
        return ClarificationResponse(
            answered=True,
            result={
                "entity": entity,
                "isolated": r.isolated,
                "degraded": r.degraded,
                "basis": r.basis,
            },
        )
