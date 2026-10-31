# 06 — Field Dictionary

> Version 0.2 · 2026-10-31 · **STATUS: OBSERVED** — filled from the organizer generator (`SRC-4`), vendored verbatim at [`sample_data/generator/`](../sample_data/generator/PROVENANCE.md).
> Machine-readable twin: [`config/telemetry_fields.toml`](../config/telemetry_fields.toml). Test `T-DOC-01` (`tests/config/test_fields.py`) checks that every entry cites a generator line containing the field verbatim, and that the dictionary and the generator's actual output contain exactly the same fields.
> Citations `gen:L<n>` = line *n* of the notebook's single code cell.

## 1. Record layout (`OBSERVED`)

The generator returns **one JSON object per call**:

```json
{
  "timestamp": "2026-10-14T07:05:49.619791Z",
  "device_id": "SW_CAMPUS_4",
  "metrics": { "cpu_utilization_pct": 99.9, "...": "..." },
  "status": "Critical"
}
```

(Example copied from the notebook's saved output.) There is no wrapper, no schema version and no topology. How NetCoop groups several records into a *bundle* is a team decision (ID-03, doc 05 §6).

## 2. Fields

| Category (`SRC-1 p4 §5`) | Field name | Location | Unit | Type | Observed range: normal / latency_spike / hardware_failure | Source |
|---|---|---|---|---|---|---|
| Timestamps | `timestamp` | record | ISO 8601, UTC, `Z` suffix | string | — | gen:L7 |
| Device ID | `device_id` | record | — | string `SW_CAMPUS_<1..10>` | — | gen:L8 |
| Device status | `status` | record | — | enum `Healthy` / `Warning` / `Critical` | Healthy / Warning / Critical | gen:L21,31,41 |
| CPU utilization | `cpu_utilization_pct` | metrics | percent | number | 10–35 / 40–70 / 99.9 | gen:L14,24,34 |
| Link utilization | `link_utilization_pct` | metrics | percent | number | 20–50 / 60–85 / 100.0 | gen:L15,25,35 |
| Packet loss | `packet_loss_pct` | metrics | percent | number | 0.0 / 0.1–1.5 / 15–30 | gen:L16,26,36 |
| Latency | `latency_ms` | metrics | millisecond | number | 5–20 / 150–400 / 500–1000 | gen:L17,27,37 |
| Jitter | `jitter_ms` | metrics | millisecond | number | 1–5 / 30–80 / **absent** | gen:L18,38 |
| Egress queue drops | `queue_drops` | metrics | count | integer | 0 / 0–50 / 5000–15000 | gen:L19,28,39 |
| Interface errors | `interface_errors` | metrics | count | integer | **absent** / **absent** / 100–500 | gen:L29 |

Units are taken from the field-name suffixes (`_pct`, `_ms`), which the values are consistent with. Whether `queue_drops` and `interface_errors` are per-sample or cumulative counters is `UNKNOWN`; NetCoop treats each value as the count reported in that sample and states this in the limitations.

## 3. Categories from `SRC-1 p4 §5` that the generator does not provide

| Category / signal | Status | Consequence |
|---|---|---|
| Throughput, bandwidth | Not emitted | Not assessable; never treated as normal |
| Memory utilization | Not emitted | Not assessable |
| Wireless signal, retransmissions | Not emitted | Weak Wi-Fi is **not diagnosable** from generator data (ID-06) |
| Network topology | Not emitted | Team-authored simulated topology, labelled `SIMULATED` (ID-04) |
| DNS / DHCP service signals | Not emitted | Diagnosed only from the separately labelled, team-authored probe input (doc 08 §3.3, ID-06) |
| Link instability / link state | Not emitted | Interface-fault diagnosis relies on `interface_errors` and loss only |
| Schema version | Not emitted | Version checks apply only to NetCoop's bundle wrapper |
| Ground-truth labels | Only the `fault_type` argument | Scenario ground truth is "by construction" (doc 09 §3) |
| Seed | Not supported by the original code | NetCoop's runner injects a seeded RNG; frozen inputs are committed anyway |

## 4. Generator worksheet answers (from doc 06 v0.1 §3)

1. Output: one Python dict printed as JSON; single record per call.
2. Fields: §2.
3. Device IDs: `SW_CAMPUS_1`–`SW_CAMPUS_10`, chosen uniformly at random; no links.
4. Timestamp: `datetime.utcnow().isoformat() + "Z"`; no sampling interval or duration concept.
5. Topology: none.
6. Scenarios: `normal` (default and fallback for any unknown value), `latency_spike`, `hardware_failure`. Intensity is fixed by the hard-coded ranges.
7. Randomness: module-level `random`, no seed parameter.
8. Noise / missing / malformed values: none injected. Field presence differs by profile (§2).
9. Ground truth: the `fault_type` argument only; `status` is a fixed function of it.
10. Unusual: `hardware_failure` uses constants for CPU (99.9) and link utilization (100.0); `jitter_ms` disappears in that profile.

## 5. Rules for this file

- Names are copied exactly from the generator; nothing is renamed. Aliases for incompatible variants live in `config/` with their own provenance (team-authored, doc 05 §6.4).
- Protocol fields (envelope, observations, hypotheses) are not telemetry fields; they live in docs 05 and 07.
- Any change to the vendored generator changes its hash and fails the test suite; this file must then be re-verified.
