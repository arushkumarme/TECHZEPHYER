"""Hypothesis catalog (doc 08 §3.1) and evidence availability matrix (doc 08 §3.2).

Signature items name *evidence items*: a doc-06 metric, ``status``, or a derived item
prefixed ``@`` that the scorer computes (topology or probe based). Each item has an
importance class (key / supporting / weak → weights in ``config/diagnosis.toml``) and a
mode: ``abnormal`` (elevated/critical supports) or ``normal`` (assessed-normal supports).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from netcoop.config.fields import FieldDictionary

ItemClass = Literal["key", "supporting", "weak"]
ContraClass = Literal["strong", "moderate"]
Mode = Literal["abnormal", "normal"]
When = Literal["normal", "abnormal", "critical"]

#: Derived items computed by the scorer, with the agent whose finding provides them.
DERIVED_ITEMS: dict[str, str] = {
    "@upstream_congestion": "connectivity_agent",
    "@downstream_affected": "connectivity_agent",
    "@probe_failures": "connectivity_agent",
    "@probe_success": "connectivity_agent",
    "@network_normal": "performance_agent",
}


@dataclass(frozen=True)
class SignatureItem:
    item: str
    cls: ItemClass
    mode: Mode = "abnormal"


@dataclass(frozen=True)
class ContraItem:
    item: str
    cls: ContraClass
    when: When


@dataclass(frozen=True)
class CauseSpec:
    cause_type: str
    label: str
    origin: str
    signature: tuple[SignatureItem, ...] = ()
    contradicting: tuple[ContraItem, ...] = ()
    needs_topology: bool = False
    #: Items that must exist in the data for the cause to be diagnosable at all.
    requires: tuple[str, ...] = ()
    alternative_wording: str = ""
    actions: tuple[str, ...] = field(default_factory=tuple)
    next_steps: tuple[str, ...] = field(default_factory=tuple)


_STATUS_WEAK = SignatureItem("status", "weak")

CATALOG: dict[str, CauseSpec] = {
    "normal_operation": CauseSpec(
        "normal_operation",
        "Normal operation",
        'PDF p4: "Measurements remain within expected ranges"',
        actions=("No corrective action indicated; continue routine monitoring",),
        next_steps=("Collect the metrics listed as not assessable before concluding health",),
    ),
    "link_congestion": CauseSpec(
        "link_congestion",
        "Link congestion causing egress queue drops",
        'PDF p4: "High utilization, elevated queue drops, and increased latency"',
        signature=(
            SignatureItem("link_utilization_pct", "key"),
            SignatureItem("queue_drops", "key"),
            SignatureItem("latency_ms", "supporting"),
            SignatureItem("packet_loss_pct", "weak"),
            SignatureItem("jitter_ms", "weak"),
            _STATUS_WEAK,
        ),
        contradicting=(
            ContraItem("link_utilization_pct", "strong", "normal"),
            ContraItem("queue_drops", "moderate", "normal"),
            ContraItem("interface_errors", "moderate", "critical"),
        ),
        alternative_wording="Link congestion",
        actions=(
            "Inspect egress link utilization and traffic distribution on the affected device",
            "Review queue configuration and QoS policy on the congested interface",
            "Consider load balancing or capacity increase on the saturated link",
        ),
        next_steps=("Re-check link utilization and queue drops over a longer window",),
    ),
    "upstream_congestion": CauseSpec(
        "upstream_congestion",
        "Upstream link congestion",
        'PDF p5 example alternative "Upstream link congestion"; generalized (ours)',
        signature=(
            SignatureItem("@upstream_congestion", "key"),
            SignatureItem("latency_ms", "supporting"),
            SignatureItem("link_utilization_pct", "supporting", "normal"),
            SignatureItem("queue_drops", "weak", "normal"),
            SignatureItem("packet_loss_pct", "weak"),
            SignatureItem("jitter_ms", "weak"),
        ),
        contradicting=(ContraItem("link_utilization_pct", "strong", "critical"),),
        needs_topology=True,
        alternative_wording="Upstream link congestion",
        actions=(
            "Inspect utilization and queue drops on the upstream device(s) on the path to core",
            "Review traffic distribution across upstream links",
        ),
        next_steps=("Collect upstream device telemetry for the same time window",),
    ),
    "weak_wifi": CauseSpec(
        "weak_wifi",
        "Weak Wi-Fi signal",
        'PDF p4: "Poor signal quality and increased retransmissions"',
        signature=(
            SignatureItem("wireless_signal", "key"),
            SignatureItem("retransmissions", "supporting"),
            SignatureItem("packet_loss_pct", "weak"),
            SignatureItem("latency_ms", "weak"),
        ),
        requires=("wireless_signal",),
        alternative_wording="Weak Wi-Fi signal",
        actions=("Survey access-point signal strength and channel utilization",),
        next_steps=("Collect wireless signal and retransmission measurements",),
    ),
    "interface_fault": CauseSpec(
        "interface_fault",
        "Ethernet / interface fault",
        'PDF p4: "Rising interface errors, link instability, or packet loss"',
        signature=(
            SignatureItem("interface_errors", "key"),
            SignatureItem("packet_loss_pct", "supporting"),
            SignatureItem("latency_ms", "weak"),
            _STATUS_WEAK,
        ),
        contradicting=(ContraItem("interface_errors", "strong", "normal"),),
        alternative_wording="Ethernet or interface fault",
        actions=(
            "Inspect interface error counters, cabling and transceivers on the affected device",
            "Check duplex/speed negotiation on the affected interface",
        ),
        next_steps=("Monitor interface error counters for a rising trend",),
    ),
    "device_overload": CauseSpec(
        "device_overload",
        "Device CPU overload",
        'PDF p1 lists "device CPU overload"; signature ours',
        signature=(
            SignatureItem("cpu_utilization_pct", "key"),
            SignatureItem("latency_ms", "weak"),
            SignatureItem("queue_drops", "weak"),
            _STATUS_WEAK,
        ),
        contradicting=(ContraItem("cpu_utilization_pct", "strong", "normal"),),
        alternative_wording="Device CPU overload",
        actions=(
            "Identify processes or control-plane traffic driving CPU load on the device",
            "Review recent configuration changes and rate-limit control-plane traffic",
        ),
        next_steps=("Collect CPU and memory utilization over a longer window",),
    ),
    "device_failure": CauseSpec(
        "device_failure",
        "Device / hardware failure",
        'PDF p1 lists "hardware failures"; signature ours',
        signature=(
            SignatureItem("status", "key"),
            SignatureItem("interface_errors", "supporting"),
            SignatureItem("packet_loss_pct", "supporting"),
            SignatureItem("cpu_utilization_pct", "weak"),
            SignatureItem("latency_ms", "weak"),
            SignatureItem("queue_drops", "weak"),
            SignatureItem("link_utilization_pct", "weak"),
            SignatureItem("@downstream_affected", "weak"),
        ),
        contradicting=(ContraItem("status", "strong", "normal"),),
        alternative_wording="Device or hardware failure",
        actions=(
            "Inspect the affected device's hardware health (power, fans, line cards, logs)",
            "Prepare failover or replacement for the affected device",
            "Notify users of downstream segments that depend on the device",
        ),
        next_steps=("Verify device reachability and hardware logs",),
    ),
    "dns_dhcp_failure": CauseSpec(
        "dns_dhcp_failure",
        "DNS / DHCP service failure",
        'PDF p4: "Service-specific connectivity problems"; probe-based (doc 08 §3.3)',
        signature=(
            SignatureItem("@probe_failures", "key"),
            SignatureItem("@network_normal", "supporting"),
        ),
        contradicting=(ContraItem("@probe_success", "strong", "abnormal"),),
        requires=("@probe_failures",),
        alternative_wording="DNS or DHCP service failure",
        actions=(
            "Check the DNS/DHCP service health and logs on the serving hosts",
            "Verify reachability from the affected segment to the DNS/DHCP servers",
        ),
        next_steps=("Run DNS and DHCP service checks from the affected segment",),
    ),
    "telemetry_unreliable": CauseSpec(
        "telemetry_unreliable",
        "Telemetry unreliable or incompatible",
        "PDF p4 interoperability-failure scenario",
        actions=(),
        next_steps=(
            "Fix the telemetry source: field names, units and schema version",
            "Re-run the diagnosis after the data is corrected",
        ),
    ),
}


def availability(fields: FieldDictionary, *, probes_present: bool) -> dict[str, bool]:
    """Evidence availability matrix (doc 08 §3.2): is each cause diagnosable at all?"""
    known = set(fields.fields) | {"status"}
    out: dict[str, bool] = {}
    for cause, spec in CATALOG.items():
        out[cause] = all(
            probes_present if req.startswith("@probe") else req in known for req in spec.requires
        )
    return out
