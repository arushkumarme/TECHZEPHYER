"""Infrastructure Health Agent — ``infrastructure_agent`` (A-INFRA, doc 03 §2.2).

Examines device status, CPU, egress queue drops and interface errors (memory is not
provided by the generator). A device without status data is observed as "status unknown",
never as healthy. Does not infer topology effects (that is the connectivity agent's job).
"""

from __future__ import annotations

from netcoop.agents.base import Investigation, SpecialistAgent, is_abnormal
from netcoop.core.blocks import Hypothesis, Observation
from netcoop.core.vocab import CauseType


class InfrastructureAgent(SpecialistAgent):
    agent_id = "infrastructure_agent"
    short = "INFRA"
    goal = "assess_device_health"
    items = ("status", "cpu_utilization_pct", "queue_drops", "interface_errors")

    def local_hypotheses(
        self, observations: list[Observation], inv: Investigation
    ) -> list[Hypothesis]:
        hyps: list[Hypothesis] = []
        prefix = inv.id_prefix.removeprefix("OBS-")
        for entity, m in sorted(self.by_entity(observations).items()):
            status, cpu = m.get("status"), m.get("cpu_utilization_pct")
            drops, errs = m.get("queue_drops"), m.get("interface_errors")

            def add(
                cause: CauseType,
                support: list[Observation | None],
                code: str,
                entity: str = entity,
            ) -> None:
                obs = [o for o in support if o is not None and is_abnormal(o)]
                hyps.append(self.hypothesis(prefix, len(hyps) + 1, cause, entity, obs, code))

            if status is not None and status.severity == "critical":
                add("device_failure", [status, errs, cpu], "DEVICE_REPORTS_CRITICAL")
            if is_abnormal(cpu):
                add("device_overload", [cpu, drops], "HIGH_CPU")
            if is_abnormal(errs):
                add("interface_fault", [errs], "INTERFACE_ERRORS")
            if is_abnormal(drops):
                add("link_congestion", [drops], "QUEUE_DROPS")
        return hyps
