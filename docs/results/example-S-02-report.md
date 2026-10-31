# NetCoop AI diagnostic report — INC-0014

> **Simulated data — scenario playback.** Mode: `simulation`; data provenance: `synthetic-generator`; topology: `SIMULATED`.

**Status:** `diagnosed`  
**Probable cause:** Likely link congestion causing egress queue drops on SW_CAMPUS_4  
**Confidence:** 0.66 (medium, heuristic score)  
**Affected devices:** SW_CAMPUS_4

## Supporting evidence

| Metric | Value | Interpretation |
|---|---|---|
| `link_utilization_pct` | 78.88 | Elevated link utilization on SW_CAMPUS_4 (sustained) |
| `queue_drops` | 35 | Elevated egress queue drops on SW_CAMPUS_4 (sustained) |
| `latency_ms` | 211.73 | Critical latency on SW_CAMPUS_4 (sustained) |
| `jitter_ms` | 66.76 | Critical jitter on SW_CAMPUS_4 (sustained) |
| `packet_loss_pct` | 1.5 | Elevated packet loss on SW_CAMPUS_4 (sustained) |
| `status` | Warning | Elevated device status on SW_CAMPUS_4 (sustained) |

Evidence sources: infrastructure_agent, performance_agent

## Alternative explanations

- Device or hardware failure on SW_CAMPUS_4 (heuristic score 0.48)
- Device CPU overload on SW_CAMPUS_4 (heuristic score 0.47)
- Ethernet or interface fault on SW_CAMPUS_4 (heuristic score 0.17)

## Not assessable

- `interface_errors (MISSING)`: SW_CAMPUS_1, SW_CAMPUS_10, SW_CAMPUS_2, SW_CAMPUS_3, SW_CAMPUS_4, SW_CAMPUS_5, SW_CAMPUS_6, SW_CAMPUS_7, SW_CAMPUS_8, SW_CAMPUS_9

## Recommended actions — simulated, require human approval

- [pending] Inspect egress link utilization and traffic distribution on the affected device (SW_CAMPUS_4)
- [pending] Review queue configuration and QoS policy on the congested interface (SW_CAMPUS_4)
- [pending] Consider load balancing or capacity increase on the saturated link (SW_CAMPUS_4)

## Agent contributions

| Agent | Status | Observations | Tool calls |
|---|---|---|---|
| connectivity_agent | ok | 0 | 14 |
| infrastructure_agent | ok | 30 | 3 |
| performance_agent | ok | 40 | 3 |

## Limitations

- DNS / DHCP service failure cannot be assessed with the supplied data (missing: DNS/DHCP service probe results).
- Weak Wi-Fi signal cannot be assessed with the supplied data (missing: wireless signal measurements).
- Root cause requires further verification by an operator.
- Whether queue_drops / interface_errors are per-sample or cumulative counters is unknown in the supplied generator; values are read as reported per sample.
- Confidence is a heuristic score from a documented method (doc 08), not a probability.
- Simulation mode: synthetic telemetry and a SIMULATED topology; NetCoop AI has no access to a real campus network.
