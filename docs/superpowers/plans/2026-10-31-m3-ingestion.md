# M3 Ingestion Implementation Plan

> Executed natively. **Spec:** doc 05 §6–§7, doc 06, doc 09 §5 (E-01..E-12), ID-03, ID-06.

**Goal:** `ingest(raw) -> IngestResult` turns a telemetry bundle into a normalized bundle + data-quality note + per entity-metric assessability, or a rejection with a specific code. Missing is never healthy.

## Decisions
- **Bundle container (ID-03):** bare JSON array of generator records, or object `{"records": [...], "schema_version"?, "mode"?, "provenance"?, "reference_time"?, "topology_ref"?, "probes"?: [...]}`. Bundle `schema_version` major 1 native; major 0 = team-authored *flat* layout (metrics at record top level) handled by a registered adapter (`SCHEMA_ADAPTER_APPLIED` warning); other majors rejected.
- **Assessable items per entity:** the 7 canonical metrics of doc 06 + `status` (8). Completeness = assessed pairs / (entities × 8). A canonical metric absent from *every* record is `METRIC_NOT_PROVIDED` (info); absent for *some* entities while present for others is `METRIC_MISSING` (warning). Either way the pair is `not_assessable (MISSING)`.
- **Aliases & units:** `config/aliases.toml`, every entry provenance `team-authored incompatibility variant (doc 05 §6.4)`. Unit known from canonical name, alias, or record-level `units` map; contradiction or no unit → `UNIT_AMBIGUOUS`. Conversions: ms/s/us; percent/ratio.
- **Status values:** case-normalized to `Healthy|Warning|Critical` only; anything else → `MALFORMED`, observation later says "status unknown".
- **Freshness:** entity stale when its newest record is older than `reference_time` (bundle) or bundle max timestamp by > `stale_after_s` (config, 900 s) → `DATA_STALE`, pair `assessed_with_caveat`.
- **Duplicates:** identical records removed (`RECORD_DUPLICATE`); same entity+timestamp with different values kept, `RECORD_CONFLICT` warning (feeds conflict rules).
- **Plausibility:** outside doc-06 definitional bounds → `VALUE_IMPLAUSIBLE`, pair `not_assessable (IMPLAUSIBLE)` for that record's value; non-numeric/NaN/bool → `MALFORMED`.
- **Mode:** bundle `mode` other than `simulation` → `INPUT_MODE_UNSUPPORTED` (fatal). `config/netcoop.toml` mode must be `simulation`.
- **Probes (ID-06):** `{"probe_id","from_entity","service":"dns"|"dhcp","outcome":"success"|"failure"|"timeout","response_ms"?, "timestamp"}`; invalid probes dropped with `PROBE_INVALID`. Probe results always labelled `team-authored probe`.
- **Q** = min(completeness, freshness, consistency).

## Files
`src/netcoop/ingestion/{issues,models,aliases,normalize,sim_source}.py`, `src/netcoop/config/settings.py`, `config/{netcoop,aliases}.toml`, `tests/ingestion/test_*.py`.

## Tests
T-ERR-01..12 per doc 09 §5 E-01..E-12 (+ no entity, no usable metric, mode); T-ING-GEN-01 real generator bundle → READY; T-ERR-MISSING-01 property: no not-assessable pair is ever reported as assessed.
