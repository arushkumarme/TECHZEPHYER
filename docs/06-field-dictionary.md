# 06 — Field Dictionary

> Version 0.1 · 2026-10-31 · **STATUS: PENDING — generator not inspected**
> The synthetic-data generator (`SRC-4`, Colab notebook linked at `SRC-1 p4 §5`) has not been provided and could not be opened (sign-in required). **No telemetry field name, unit, type, range, alias, topology field or ground-truth label is defined in this file.** Project rule P-06 ([doc 01 §8](01-requirements-traceability.md)): a field is not real because an example mentions it (`SRC-2 l.75`).

## 1. What is confirmed

`SRC-1 p4 §5` says the dataset "may include" the categories below. This is a list of *categories*, not field names, and "may" is not a guarantee.

| Category (wording from `SRC-1 p4 §5`) | Field name | Unit | Type | Valid range | Required? | Known variants | Source citation |
|---|---|---|---|---|---|---|---|
| Latency | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Jitter | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Packet loss | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Throughput | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Bandwidth | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Link utilization | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Device ID | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Device status | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| CPU utilization | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Memory utilization | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Egress queue drops | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Interface errors | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Wireless signal measurements ("where available") | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Timestamps | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Network topology information | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

## 2. Signals mentioned in scenarios but not in the category list

| Signal | Where mentioned | Status |
|---|---|---|
| Retransmissions | Weak Wi-Fi scenario, `SRC-1 p4 §5` | `UNKNOWN` whether the data has it |
| Link instability | Interface fault scenario, `SRC-1 p4 §5` | `UNKNOWN` whether the data has it |
| Service-specific signals for DNS/DHCP | DNS/DHCP scenario, `SRC-1 p4 §5` | `UNKNOWN`; see [doc 08 §3.3](08-diagnosis-and-confidence.md) |
| Schema version, "missing message information" | Interoperability scenario, `SRC-1 p4 §5` | `UNKNOWN` whether the data carries a version |
| Ground-truth cause labels | — | `UNKNOWN` |
| Generator seed / parameters | — | `UNKNOWN` |

## 3. Generator inspection worksheet

To be filled from `SRC-4` only. Each row needs a citation (notebook cell, line, or output file); rows without one are not allowed (`T-DOC-01`).

1. Output files and container format(s); one file or several; example record layout.
2. For each category in §1: exact field name, unit, type, observed value range, whether always present, whether nullable.
3. Device and link identifier format; how devices and links relate.
4. Timestamp format, timezone, sampling interval, total duration.
5. Topology: is it generated? Fields, hierarchy, redundancy, any location or building/zone attribute.
6. Scenario parameters: which scenarios the generator can produce, and how fault intensity is set.
7. Randomness: seed support (needed for reproducible runs).
8. Noise, missing values, malformed values — does the generator inject any?
9. Ground truth: is the true cause recorded?
10. Anything unusual: units that differ by device type, sentinel values, duplicates.

## 4. Rules for filling this file

- Names are copied exactly from the generator; nothing is renamed here. Canonical internal names (if different) are listed in an extra column, with the mapping in `config/`.
- A unit is recorded only if the generator states or demonstrably uses it; otherwise `UNKNOWN`.
- Aliases are added only with a cited source (generator variant, or a team-authored incompatibility variant labelled as such — doc 05 §6.4).
- Protocol fields (envelope, observations, hypotheses) are **not** telemetry fields; they live in doc 05 and doc 07.

## 5. Consequences of the gap

| Dependent item | What is blocked |
|---|---|
| Alias map, unit rules, plausibility ranges | Ingestion and normalization implementation |
| Evidence availability matrix | Which hypotheses can be diagnosed (doc 08 §3.2) |
| Scenario packages | Which suggested scenarios can be produced from real generator output vs team-authored variants |
| Topology and zone mapping | Connectivity analysis, blast radius, community-to-device mapping |
| Seed support | Reproducibility guarantees (`R-14`, `M-06`) |
