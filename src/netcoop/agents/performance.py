"""Telemetry & Performance Agent — ``performance_agent`` (A-PERF, doc 03 §2.1).

Examines latency, jitter, packet loss and link utilization (the generator provides no
throughput, bandwidth or wireless signal — those are reported as not provided).
"""

from __future__ import annotations

from netcoop.agents.base import Investigation, SpecialistAgent, is_abnormal, is_normal
from netcoop.core.blocks import Hypothesis, Observation


class PerformanceAgent(SpecialistAgent):
    agent_id = "performance_agent"
    short = "PERF"
    goal = "assess_performance"
    items = ("latency_ms", "jitter_ms", "packet_loss_pct", "link_utilization_pct")

    def local_hypotheses(
        self, observations: list[Observation], inv: Investigation
    ) -> list[Hypothesis]:
        hyps: list[Hypothesis] = []
        prefix = inv.id_prefix.removeprefix("OBS-")
        for entity, m in sorted(self.by_entity(observations).items()):
            util, lat = m.get("link_utilization_pct"), m.get("latency_ms")
            loss, jit = m.get("packet_loss_pct"), m.get("jitter_ms")
            delay = [o for o in (lat, jit) if o is not None and is_abnormal(o)]
            if is_abnormal(util) and delay:
                assert util is not None
                hyps.append(
                    self.hypothesis(
                        prefix,
                        len(hyps) + 1,
                        "link_congestion",
                        entity,
                        [util, *delay],
                        "HIGH_UTILIZATION_WITH_DELAY",
                    )
                )
            if delay and is_normal(util):
                hyps.append(
                    self.hypothesis(
                        prefix,
                        len(hyps) + 1,
                        "upstream_congestion",
                        entity,
                        delay,
                        "DELAY_WITH_NORMAL_LOCAL_UTILIZATION",
                        missing=["upstream device telemetry"],
                    )
                )
            if is_abnormal(loss) and not is_abnormal(util):
                assert loss is not None
                hyps.append(
                    self.hypothesis(
                        prefix,
                        len(hyps) + 1,
                        "interface_fault",
                        entity,
                        [loss],
                        "LOSS_WITHOUT_LOAD",
                        missing=["interface_errors"],
                    )
                )
        return hyps
