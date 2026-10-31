"""Simulated remediation (component 12; doc 12 §3).

``SRC-1 p3 §4``: automated remediation "may simulate corrective actions. Do not modify
production campus infrastructure without explicit authorization." This module only
*describes* what an approved action would involve. It has no access to the tool layer,
no network and no process execution - there is no code path that can change a device.
Every outcome is labelled SIMULATED and states that nothing was changed or verified.
"""

from __future__ import annotations

_PLANS: dict[str, str] = {
    "link_congestion": "rebalance traffic or raise capacity on the congested egress link, "
    "then watch utilization and queue drops return below their thresholds",
    "upstream_congestion": "relieve the saturated upstream link on the path to core, then "
    "re-check latency on the downstream device",
    "interface_fault": "replace or re-seat the cable/transceiver on the faulty interface, "
    "then confirm interface error counters stop rising",
    "device_overload": "identify and rate-limit the load driving CPU, then confirm CPU "
    "utilization returns to its normal range",
    "device_failure": "fail over to redundant equipment or replace the failed device, then "
    "confirm the device and its dependants are reachable",
    "dns_dhcp_failure": "restart or fail over the DNS/DHCP service, then re-run the service "
    "probes from the affected segment",
    "normal_operation": "continue routine monitoring",
    "telemetry_unreliable": "correct the telemetry source and re-run the diagnosis",
}


def simulate_action(action: str, cause_type: str | None) -> str:
    """Describe the simulated execution of one approved recommendation."""
    plan = _PLANS.get(cause_type or "", "carry out the recommended step")
    return (
        "SIMULATED: no device was changed and nothing was sent to any network. "
        f"Approved action '{action}' would {plan}. In a real deployment this requires "
        "change control and explicit authorization from the network team; the outcome "
        "has not been verified."
    )
