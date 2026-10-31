# 05 — Interoperability Protocol Specification

> Version 0.1 · 2026-10-31 · Draft for review
> Everything here is `PROPOSAL` unless tagged. Covers the **agent message protocol** and the **input-handling policy**. Telemetry field names, units and aliases are *not* defined here — they wait for the generator ([doc 06](06-field-dictionary.md)). Formal JSON Schemas will be exported from the implementation models later; this document is the human-readable contract.

`SRC-1 p3 §4` (interoperability, mandatory): "Document message formats, field meanings and units; provide a way to exchange and interpret findings." Evaluation weight 30% (`SRC-1 p6 §8`). `CONFIRMED`

## 1. Principles

1. One envelope for every message; every message validated on every hop, even in-process.
2. Facts, interpretations and unknowns are kept apart: *observations* are measured, *hypotheses* are interpretations, *not assessable* items are unknowns.
3. Every conclusion cites observation IDs, so any report claim can be traced to a raw record.
4. Unknown extra fields are ignored and logged; missing required fields make a message invalid.
5. Nothing is silently guessed: conversions, aliases and gaps are recorded.
6. **Agents exchange references, not data.** Telemetry and topology never travel inside messages. Every message of an incident carries the same `snapshot_id`, a fingerprint of the exact data all agents analyse (§13). Telemetry-like extra fields in a message are ignored and reported (`FIELD_IGNORED`), never accepted.

## 2. Message envelope

| Field | Meaning | Required |
|---|---|---|
| `protocol_version` | Version of this envelope specification | yes |
| `message_id` | Unique ID of this message | yes |
| `incident_id` | Incident the message belongs to | yes (after `RECEIVED`) |
| `in_reply_to` | `message_id` of the request being answered | for responses |
| `sender`, `recipient` | `orchestrator`, an agent identifier (`performance_agent`, `infrastructure_agent`, `connectivity_agent`, `correlation_agent`, `reporting_agent`), or `community_module` | yes |
| `message_type` | One of §3 | yes |
| `sent_at` | UTC timestamp | yes |
| `payload_schema_version` | Version of the payload layout for this type | yes |
| `status` | `ok`, `partial`, or `error` | yes |
| `payload` | Type-specific content | yes |
| `snapshot_id` | `SNAP-` + 12 hex: the data snapshot the message refers to (§13) | no (1.1; stamped by the bus) |
| `mode` | Always `simulation`; any other value is rejected with `MODE_NOT_ALLOWED`, never defaulted to live | no (1.1; stamped by the bus) |
| `data_provenance` | A registered `data_provenance` term (Appendix A), e.g. `synthetic-generator` | no (1.1; stamped by the bus) |
| `seq` | Per-incident sequence number (1, 2, 3 ...) in log order, deterministic | no (1.1; assigned by the bus) |

The four 1.1 fields are optional so 1.0 messages still parse (compatibility tests in `tests/core/test_envelope_v11.py`).

## 3. Message types

| Type | Direction | Payload summary |
|---|---|---|
| `task_request` | Orchestrator → agent | Goal; scope (entities); time window; tool-call budget; deadline. 1.1: `task_id` (`TASK-0001`, per incident), `task_kind` (`investigate` / `correlate` / `report`), `input_message_ids` (the findings/decision a correlate or report task works from: references, not copies), `incident_context` (description, zone, trigger `telemetry_bundle` / `community_candidate`, incident time) |
| `finding` | Agent → Orchestrator | Observations; hypotheses; not-assessable items; limitations; tool-call records; self-assessment (completeness). 1.1: `task_id` echoed from the task |
| `clarification_request` | Agent → Orchestrator → target | Question type (closed list, doc 03 §3); parameters, checked per question type (`recheck_metric`: entity + metric; `what_if_cause`: entity; the others: entities); reason; round number. 1.1: `clarification_id` (`CLR-0001` = round 1) |
| `clarification_response` | Target → Orchestrator → requester | Answer (observations or what-if result) or "cannot answer" with reason. 1.1: `clarification_id`, `answerable` (`yes` / `no` / `partial`, consistent with `answered`), `source` |
| `decision` | A-CORR → Orchestrator | Ranked hypotheses with scores; decision (`diagnosed` / `insufficient_evidence` / `no_fault_detected`); conflict trail. 1.1: `decision_id` (`DEC-0001`, one per incident), `score_method` (`heuristic`), `abstention` {`reasons` (abstention_reason terms), `evidence_that_would_change_decision`}: **required** for `insufficient_evidence`, **forbidden** for `diagnosed` |
| `report_ready` | A-REPT → Orchestrator | The report (doc 07). 1.1: `recommendations` (structured `Recommendation`s, §4) |
| `agent_error` | Any | Error code (§7), message, recoverable? 1.1: `related_message_id`, `details` |
| `community_candidate` | Community module → Orchestrator | Candidate incident (extension, doc 10). 1.1: `complaint_ids` |

All 1.1 payload fields are optional or derived, so 1.0 payloads still parse. Where a 1.0 sender omits them, the parser derives the new form from the old one: hypothesis evidence refs from the observation-id lists, `answerable` from `answered`, and the abstention block from the failed gate checks. A validator checks that old and new forms agree. Each message type maps to one payload model (`PAYLOAD_TYPES` in `core/messages.py`).

## 4. Payload building blocks

Names are protocol design choices. Models live in `core/blocks.py`.

**Observation** — a measured or derived fact.
`observation_id` · `entity` (device, link, or zone as identified in the normalized data) · `metric` (a doc 06 field name, e.g. `latency_ms`; its problem-statement category, unit and dimension come from the `metric` vocabulary) · `metric_category` (display label) · `value` · `unit` · `window` (start, end) · `severity` (`normal`, `elevated`, `critical`, `unknown`) · `assessability` (`assessed`, `assessed_with_caveat`, `not_assessable`) · `quality_flags` · `source_ref` (pointer to normalized record(s), and through them the raw record). 1.1 (optional): `aggregation` · `sample_count` · `baseline_ref` (threshold id in config) · `not_assessable_reason`

**Hypothesis** — an interpretation, never a fact.
`hypothesis_id` · `cause_type` (from the catalog, doc 08 §3) · `entities` · `supporting_observation_ids` · `contradicting_observation_ids` · `missing_expected_evidence` · `local_score` (agent-local heuristic, not the final confidence) · `rationale_code`. 1.1: `supporting` / `contradicting` (lists of **EvidenceRef**) · `score_method` (`agent_local_heuristic`)

**EvidenceRef** — a typed pointer to evidence: `evidence_type` (`observation`, `hypothesis`, `normalized_record`, `community_report`, `tool_result`, `topology_element`) · `evidence_id` (its prefix must match the type: `OBS-`, `HYP-`, `REC-`, `CAND-`) · `stance` (`supports`, `contradicts`, `neutral`) · `strength` (0..1, optional) · `note`.

**EntityRef** — `entity_type` (`device`, `link`, `zone`) · `entity_id` (non-empty).

**Recommendation** — `recommendation_id` (`RCM-0001`; `REC-` is taken by records) · `action_text` · `kind` (recommendation_mode) · `target_entities` · `reason` · `priority` (`high` / `medium` / `low`; by order, PROVISIONAL D-24) · `precautions` · `requires_human_approval` and `simulated` (always `true`; `false` is rejected) · `verification_step` · `linked_hypothesis_id`.

**Official report** — `report/official.py` `OfficialReport`: exactly the ten keys of doc 07 §1 in the PDF's order and types, strict (an eleventh key or a boolean confidence is rejected). The PDF example validates against it.

**Semantic rules** (each a registered error code, reported by `try_parse` with the field path):
1. A `not_assessable` observation has no value, severity `unknown` and a `not_assessable_reason`; an assessed one has a value (`ASSESSABILITY_VALUE_MISMATCH`).
2. A declared unit must exist and fit the dimension of the observation's metric (`UNIT_INCOMPATIBLE`).
3. A hypothesis cites a supporting EvidenceRef or names missing expected evidence (`HYPOTHESIS_WITHOUT_EVIDENCE`); refs in the supporting list have stance `supports`, in the contradicting list `contradicts` (`EVIDENCE_STANCE_MISMATCH`).
4. Every score carries its `score_method`; `calibrated` is a blocked term (`UNKNOWN_TERM`).
5. Evidence ids carry the prefix of their type (`EVIDENCE_PREFIX_MISMATCH`).
6. Recommendations cannot set `requires_human_approval` or `simulated` to false (`RECOMMENDATION_SAFETY_VIOLATION`).
7. The official report has exactly ten keys (strict `OfficialReport`).
Also: `ABSTENTION_MISMATCH`, `CLARIFICATION_PARAMETERS_INVALID`, `CLARIFICATION_ANSWER_MISMATCH`, `EVIDENCE_REFS_DISAGREE`.

**Not-assessable item** — an unknown, stated explicitly.
`entity` · `metric_category` · `reason` (`MISSING`, `MALFORMED`, `UNMAPPED_FIELD`, `UNIT_AMBIGUOUS`, `STALE`, `INSUFFICIENT_SAMPLES`, `NO_TOPOLOGY`, `OUT_OF_SCOPE`) · `detail`

**Limitation** — free-text statement of what the agent could not conclude, with a code.

**Tool-call record** — `tool` · `arguments` summary · `result` summary · `timestamp`. Makes the agent's investigation visible.

**Self-assessment** — fraction of the assigned scope the agent could actually assess, and whether it hit its tool budget.

## 5. Identifiers, time, versions

- **Agent identifiers** are fixed strings (doc 02 §2). `performance_agent` and `infrastructure_agent` match the official example (`SRC-1 p5 §6`).
- **Incident ID** format is not mandated by the PDF (the example is `INC-8832`). Implemented: `<prefix>-NNNN`, prefix `INC` configurable (`[protocol] incident_prefix`). **PROVISIONAL** (D-22).
- **Other identifiers** keep their existing formats; `validate_id(kind, value)` in `core/ids.py` checks every kind: messages `INC-0001-MSG-000001` (replies add `.R`), observations `OBS-PERF-000003-001`, hypotheses `HYP-…`, records `REC-0001`, snapshots `SNAP-<12 hex>`, candidates `CAND-`, complaints `CMP-`, conflicts `CONF-`, and the prefixes reserved for later prompts `TASK-`, `CLR-`, `DEC-`, `RCM-` (recommendations; `REC-` is taken by records).
- **Time:** internal timestamps are UTC. Input timestamp format, timezone and sampling interval are `PENDING` (generator).
- **Versioning (semantic):**
  - *Minor* change = additive (new optional field, new enum value readers can ignore) → accepted by older readers.
  - *Major* change = breaking → rejected with `INPUT_SCHEMA_VERSION_UNSUPPORTED` unless a registered adapter exists.
  - Current `protocol_version` is **1.1**. A message with the same major and an older or equal minor is accepted. A **newer minor** (e.g. 1.9) is accepted with the warning `PROTOCOL_MINOR_NEWER`, and its unknown fields are ignored and reported. A different major is rejected with `PROTOCOL_VERSION_UNSUPPORTED` (`core/versioning.py`).
  - Three version numbers are kept distinct: `protocol_version` (envelope), `payload_schema_version` (per message type), and the **input data schema version** (from the telemetry itself, *if* the data carries one — `UNKNOWN`).

## 6. Ingestion, normalization and bundle acceptance

This stage is deterministic code (C-ING), not an agent. It implements `CD-10`: a partly missing metric never invalidates a bundle, and missing is never healthy.

### 6.1 Steps

1. **Parse.** Supported container formats: `PENDING` (generator output format unknown).
2. **Structure check** against the expected layout.
3. **Schema-version check** (only if the data declares a version).
4. **Field mapping** through the alias map in `config/`. An alias applies only if it is listed with a cited source; otherwise the field is `UNMAPPED_FIELD`.
5. **Unit normalization.** Convert when the unit is declared or the field dictionary defines exactly one unit; otherwise mark `UNIT_AMBIGUOUS` and the metric is not assessable.
6. **Timestamp normalization** to UTC; records without usable timestamps are flagged.
7. **Plausibility checks** (ranges from the field dictionary; `PENDING`). Implausible values are flagged, not silently corrected.
8. **De-duplication** of repeated records (flagged).
9. **Data-quality note**: completeness (share of expected entity-metric pairs assessable), freshness (age against a configured limit), consistency (share passing plausibility/duplicate checks). Thresholds are configuration; values `PENDING`.

### 6.2 Bundle acceptance

| Outcome | Condition |
|---|---|
| `REJECTED` | Cannot be parsed; unsupported major schema version without adapter; **no** entity can be identified in any record; **no** timestamp can be established in any record; or **no** usable metric exists at all |
| `READY_WITH_WARNINGS` | Anything else with problems: missing metrics or entities, unmapped fields, ambiguous units, stale or implausible values, duplicates, missing topology |
| `READY` | No warnings |

A rejection produces a specific error report (doc 07 §6), not a diagnosis.

### 6.3 Metric-level assessability

Every entity-metric pair ends in exactly one state: `assessed`, `assessed_with_caveat`, or `not_assessable` (with a reason). Rules:

- `not_assessable` is never converted to `normal`.
- A hypothesis that needs a `not_assessable` item lists it under `missing_expected_evidence`; it lowers support but is not contradicting evidence (doc 08 §7).
- "Normal operation" itself needs *assessed* evidence of normality for enough of the scope.

### 6.4 Team-authored incompatibility variants

The interoperability scenario requires data with incompatible field names, units, schema versions or missing message information (`SRC-1 p4 §5`). Unless the generator already offers such variants, the team creates them by *mutating* valid generator output (rename, rescale, drop, retag). These variants are labelled **team-authored incompatibility**; any alias needed to map them back is listed in `config/` with that provenance. It is never presented as a real-world campus alias.

## 7. Error taxonomy

Severity: **fatal** stops the incident; **error** degrades it; **warning** is recorded and surfaced; **info** is logged.

| Code | Severity | Meaning | Handling |
|---|---|---|---|
| `INPUT_UNPARSEABLE` | fatal | Input cannot be parsed | Reject |
| `INPUT_SCHEMA_VERSION_UNSUPPORTED` | fatal | Major version with no adapter | Reject |
| `INPUT_NO_ENTITY` / `INPUT_NO_TIMESTAMP` / `INPUT_NO_USABLE_METRIC` | fatal | Nothing identifiable / datable / usable | Reject |
| `FIELD_ALIAS_APPLIED` | warning | Known alternate name mapped | Continue, note |
| `FIELD_UNMAPPED` | warning | Unrecognized field for a needed metric | Metric `not_assessable` |
| `UNIT_CONVERTED` | info | Unit converted | Record conversion |
| `UNIT_AMBIGUOUS` | warning | Unit unknown or unclear | Metric `not_assessable` |
| `METRIC_MISSING` | warning | Expected metric absent | `not_assessable (MISSING)` |
| `VALUE_IMPLAUSIBLE` | warning | Outside plausible range | Flag; caveat or not assessable |
| `RECORD_DUPLICATE` | info | Duplicate removed | Record |
| `DATA_STALE` | warning | Older than freshness limit | Caveat or not assessable |
| `TOPOLOGY_MISSING` | warning | No topology | Scope `unknown`; confidence ceiling lowered |
| `ENTITY_NOT_IN_TOPOLOGY` | warning | Entity absent from topology | Entity scope `unknown` |
| `AGENT_TIMEOUT` / `AGENT_FAILED` | error | Agent late or failed | Degraded run |
| `MESSAGE_INVALID` | error | Message fails validation | Reject message; treat as missing |
| `CLARIFICATION_LIMIT_REACHED` | info | Round cap hit | A-CORR decides; recorded |
| `LLM_UNAVAILABLE` / `LLM_OUTPUT_REJECTED` | info | LLM absent or grounding check failed | Template fallback |

## 8. Transport

- In-process message bus; each message is serialized to JSON, validated (envelope, payload rules, conversation guard), appended to the log, then delivered synchronously to the recipient registered for it. `IMPLEMENTED` (§16)
- No broker and no external agent framework (`CD-2`). MCP exists only as the read-only tool/resource interface (doc 16); agent-to-agent messages never use it.
- Agent-to-agent REST is not planned. The envelope is transport-neutral, so it could be added later. `FUTURE`
- The backend API (doc 02) is for dashboard and complaint submission only, not for agent communication.

## 9. Pending until the generator is inspected

- Canonical metric names and units (doc 06).
- Alias map contents, container format, timestamp format and timezone.
- Whether the data carries a schema version.
- Plausibility ranges and freshness limit.
- Whether any wireless, service-level (DNS/DHCP) or link-state signals exist.

## 10. Implementation status (M1, 2026-10-31) — `IMPLEMENTED`, `TESTED`

| Item | Where |
|---|---|
| Closed vocabularies (agents, message types, cause types, severities, reasons…) | `src/netcoop/core/vocab.py` |
| Building blocks (§4) | `src/netcoop/core/blocks.py` |
| Envelope, eight payload types, `make_message`, `parse_message` | `src/netcoop/core/messages.py` |
| Formal JSON Schemas (generated; a test fails if stale) | `schemas/protocol/*.schema.json` |
| Deterministic ids and injectable clock | `src/netcoop/core/ids.py` |
| Contract tests `T-PROTO-01..10`, `T-PROTO-SCHEMA-01` | `tests/core/` |

Decisions made while implementing (additive to §2–§7):

- `protocol_version` and `payload_schema_version` are both `"1.0"`; format `MAJOR.MINOR`. A different major is rejected with **`PROTOCOL_VERSION_UNSUPPORTED`** or **`PAYLOAD_SCHEMA_VERSION_UNSUPPORTED`** (new codes, severity *error*, handled like `MESSAGE_INVALID`).
- `finding`, `clarification_response`, `decision` and `report_ready` must carry `in_reply_to`.
- `sent_at` and all window timestamps must be timezone-aware.
- Ignored unknown fields are reported with their path (e.g. `payload.observations[0].x_note`) so they can be logged.
- Observation gains `metric` (canonical name from doc 06) next to `metric_category`, an `agent` field and an `evidence_class` (`direct_measurement` / `derived` / `user_report`) used by conflict rule 1 (doc 08 §5).
- Not-assessable reasons gain `IMPLAUSIBLE` (doc 05 §7 `VALUE_IMPLAUSIBLE`).
- `finding` carries an optional `facts` object for structured non-metric facts (e.g. dependency scope from `connectivity_agent`).

## 11. Ingestion implementation (M3, 2026-10-31) — `IMPLEMENTED`, `TESTED`

Code: `src/netcoop/ingestion/` (`normalize.ingest`), configuration `config/netcoop.toml` and `config/aliases.toml`, tests `tests/ingestion/`.

- **Bundle container** (`PROPOSAL`, ID-03): a JSON array of generator records, or an object `{"records": [...], "schema_version"?, "mode"?, "provenance"?, "reference_time"?, "topology_ref"?, "probes"?, "description"?}`. Record fields are the generator's (doc 06). An optional record-level `units` object declares units for aliased fields.
- **Schema versions:** bundle major `1` native; major `0` = team-authored *flat* layout (metrics at record top level), handled by a registered adapter (`SCHEMA_ADAPTER_APPLIED`); any other major is rejected.
- **Assessable items** per device: the seven doc-06 metrics plus `status`. A metric absent from every record → `METRIC_NOT_PROVIDED` (info); absent for some devices but present for others → `METRIC_MISSING` (warning). Either way the pair is `not_assessable (MISSING)` — e.g. `interface_errors` in generator `normal` data.
- **Units:** taken from the canonical name, the alias, or the record's `units` declaration. A contradiction between name and declaration, an unknown spelling, or no unit at all → `UNIT_AMBIGUOUS`; nothing is guessed. Conversions: s/us → ms, ratio/fraction → percent.
- **Status values** are case-normalized to `Healthy`/`Warning`/`Critical`; anything else → `STATUS_UNRECOGNIZED`, status not assessable (never "healthy").
- **Freshness:** a device is stale when its newest record is older than `reference_time` (or the newest record in the bundle) by more than `stale_after_s` (900 s, `PROPOSAL`). Stale pairs are `assessed_with_caveat (STALE)`.
- **Duplicates:** identical records removed (`RECORD_DUPLICATE`); different records for the same device and timestamp are all kept (`RECORD_CONFLICT`) for the conflict rules.
- **Data quality:** completeness = assessed pairs ÷ (devices × 8); freshness = share of non-stale devices; consistency = share of kept records without implausible/malformed/ambiguous/conflicting values; `Q` = min of the three.
- **Probes** (ID-06): validated `{probe_id, from_entity, service: dns|dhcp, outcome: success|failure|timeout, response_ms?, timestamp}`; always labelled `team-authored probe`; invalid ones dropped with `PROBE_INVALID`.
- **New codes** beyond §7: `INPUT_MODE_UNSUPPORTED` (fatal), `SCHEMA_ADAPTER_APPLIED`, `VALUE_MALFORMED`, `STATUS_UNRECOGNIZED`, `TIMESTAMP_UNUSABLE`, `ENTITY_UNUSABLE`, `RECORD_CONFLICT`, `PROBE_INVALID` (warnings), `FIELD_IGNORED`, `METRIC_NOT_PROVIDED` (info). Full list with severities: `src/netcoop/ingestion/issues.py`.

## 12. Controlled vocabularies (protocol upgrade, Prompt 1) — `IMPLEMENTED`, `TESTED`

The "interpret" half of `R-09`: every agent uses the same defined terms. Each vocabulary is one file in `config/vocabulary/` (35 files) giving every term a definition, a status (`active` / `deprecated` / `blocked`), a source and attributes. The registry (`src/netcoop/core/vocabulary/`) is **metadata layered over the term sets the code already enforces**: where a `Literal` or constant exists, the file names it in `code_literal`, and a test fails if the two drift apart. The app's own term names are kept (e.g. `upstream_congestion`, `weak_wifi`, metric names such as `latency_ms`); each metric term carries its problem-statement category, unit and dimension from doc 06.

- **API:** `get_vocabulary`, `is_valid`, `require` (raises `UnknownTermError` with closest-match suggestions, or `BlockedTermError`), and the pydantic marker `Annotated[str, VocabTerm("cause_type")]`.
- **Closed vs extensible:** closed vocabularies reject unknown ids; an extensible one (`rationale_code`) also accepts `x-` ids, flagged as unrecognised. `blocked` terms - `calibrated` (until doc 08 §9), `deployment`, the verified provenances - are always rejected.
- **Units:** `core/vocabulary/units.py` converts only inside one dimension and never guesses a missing unit (0.94 is not read as 94 %). `unit_fits_metric` checks a declared unit against the metric's dimension.
- **Error codes:** one `error_code` vocabulary holds every code the system emits, with severity and kind; a test scans the source and fails on an unregistered or unused code.
- **Generated outputs:** `scripts/generate_docs.py` writes Appendix A below and `conformance/vocabularies.json` (for the conformance kit); idempotent, and a test fails if either is stale.
- **Evidence:** `tests/core/test_vocabulary.py` (22) and `tests/e2e/test_vocabulary_in_runs.py`, which checks every vocabulary-controlled value in real S-05, S-09 and S-12 runs.

## 13. Envelope 1.1, data snapshot and safe parsing (protocol upgrade, Prompt 2) — `IMPLEMENTED`, `TESTED`

- **Data snapshot** (`core/snapshot.py`). After ingestion the orchestrator fingerprints the normalized bundle: canonical JSON (sorted keys, `,`/`:` separators, UTF-8, NaN/Infinity rejected), then SHA-256. `snapshot_id` = `SNAP-` + the first 12 hex. The descriptor also records the full hash, `topology_version` (hash of the topology, or `none`), `config_hash` (settings + diagnosis parameters that can change the analysis; execution mechanics proven result-neutral, parallel/sequential and direct/MCP, are excluded), `mode`, `data_provenance` (the registered term; an unregistered declared provenance is kept in `declared_provenance` and stamped as `unspecified`), `bundle_acceptance`, `source_label`, `created_at`. It is checkpointed, so a resumed run reuses the identical snapshot, and it appears in the report under `netcoop_extensions.data_snapshot`. Same data in any key order gives the same id; changing one value changes it.
- **Stamping** (`core/bus.py`). The bus stamps `snapshot_id`, `mode` and `data_provenance` on every message it builds and assigns `seq` to every accepted message, under a lock, continuing from the log after a restart. Specialist handlers still run in parallel, but their replies are validated, logged and numbered by the orchestrator in fixed agent order, so `seq` is identical in parallel and sequential runs. A reply that arrives after its deadline is no longer logged; the timeout itself is recorded as an `agent_error`.
- **Safe parsing** (`core/parse.py`). `try_parse(raw)` never raises: it returns a `ParseResult` with the message or `None`, plus `errors` and `warnings`, each with a registered code, a plain reason and the field path (e.g. `payload.tool_budget`). Codes: `MESSAGE_INVALID`, `UNKNOWN_TERM` (unregistered or blocked vocabulary value), `MODE_NOT_ALLOWED`, `MESSAGE_TOO_LARGE` (limit `[protocol] max_message_bytes`, default 1 MiB, about 20x the largest scenario message, **PROVISIONAL** D-23), `PROTOCOL_VERSION_UNSUPPORTED`, `PAYLOAD_SCHEMA_VERSION_UNSUPPORTED`; warnings `PROTOCOL_MINOR_NEWER`, `FIELD_IGNORED`. `parse_message` keeps its raising behaviour and is now a thin wrapper.
- **Trace.** Every message line shows `seq=N` and `[SNAP-… provenance]`.
- **Evidence:** `tests/core/test_envelope_v11.py`, `tests/core/test_snapshot.py`, `tests/orchestrator/test_stamping.py` (real S-09 run: every message carries the snapshot, mode and provenance, `seq` is 1..N without gaps, also after pause/resume, and parallel = sequential).

## 14. Payload models and semantic rules (protocol upgrade, Prompt 3) — `IMPLEMENTED`, `TESTED`

§3 and §4 describe the 1.1 payloads. The real agents fill the new fields. The orchestrator stamps task ids and kinds and points correlate/report tasks at earlier messages by id. Specialists echo the task id and give the reason for every not-assessable observation. The correlation agent numbers clarifications (`CLR-<round>`) and decisions (`DEC-0001`) and writes a real abstention block: failed gate checks mapped to abstention reasons, plus the evidence that would change the decision. The reporting agent sends one `Recommendation` per official recommended action. Telemetry is never placed in a payload. Evidence: `tests/core/test_payload_rules.py` (the 7 rules, every model, round trips, the PDF example), `tests/e2e/test_payloads_in_runs.py` (real S-02, S-07, S-08, S-09, S-12 runs; every logged message re-validates).

## 15. Authority matrix and conversation rules (protocol upgrade, Prompt 4) — `IMPLEMENTED`, `TESTED`

A rulebook enforced by code: **who** may send **which** message, **to whom**, and **when**. The rules are data (`config/protocol/authority.toml`). `ConversationGuard.check(message, state)` in `core/guard/` is pure: it never changes the message or the state and returns the violations, each with a code and a plain-English reason, e.g. *"Rejected: only correlation_agent may send a decision; performance_agent tried."* `ConversationState` tracks, per incident, the open tasks, questions waiting for relay, relayed questions, rounds used, whether a decision and a report were accepted, the seen message ids and the current incident state. `state.apply(message)` returns a new state and is called only for accepted messages. Replaying the same messages always gives the identical, JSON-serializable state (`rebuild_state`).

- **In the bus.** The orchestrator's bus checks every message after parsing. The check, the state update, the `seq` assignment and the log append happen under one lock, so the state follows the log exactly. A rejected message is logged (invalid, with the first violation's code and all reasons) and raises `GuardViolationError`. The incident state comes from the orchestrator's state machine and is not duplicated. After a restart the state is rebuilt from the log.
- **The rows describe the app's real flow** (measured on every scenario run). Investigate tasks go out before the `DISPATCHED` transition. The correlation agent answers its correlate task with a `clarification_request` or a `decision`. The orchestrator relays the question to the named target with `in_reply_to` = the original question, and sends `agent_error` against a timed-out or failed request. Only the correlation agent asks questions.
- **Community input** is admitted only with the `community_signals` extension on. Otherwise the guard rejects it (`EXTENSION_DISABLED`), it is logged, and the report states it in `limitations`. The core result is unchanged.
- **Codes.** `MESSAGE_ROUTING_INVALID` is deprecated, replaced by `DIRECT_AGENT_MESSAGE_FORBIDDEN` and `RECIPIENT_NOT_ALLOWED`. `BusRoutingError` is still raised for routing faults.
- **Evidence:** `tests/core/test_guard.py`. It has an accepted case for every row, a rejected case per rule, the demo sentence, no mutation, deterministic replay, every real scenario passing the guard, a forged decision injected into a real incident and logged with its reason, and a community message rejected when the flag is off.

<!-- BEGIN GENERATED: authority -->

### Authority matrix

Specialists = `performance_agent`, `infrastructure_agent`, `connectivity_agent`. Source: `config/protocol/authority.toml` (version 1.1).

| Message type | Sender | Recipient | Incident states | Reply rule | Other |
|---|---|---|---|---|---|
| `task_request` | `orchestrator` | specialists | `READY`, `READY_WITH_WARNINGS`, `DISPATCHED`, `COLLECTING` | starts a conversation (no `in_reply_to`) | task kind `investigate` |
| `task_request` | `orchestrator` | `correlation_agent` | `CORRELATING` | starts a conversation (no `in_reply_to`) | task kind `correlate` |
| `task_request` | `orchestrator` | `reporting_agent` | `REPORTING` | starts a conversation (no `in_reply_to`) | task kind `report` |
| `finding` | specialists | `orchestrator` | `DISPATCHED`, `COLLECTING` | answers an open `task_request` addressed to the sender | task kind `investigate` |
| `clarification_request` | `correlation_agent` | `orchestrator` | `CORRELATING` | answers an open `task_request` addressed to the sender | task kind `correlate`; counts toward the round limit |
| `clarification_request` | `orchestrator` | specialists | `CLARIFYING` | relays the correlation agent's open question to the target it names | - |
| `clarification_response` | specialists | `orchestrator` | `CLARIFYING` | answers the question relayed to the sender | - |
| `decision` | `correlation_agent` | `orchestrator` | `CORRELATING` | answers an open `task_request` addressed to the sender | task kind `correlate`; once per incident |
| `report_ready` | `reporting_agent` | `orchestrator` | `REPORTING` | answers an open `task_request` addressed to the sender | task kind `report`; once per incident; after a decision |
| `agent_error` | `performance_agent`, `infrastructure_agent`, `connectivity_agent`, `correlation_agent`, `reporting_agent` | `orchestrator` | any open state | may reply to any earlier message of the incident | - |
| `agent_error` | `orchestrator` | `performance_agent`, `infrastructure_agent`, `connectivity_agent`, `correlation_agent`, `reporting_agent` | any open state | may reply to any earlier message of the incident | - |
| `community_candidate` | `community_module` | `orchestrator` | any open state | starts a conversation (no `in_reply_to`) | extension `community_signals` must be on |

### Conversation rules

Checked in this order; every rejection is logged with its code and a plain-English reason.

1. **Closed incident** — nothing is accepted once the incident is `REJECTED`, `COMPLETE`, `FAILED` (`INCIDENT_CLOSED`).
2. **No duplicates** — a message id is accepted once per incident (`DUPLICATE_MESSAGE`).
3. **Hub and spoke** — every message is to or from the `orchestrator`; agents never message each other (`DIRECT_AGENT_MESSAGE_FORBIDDEN`), and nobody messages itself (`RECIPIENT_NOT_ALLOWED`).
4. **Authority** — only the senders in the matrix may send a type (`SENDER_NOT_AUTHORIZED`), and only to its recipients (`RECIPIENT_NOT_ALLOWED`).
5. **Extensions** — extension messages need their feature flag (`EXTENSION_DISABLED`).
6. **Sequence** — a type is legal only in its incident states, `decision` and `report_ready` at most once, `report_ready` only after a decision (`MESSAGE_OUT_OF_SEQUENCE`).
7. **Replies** — a reply must answer an open request addressed to its sender; a relayed question must name the target of the correlation agent's question (`REPLY_MISMATCH`).
8. **Round limit** — the correlation agent's questions count toward `max_clarification_rounds` (default 2) per incident (`CLARIFICATION_LIMIT_EXCEEDED`).

<!-- END GENERATED: authority -->

## 16. Message bus and append-only log (protocol upgrade, Prompt 5) — `IMPLEMENTED`, `TESTED`

- **Order of work in `MessageBus.transmit`:** serialize to JSON, then `try_parse` (envelope, version, size, payload and semantic rules), then the hub-and-spoke route check, then the reply check, then the conversation guard. On success it applies the new state, stamps `seq` and appends to the log, all under one lock, and then delivers. **Every attempt is logged**, accepted or rejected. Specialist handlers still run in worker threads (deadlines need them), but every reply is validated and logged by the orchestrator's thread in fixed order.
- **Log row:** `attempt_seq` (1, 2, 3 … per incident, every attempt), `protocol_seq` (the envelope `seq` of an accepted message), `received_at` (injected clock), sender, recipient, type, `in_reply_to`, `snapshot_id`, `mode`, `data_provenance`, `status`, `payload_json`, `verdict` (`accepted` / `rejected`), `violations_json` (code, plain-English reason, field path), `warnings_json`, plus the raw message.
- **Store API:** `append`, `get_incident_messages`, `get_message`, `iter_trace`, `export_jsonl`. There is **no update or delete method**. SQLite triggers abort any `UPDATE` or `DELETE`, and the only raw-SQL hook is the private `_execute_raw_for_tests`.
- **Migration:** opening a database written by an earlier version adds the new columns automatically (`ALTER TABLE … ADD COLUMN` never rewrites rows) and records `messages_v2_protocol_1_1` in `schema_migrations`. Old rows read the new columns as derived values: attempt order, verdict from `valid`, violations from the old error code.
- **Read API for agents and tools:** `bus.get_message(id)` and `bus.messages_for(incident, types=...)`, so a correlate task can read the findings it references. Reading never changes anything. `bus.rebuild_state(incident)` replays the conversation state from the log alone.
- **Evidence:** `tests/core/test_bus_v11.py`. It checks delivery once and in order; rejected messages logged with reasons and not delivered; warnings logged; monotonic sequence and duplicate rejection; identical log on replay; rebuilt state equal to live; references resolved by id; no update/delete; subscribers only receive their own messages; and an old-format database migrated.

## Appendix A: Controlled vocabularies

<!-- BEGIN GENERATED: vocabulary -->

_Generated by `scripts/generate_docs.py` from `config/vocabulary/*.toml`; do not edit by hand. A term marked **blocked** is defined but always rejected._

| Vocabulary | Terms | Closed? | Enforced in code by |
|---|---|---|---|
| [`abstention_reason`](#vocabulary-abstention-reason) | 9 | closed | registry only |
| [`agent`](#vocabulary-agent) | 7 | closed | `netcoop.core.vocab:AgentId` |
| [`aggregation`](#vocabulary-aggregation) | 4 | closed | registry only |
| [`assessability`](#vocabulary-assessability) | 3 | closed | `netcoop.core.vocab:Assessability` |
| [`bundle_acceptance`](#vocabulary-bundle-acceptance) | 3 | closed | `netcoop.ingestion.models:Acceptance` |
| [`cause_type`](#vocabulary-cause-type) | 9 | closed | `netcoop.core.vocab:CauseType` |
| [`clarification_reason`](#vocabulary-clarification-reason) | 3 | closed | `netcoop.core.vocab:ClarificationReason` |
| [`confidence_category`](#vocabulary-confidence-category) | 4 | closed | `netcoop.core.vocab:ConfidenceCategory` |
| [`conflict_rule`](#vocabulary-conflict-rule) | 4 | closed | `netcoop.core.vocab:ConflictRule` |
| [`data_provenance`](#vocabulary-data-provenance) | 6 | closed | registry only |
| [`decision_kind`](#vocabulary-decision-kind) | 3 | closed | `netcoop.core.vocab:DecisionKind` |
| [`dimension`](#vocabulary-dimension) | 6 | closed | registry only |
| [`entity_type`](#vocabulary-entity-type) | 3 | closed | registry only |
| [`error_code`](#vocabulary-error-code) | 63 | closed | registry only |
| [`evidence_class`](#vocabulary-evidence-class) | 3 | closed | `netcoop.core.vocab:EvidenceClass` |
| [`evidence_stance`](#vocabulary-evidence-stance) | 3 | closed | registry only |
| [`evidence_type`](#vocabulary-evidence-type) | 6 | closed | registry only |
| [`incident_state`](#vocabulary-incident-state) | 14 | closed | `netcoop.orchestrator.states:State` |
| [`message_status`](#vocabulary-message-status) | 3 | closed | `netcoop.core.vocab:MessageStatus` |
| [`message_type`](#vocabulary-message-type) | 8 | closed | `netcoop.core.vocab:MessageType` |
| [`metric`](#vocabulary-metric) | 11 | closed | registry only |
| [`metric_category`](#vocabulary-metric-category) | 12 | closed | registry only |
| [`mode`](#vocabulary-mode) | 2 | closed | `netcoop.config.settings:Settings.mode` |
| [`not_assessable_reason`](#vocabulary-not-assessable-reason) | 9 | closed | `netcoop.core.vocab:NotAssessableReason` |
| [`question_type`](#vocabulary-question-type) | 4 | closed | `netcoop.core.vocab:QuestionType` |
| [`rationale_code`](#vocabulary-rationale-code) | 8 | extensible (`x-` ids) | registry only |
| [`recommendation_mode`](#vocabulary-recommendation-mode) | 4 | closed | registry only |
| [`recommendation_priority`](#vocabulary-recommendation-priority) | 3 | closed | registry only |
| [`report_status`](#vocabulary-report-status) | 4 | closed | `netcoop.report.validate:STATUSES` |
| [`score_method`](#vocabulary-score-method) | 3 | closed | registry only |
| [`severity`](#vocabulary-severity) | 4 | closed | `netcoop.core.vocab:Severity` |
| [`task_kind`](#vocabulary-task-kind) | 3 | closed | registry only |
| [`topology_provenance`](#vocabulary-topology-provenance) | 3 | closed | `netcoop.tools.topology:Topology.provenance` |
| [`trust_label`](#vocabulary-trust-label) | 3 | closed | `netcoop.core.vocab:TrustLabel` |
| [`unit`](#vocabulary-unit) | 8 | closed | registry only |

### Vocabulary: abstention_reason

Why a decision abstains; one per failed gate check (PROVISIONAL naming, D-18).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `below_score_threshold` | Below score threshold | The top score is below tau_diag. | active | doc 08 §4.5 | gate_check=score_at_least_tau |
| `missing_key_evidence` | Missing key evidence | None of the cause's key signature items has supporting evidence. | active | doc 08 §11 ID-13 | gate_check=key_evidence_present |
| `too_few_signature_items` | Too few signature items | Fewer than n_min signature items support the cause. | active | doc 08 §4.5 | gate_check=min_signature_items |
| `too_few_independent_sources` | Too few independent sources | Fewer than s_min agents support the cause. | active | doc 08 §4.5 | gate_check=min_independent_sources |
| `ambiguous_margin` | Ambiguous margin | The top two explanations are closer than delta. | active | doc 08 §4.4 | gate_check=margin_at_least_delta |
| `telemetry_unreliable` | Telemetry unreliable | The best explanation is that the data itself is broken. | active | doc 08 §4.5 | gate_check=not_telemetry_unreliable |
| `not_diagnosable` | Not diagnosable | The leading cause's required evidence does not exist in the data. | active | doc 08 §3.2 | gate_check=diagnosable |
| `coverage_too_low` | Coverage too low | Too little of the scope was assessed to call it healthy. | active | doc 08 §4.5 | gate_check=coverage_at_least_min |
| `abnormal_measurements_present` | Abnormal measurements present | Something is out of range, so 'no fault' cannot be claimed. | active | doc 08 §11 ID-14 | gate_check=no_abnormal_measurements |

### Vocabulary: agent

Participants that may send or receive protocol messages.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `orchestrator` | Orchestrator | Deterministic coordinator that assigns tasks, enforces limits and records every transition; not an AI. | active | doc 02 C-ORC | kind=orchestrator |
| `performance_agent` | Performance agent | Specialist that grades latency, jitter, packet loss and link utilization. | active | SRC-1 p2 §3; doc 03 §2.1 | kind=agent |
| `infrastructure_agent` | Infrastructure agent | Specialist that grades device status, CPU, egress queue drops and interface errors. | active | SRC-1 p2 §3; doc 03 §2.2 | kind=agent |
| `connectivity_agent` | Connectivity agent | Specialist that establishes topology scope, upstream paths, blast radius and service-probe results. | active | SRC-1 p2 §3; doc 03 §2.3 | kind=agent |
| `correlation_agent` | Correlation agent | Agent that scores competing explanations from all findings and decides diagnosed or insufficient evidence. | active | SRC-1 p2 §3; doc 03 §2.4 | kind=agent |
| `reporting_agent` | Reporting agent | Agent that builds, validates and renders the final report and its recommendations. | active | SRC-1 p2 §3; doc 03 §2.5 | kind=agent |
| `community_module` | Community module | Extension A pipeline that turns user complaints into unverified candidate incidents; not an agent. | active | doc 10 | kind=module |

### Vocabulary: aggregation

How one observation value summarizes several samples (PROVISIONAL, D-19).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `worst_by_severity` | Worst by severity | The sample with the highest severity, ties broken by magnitude; what the specialists report today. | active | agents/base.py |  |
| `last_value` | Last value | The most recent sample. | active | PROPOSAL |  |
| `mean` | Mean | Arithmetic mean of the samples. | active | PROPOSAL |  |
| `max` | Maximum | Largest sample. | active | PROPOSAL |  |

### Vocabulary: assessability

Whether an entity-metric pair could be judged.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `assessed` | Assessed | Usable data was present and graded. | active | doc 05 §6.3 |  |
| `assessed_with_caveat` | Assessed with caveat | Graded, but the data carries a caveat such as being stale. | active | doc 05 §6.3 |  |
| `not_assessable` | Not assessable | No usable data; the pair is unknown, never healthy. | active | doc 05 §6.3; CD-10 |  |

### Vocabulary: bundle_acceptance

Result of ingestion for one telemetry bundle.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `READY` | Ready | No warnings. | active | doc 05 §6.2 |  |
| `READY_WITH_WARNINGS` | Ready with warnings | Usable, with recorded problems such as missing metrics. | active | doc 05 §6.2 |  |
| `REJECTED` | Rejected | Unusable: nothing parseable, identifiable, datable or measurable. | active | doc 05 §6.2 |  |

### Vocabulary: cause_type

Root-cause hypotheses the diagnosis catalog can score (closed list).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `normal_operation` | Normal operation | Assessed measurements are within expected ranges across enough of the scope. | active | SRC-1 p4 §5; doc 08 §3.1 | diagnosable=yes |
| `link_congestion` | Link congestion | High link utilization with elevated egress queue drops and increased delay on the same device. | active | SRC-1 p4 §5; doc 08 §3.1 | diagnosable=yes |
| `upstream_congestion` | Upstream congestion | Symptoms on a device whose own load is normal while a device on its path to the core is congested. | active | SRC-1 p5 §6 (alternative); doc 08 §3.1 | diagnosable=yes, needs topology |
| `weak_wifi` | Weak Wi-Fi signal | Poor wireless signal with retransmissions; requires wireless measurements. | active | SRC-1 p4 §5; doc 08 §3.1 | diagnosable=no: the generator has no wireless signal field (doc 06 §3) |
| `interface_fault` | Ethernet or interface fault | Rising interface errors, with packet loss localized to the interface. | active | SRC-1 p4 §5; doc 08 §3.1 | diagnosable=yes |
| `device_overload` | Device CPU overload | High CPU utilization on the device, with delay or drops on traffic through it. | active | SRC-1 p1 §1; doc 08 §3.1 | diagnosable=yes |
| `device_failure` | Device or hardware failure | The device reports a critical status, with symptoms explained by its failure. | active | SRC-1 p1 §1; doc 08 §3.1 | diagnosable=yes |
| `dns_dhcp_failure` | DNS or DHCP failure | Service checks fail while the network path is healthy. | active | SRC-1 p4 §5; doc 08 §3.3 | diagnosable=conditional: needs team-authored service-probe data |
| `telemetry_unreliable` | Telemetry unreliable | The data itself is broken or incompatible, so a network fault cannot be claimed. | active | SRC-1 p4 §5 (interoperability failure); doc 08 §3.1 | diagnosable=yes (as a data problem, never as a network fault) |

### Vocabulary: clarification_reason

Why a clarification is asked.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `conflict` | Conflict | Observations of the same thing disagree and the conflict rules could not resolve it. | active | doc 03 §3 |  |
| `narrow_margin` | Narrow margin | The top two explanations are closer than the decision margin. | active | doc 03 §3; doc 08 §4.4 |  |
| `missing_expected_evidence` | Missing expected evidence | Evidence the leading explanation predicts was not assessed. | active | doc 03 §3 |  |

### Vocabulary: confidence_category

Category reported next to the numeric confidence.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `high` | High | Score at or above t_high. | active | doc 08 §4.6 |  |
| `medium` | Medium | Score at or above t_med but below t_high. | active | doc 08 §4.6 |  |
| `low` | Low | Score below t_med. | active | doc 08 §4.6 |  |
| `insufficient` | Insufficient | The decision gate failed. | active | doc 08 §4.6 |  |

### Vocabulary: conflict_rule

Rule that settled a conflict between observations.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `evidence_class` | Evidence class | Direct measurement beats derived evidence, which beats a user report. | active | doc 08 §5 rule 1 |  |
| `freshness` | Freshness | A newer observation beats one older by more than the tolerance. | active | doc 08 §5 rule 2 |  |
| `topology_consistency` | Topology consistency | An explanation consistent with the dependency structure beats one that is not. | active | doc 08 §5 rule 3 |  |
| `unresolved` | Unresolved | No rule decides: both are kept, the weaker evidence is used and the conflict is stated. | active | doc 08 §5 rule 4 |  |

### Vocabulary: data_provenance

Where a telemetry bundle came from (values as used in scenario files).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `synthetic-generator` | Synthetic (generator) | Produced by the organizers' generator with fixed seeds. | active | doc 06; doc 09 §3 |  |
| `team-authored` | Team-authored synthetic | Generator output deliberately mutated by the team, labelled as such. | active | doc 05 §6.4 |  |
| `synthetic-generator + team-authored probes` | Synthetic + team-authored probes | Generator telemetry plus team-authored DNS/DHCP probe results. | active | doc 08 §3.3 |  |
| `unspecified` | Unspecified | The bundle declared no provenance. | active | doc 05 §11 |  |
| `verified-public` | Verified public | Checked against a public source; not available in this build. | **blocked** | doc 11 §2 |  |
| `verified-iitbbs` | Verified IIT Bhubaneswar | Authorized campus data; needs network-team access. | **blocked** | doc 11 §2; doc 15 |  |

### Vocabulary: decision_kind

Verdict in a decision message.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `diagnosed` | Diagnosed | Every gate condition holds: a probable cause is named. | active | doc 08 §4.5 |  |
| `insufficient_evidence` | Insufficient evidence | At least one gate condition fails: no single cause is asserted. | active | SRC-1 p2; doc 08 §4.5 |  |
| `no_fault_detected` | No fault detected | Assessed measurements are within range with enough coverage and no anomaly. | active | doc 08 §4.5; doc 08 §11 ID-14 |  |

### Vocabulary: dimension

Physical dimension of a metric; conversion only happens inside one dimension.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `time` | Time | Durations such as latency and jitter; canonical unit millisecond. | active | doc 06 §2 |  |
| `ratio` | Ratio | Shares of a whole; canonical unit percent. | active | doc 06 §2 |  |
| `count` | Count | Integer counts of events per sample; canonical unit count. | active | doc 06 §2 |  |
| `categorical` | Categorical | Named states with no numeric unit. | active | doc 06 §2 |  |
| `data_rate` | Data rate | Bits per second. No generator field uses it, so no units are defined (PROVISIONAL, D-17). | active | SRC-1 p4 §5 | provisional=True |
| `power_level` | Power level | Signal power such as dBm. No generator field uses it, so no units are defined (PROVISIONAL, D-17). | active | SRC-1 p4 §5 | provisional=True |

### Vocabulary: entity_type

Kinds of entity a message can refer to.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `device` | Device | A network device identified by the generator's device_id. | active | doc 06 §2 |  |
| `link` | Link | A connection between two devices in the SIMULATED topology. | active | sample_data/topology/README.md |  |
| `zone` | Zone | A placeholder campus area served by devices in the SIMULATED topology. | active | doc 10 §4; doc 11 §2 |  |

### Vocabulary: error_code

Every error, warning and limitation code the system emits. Severity: fatal stops the incident, error degrades it, warning is surfaced, info is logged.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `AGENT_FAILED` | Agent failed | An agent reported or suffered a failure. | active | doc 05 §7; doc 04 §5 | severity=error, kind=orchestration |
| `AGENT_MISSING` | Agent missing | No finding arrived from an agent; its evidence is absent. | active | doc 04 §5 | severity=warning, kind=limitation |
| `AGENT_TIMEOUT` | Agent timeout | An agent did not reply before its deadline. | active | doc 05 §7; doc 04 §5 | severity=error, kind=orchestration |
| `CAUSE_NOT_ASSESSABLE` | Cause not assessable | A cause cannot be assessed because its required evidence is not in the data. | active | doc 08 §3.2 | severity=info, kind=limitation |
| `CLARIFICATION_LIMIT_REACHED` | Clarification limit reached | The round limit was reached; the correlation agent decided on what it had. | active | doc 05 §7; doc 03 §3 | severity=info, kind=orchestration |
| `CONFLICT_UNRESOLVED` | Conflict unresolved | Conflicting observations could not be resolved by the rules. | active | doc 08 §5 | severity=warning, kind=limitation |
| `DATA_STALE` | Data stale | A device's newest data is older than the freshness limit. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `ENTITY_NOT_IN_TOPOLOGY` | Entity not in topology | A device is absent from the topology. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `ENTITY_UNUSABLE` | Entity unusable | A record has no usable device id. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `FIELD_ALIAS_APPLIED` | Field alias applied | A listed alternate field name was mapped. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `FIELD_IGNORED` | Field ignored | An unknown field was ignored and reported. | active | doc 05 §7; doc 05 §11 | severity=info, kind=ingestion |
| `FIELD_UNMAPPED` | Field unmapped | A field has no listed alias and is not interpreted. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `GATE_NOT_MET` | Gate not met | The decision gate failed, so no single cause is asserted. | active | doc 08 §4.5 | severity=info, kind=limitation |
| `INPUT_MODE_UNSUPPORTED` | Input mode unsupported | The bundle declares a mode other than simulation. | active | doc 05 §7; doc 05 §11 | severity=fatal, kind=ingestion |
| `INPUT_NO_ENTITY` | Input no entity | No record identifies a device. | active | doc 05 §7; doc 05 §11 | severity=fatal, kind=ingestion |
| `INPUT_NO_TIMESTAMP` | Input no timestamp | No record has a usable timestamp. | active | doc 05 §7; doc 05 §11 | severity=fatal, kind=ingestion |
| `INPUT_NO_USABLE_METRIC` | Input no usable metric | No record carries a usable metric. | active | doc 05 §7; doc 05 §11 | severity=fatal, kind=ingestion |
| `INPUT_SCHEMA_VERSION_UNSUPPORTED` | Input schema version unsupported | The bundle declares a schema major version with no adapter. | active | doc 05 §7; doc 05 §11 | severity=fatal, kind=ingestion |
| `INPUT_UNPARSEABLE` | Input unparseable | The input is not valid JSON or not a bundle. | active | doc 05 §7; doc 05 §11 | severity=fatal, kind=ingestion |
| `LLM_OUTPUT_REJECTED` | Llm output rejected | LLM wording failed the grounding check; template text was used. | active | doc 05 §7; doc 12 §9 | severity=info, kind=llm |
| `LLM_UNAVAILABLE` | Llm unavailable | No LLM was available; template text was used. | active | doc 05 §7; doc 12 §9 | severity=info, kind=llm |
| `MESSAGE_INVALID` | Message invalid | A message failed validation; it is logged and not delivered. | active | doc 05 §7 | severity=error, kind=protocol |
| `MESSAGE_ROUTING_INVALID` | Message routing invalid | A message bypassed the orchestrator or addressed its own sender. Deprecated since protocol 1.1: replaced by DIRECT_AGENT_MESSAGE_FORBIDDEN and RECIPIENT_NOT_ALLOWED. | deprecated | doc 03 §3; M2 | severity=error, kind=protocol |
| `METRIC_MISSING` | Metric missing | A metric is missing for some devices but present for others. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `METRIC_NOT_PROVIDED` | Metric not provided | A metric is absent from every record of the bundle. | active | doc 05 §7; doc 05 §11 | severity=info, kind=ingestion |
| `NO_SERVICE_PROBES` | No service probes | No DNS/DHCP probe data was supplied. | active | doc 08 §3.3 | severity=info, kind=limitation |
| `PAYLOAD_SCHEMA_VERSION_UNSUPPORTED` | Payload schema version unsupported | The payload schema major version is not supported. | active | doc 05 §10 | severity=error, kind=protocol |
| `PROBE_INVALID` | Probe invalid | A service-probe entry was malformed and dropped. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `PROTOCOL_VERSION_UNSUPPORTED` | Protocol version unsupported | The envelope's protocol major version is not supported. | active | doc 05 §10 | severity=error, kind=protocol |
| `RECORD_CONFLICT` | Record conflict | Different records exist for the same device and time. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `RECORD_DUPLICATE` | Record duplicate | An identical duplicate record was removed. | active | doc 05 §7; doc 05 §11 | severity=info, kind=ingestion |
| `SCHEMA_ADAPTER_APPLIED` | Schema adapter applied | A registered adapter converted an older bundle layout. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `STATUS_UNRECOGNIZED` | Status unrecognized | A device status is not Healthy, Warning or Critical. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `TIMESTAMP_UNUSABLE` | Timestamp unusable | A record's timestamp is missing, unparseable or has no timezone. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `TOOL_BUDGET_EXHAUSTED` | Tool budget exhausted | An agent used all its tool calls; its investigation may be incomplete. | active | doc 03 §1 | severity=warning, kind=orchestration |
| `TOPOLOGY_MISSING` | Topology missing | No topology is available. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `UNIT_AMBIGUOUS` | Unit ambiguous | A unit is missing, unknown or contradictory. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `UNIT_CONVERTED` | Unit converted | A value was converted to the canonical unit. | active | doc 05 §7; doc 05 §11 | severity=info, kind=ingestion |
| `VALUE_IMPLAUSIBLE` | Value implausible | A value is outside its definitional range. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `VALUE_MALFORMED` | Value malformed | A value is not a finite number. | active | doc 05 §7; doc 05 §11 | severity=warning, kind=ingestion |
| `MESSAGE_TOO_LARGE` | Message too large | The message exceeds the configured size limit and is rejected unread. | active | doc 05 §10 (P2); D-23 | severity=error, kind=protocol |
| `MODE_NOT_ALLOWED` | Mode not allowed | The envelope declares a mode other than simulation; it is never defaulted to live. | active | doc 05 §2 (P2) | severity=error, kind=protocol |
| `UNKNOWN_TERM` | Unknown term | A field holds a value that is not a registered (or is a blocked) vocabulary term. | active | doc 05 App. A (P2) | severity=error, kind=protocol |
| `PROTOCOL_MINOR_NEWER` | Protocol minor newer | The sender uses a newer minor protocol version; the message is accepted and unknown fields are ignored. | active | doc 05 §5 (P2) | severity=warning, kind=protocol |
| `ASSESSABILITY_VALUE_MISMATCH` | Assessability and value disagree | Rule 1: a not_assessable observation carries a value, a severity other than unknown, or no reason; or an assessed observation has no value. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `UNIT_INCOMPATIBLE` | Unit incompatible | Rule 2: the declared unit is unknown or does not fit the dimension of the observation's metric. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `HYPOTHESIS_WITHOUT_EVIDENCE` | Hypothesis without evidence | Rule 3: a hypothesis cites no supporting evidence and names no missing expected evidence. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `EVIDENCE_STANCE_MISMATCH` | Evidence stance mismatch | Rule 3: a supporting reference without stance supports, or a contradicting one without stance contradicts. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `EVIDENCE_REFS_DISAGREE` | Evidence references disagree | A hypothesis's evidence references and its observation-id lists name different observations. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `EVIDENCE_PREFIX_MISMATCH` | Evidence id prefix mismatch | Rule 5: the evidence id does not start with the prefix of its evidence type. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `RECOMMENDATION_SAFETY_VIOLATION` | Recommendation safety violation | Rule 6: a recommendation tried to set requires_human_approval or simulated to false. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `ABSTENTION_MISMATCH` | Abstention block mismatch | An insufficient_evidence decision has no abstention block, or a diagnosed decision has one. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `CLARIFICATION_PARAMETERS_INVALID` | Clarification parameters invalid | A clarification request lacks a parameter its question type needs. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `CLARIFICATION_ANSWER_MISMATCH` | Clarification answer mismatch | A clarification response's answerable value contradicts its answered flag. | active | doc 05 §14 (P3) | severity=error, kind=protocol |
| `SENDER_NOT_AUTHORIZED` | Sender not authorized | The authority matrix does not allow this participant to send this message type. | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `RECIPIENT_NOT_ALLOWED` | Recipient not allowed | This message type from this sender may not go to this recipient (or a participant messaged itself). | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `MESSAGE_OUT_OF_SEQUENCE` | Message out of sequence | The message is legal only in other incident states, was already sent once, or needs an earlier decision. | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `REPLY_MISMATCH` | Reply mismatch | in_reply_to is missing, or does not point to an open request addressed to the sender. | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `DUPLICATE_MESSAGE` | Duplicate message | A message with this id was already accepted in the incident. | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `INCIDENT_CLOSED` | Incident closed | The incident is complete, failed or rejected; no further messages are accepted. | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `CLARIFICATION_LIMIT_EXCEEDED` | Clarification limit exceeded | A clarification question beyond the configured rounds per incident (default 2). | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `DIRECT_AGENT_MESSAGE_FORBIDDEN` | Direct agent message forbidden | Hub and spoke: every message is to or from the orchestrator; agents never message each other directly. | active | doc 05 §15 (P4) | severity=error, kind=conversation |
| `EXTENSION_DISABLED` | Extension disabled | The message belongs to an extension whose feature flag is off (e.g. community_candidate without community_signals). | active | doc 05 §15 (P4) | severity=error, kind=conversation |

### Vocabulary: evidence_class

Strength class used by conflict rule 1.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `direct_measurement` | Direct measurement | Read directly from telemetry. | active | doc 08 §5 |  |
| `derived` | Derived | Computed or inferred from other evidence. | active | doc 08 §5 |  |
| `user_report` | User report | Reported by a person; unverified. | active | doc 08 §5-6 |  |

### Vocabulary: evidence_stance

Whether evidence supports or contradicts a hypothesis (PROVISIONAL, D-19).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `supports` | Supports | Makes the hypothesis more likely. | active | doc 05 §4 |  |
| `contradicts` | Contradicts | Makes the hypothesis less likely. | active | doc 05 §4 |  |
| `neutral` | Neutral | Relevant context that neither supports nor contradicts. | active | PROPOSAL |  |

### Vocabulary: evidence_type

What an evidence reference points at (PROVISIONAL, D-19).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `observation` | Observation | A measured or derived fact in a finding. | active | doc 05 §4 | id_prefix=OBS- |
| `hypothesis` | Hypothesis | An agent-local interpretation. | active | doc 05 §4 | id_prefix=HYP- |
| `normalized_record` | Normalized record | One record of the normalized bundle. | active | doc 05 §6 | id_prefix=REC- |
| `community_report` | Community report | An unverified candidate built from complaints. | active | doc 10 | id_prefix=CAND- |
| `tool_result` | Tool result | The recorded result of a tool call. | active | doc 03 §1 | id_prefix= |
| `topology_element` | Topology element | A device or link in the SIMULATED topology. | active | doc 11 | id_prefix= |

### Vocabulary: incident_state

Incident workflow states (doc 04 §2).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `RECEIVED` | Received | Input received; incident id assigned. | active | doc 04 §2 |  |
| `VALIDATING` | Validating | Ingestion is checking and normalizing the input. | active | doc 04 §2 |  |
| `REJECTED` | Rejected | The input was unusable; a failure report was issued. Terminal. | active | doc 04 §2 |  |
| `READY` | Ready | Usable input with no warnings. | active | doc 04 §2 |  |
| `READY_WITH_WARNINGS` | Ready with warnings | Usable input with recorded warnings. | active | doc 04 §2 |  |
| `DISPATCHED` | Dispatched | Tasks sent to the specialist agents. | active | doc 04 §2 |  |
| `COLLECTING` | Collecting | Waiting for specialist findings; failures and retries are recorded here. | active | doc 04 §2 |  |
| `CORRELATING` | Correlating | The correlation agent is weighing the findings. | active | doc 04 §2 |  |
| `CLARIFYING` | Clarifying | A clarification question is being answered. | active | doc 04 §2 |  |
| `DECIDED` | Decided | The correlation agent's decision is recorded. | active | doc 04 §2 |  |
| `REPORTING` | Reporting | The reporting agent is building the report. | active | doc 04 §2 |  |
| `AWAITING_REVIEW` | Awaiting review | Recommendations wait for a human decision; actions stay simulated. | active | doc 04 §2 |  |
| `COMPLETE` | Complete | Incident closed. Terminal. | active | doc 04 §2 |  |
| `FAILED` | Failed | An unrecoverable internal error; a failure report was issued. Terminal. | active | doc 04 §2 |  |

### Vocabulary: message_status

Outcome flag carried by every envelope.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `ok` | OK | The sender completed the work fully. | active | doc 05 §2 |  |
| `partial` | Partial | The sender completed part of the work, for example could not assess its whole scope. | active | doc 05 §2 |  |
| `error` | Error | The message reports a failure. | active | doc 05 §2 |  |

### Vocabulary: message_type

Kinds of protocol message.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `task_request` | Task request | Orchestrator asks one agent to do a scoped piece of work within a budget and deadline. | active | doc 05 §3 |  |
| `finding` | Finding | A specialist's independent observations, hypotheses, unknowns and tool trail for one task. | active | doc 05 §3 |  |
| `clarification_request` | Clarification request | A bounded, typed question one agent asks another through the orchestrator. | active | doc 05 §3; doc 03 §3 |  |
| `clarification_response` | Clarification response | The answer to a clarification request, or a stated reason it cannot be answered. | active | doc 05 §3 |  |
| `decision` | Decision | The correlation agent's ranked hypotheses and its verdict: diagnosed, insufficient evidence or no fault. | active | doc 05 §3 |  |
| `report_ready` | Report ready | The reporting agent delivers the validated report and its Markdown rendering. | active | doc 05 §3 |  |
| `agent_error` | Agent error | A failure, timeout or invalid message, with a code and whether it is recoverable. | active | doc 05 §3 |  |
| `community_candidate` | Community candidate | An unverified candidate incident built from user complaints (Extension A). | active | doc 05 §3; doc 10 |  |

### Vocabulary: metric

Metric names used in observations: the generator's observed fields plus team-authored probe items. Never invent more (CLAUDE.md rule 1).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `latency_ms` | Latency | Generator field 'latency_ms' (doc 06 §2), category latency, unit millisecond. | active | OBSERVED doc 06 §2 | origin=generator, category=latency, unit=millisecond, dimension=time |
| `jitter_ms` | Jitter | Generator field 'jitter_ms' (doc 06 §2), category jitter, unit millisecond. | active | OBSERVED doc 06 §2 | origin=generator, category=jitter, unit=millisecond, dimension=time |
| `packet_loss_pct` | Packet loss | Generator field 'packet_loss_pct' (doc 06 §2), category packet_loss, unit percent. | active | OBSERVED doc 06 §2 | origin=generator, category=packet_loss, unit=percent, dimension=ratio |
| `link_utilization_pct` | Link utilization | Generator field 'link_utilization_pct' (doc 06 §2), category link_utilization, unit percent. | active | OBSERVED doc 06 §2 | origin=generator, category=link_utilization, unit=percent, dimension=ratio |
| `cpu_utilization_pct` | CPU utilization | Generator field 'cpu_utilization_pct' (doc 06 §2), category cpu_utilization, unit percent. | active | OBSERVED doc 06 §2 | origin=generator, category=cpu_utilization, unit=percent, dimension=ratio |
| `queue_drops` | Egress queue drops | Generator field 'queue_drops' (doc 06 §2), category egress_queue_drops, unit count. | active | OBSERVED doc 06 §2 | origin=generator, category=egress_queue_drops, unit=count, dimension=count |
| `interface_errors` | Interface errors | Generator field 'interface_errors' (doc 06 §2), category interface_errors, unit count. | active | OBSERVED doc 06 §2 | origin=generator, category=interface_errors, unit=count, dimension=count |
| `status` | Device status | Generator field 'status': Healthy, Warning or Critical (doc 06 §2). | active | OBSERVED doc 06 §2 | origin=generator, category=device_status, unit=none, dimension=categorical |
| `probe_dns` | DNS probe | Outcome of a team-authored DNS service check (success, failure, timeout). | active | doc 08 §3.3; ID-06 | origin=team_authored_probe, unit=outcome, dimension=categorical |
| `probe_dhcp` | DHCP probe | Outcome of a team-authored DHCP service check (success, failure, timeout). | active | doc 08 §3.3; ID-06 | origin=team_authored_probe, unit=outcome, dimension=categorical |
| `topology` | Topology placement | Whether the entity could be placed in the topology; used only in not-assessable items. | active | doc 05 §4 (NO_TOPOLOGY) | origin=structural, unit=none, dimension=categorical |

### Vocabulary: metric_category

Metric categories named in the problem statement (SRC-1 p4 §5). Categories, not field names.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `latency` | Latency | The 'latency' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=time, in_generator_data=True |
| `jitter` | Jitter | The 'jitter' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=time, in_generator_data=True |
| `packet_loss` | Packet loss | The 'packet loss' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=ratio, in_generator_data=True |
| `throughput` | Throughput | The 'throughput' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=data_rate, in_generator_data=False |
| `bandwidth` | Bandwidth | The 'bandwidth' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=data_rate, in_generator_data=False |
| `link_utilization` | Link utilization | The 'link utilization' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=ratio, in_generator_data=True |
| `device_status` | Device status | The 'device status' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=categorical, in_generator_data=True |
| `cpu_utilization` | CPU utilization | The 'cpu utilization' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=ratio, in_generator_data=True |
| `memory_utilization` | Memory utilization | The 'memory utilization' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=ratio, in_generator_data=False |
| `egress_queue_drops` | Egress queue drops | The 'egress queue drops' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=count, in_generator_data=True |
| `interface_errors` | Interface errors | The 'interface errors' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=count, in_generator_data=True |
| `wireless_signal` | Wireless signal measurements | The 'wireless signal measurements' category from the problem statement's dataset list. | active | SRC-1 p4 §5 | dimension=power_level, in_generator_data=False |

### Vocabulary: mode

Operating mode. Only simulation is accepted in this build.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `simulation` | Simulation | Synthetic or authorized test data, scenario playback, simulated actions. | active | doc 00 §4; R-17 |  |
| `deployment` | Deployment | Authorized campus feeds; defined for documentation only and never accepted. | **blocked** | doc 15 |  |

### Vocabulary: not_assessable_reason

Why an entity-metric pair could not be assessed.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `MISSING` | Missing | The metric is absent for this entity. | active | doc 05 §4 |  |
| `MALFORMED` | Malformed | The value is not a usable number or recognised status. | active | doc 05 §4 |  |
| `UNMAPPED_FIELD` | Unmapped field | A field may carry the metric but has no listed alias, so it is not interpreted. | active | doc 05 §4 |  |
| `UNIT_AMBIGUOUS` | Unit ambiguous | The unit is missing, unknown or contradicts the field name. | active | doc 05 §4 |  |
| `STALE` | Stale | The newest data is older than the freshness limit. | active | doc 05 §4 |  |
| `INSUFFICIENT_SAMPLES` | Insufficient samples | Too few samples to judge. | active | doc 05 §4 |  |
| `NO_TOPOLOGY` | No topology | Topology is missing or does not contain the entity. | active | doc 05 §4 |  |
| `OUT_OF_SCOPE` | Out of scope | The entity or item is not part of the bundle being analysed. | active | doc 05 §4 |  |
| `IMPLAUSIBLE` | Implausible | The value is outside the definitional range, for example a percentage above 100. | active | doc 05 §10 |  |

### Vocabulary: question_type

Closed list of clarification questions.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `widen_time_window` | Widen time window | Re-examine entities over the whole bundle window. | active | doc 03 §3 |  |
| `assess_additional_entities` | Assess additional entities | Examine entities outside the original scope. | active | doc 03 §3 |  |
| `what_if_cause` | What-if cause | Which entities would be isolated or degraded if this entity failed. | active | doc 03 §3 |  |
| `recheck_metric` | Re-check metric | Read one metric of one entity again. | active | doc 03 §3 |  |

### Vocabulary: rationale_code

Why a specialist attached a local hypothesis. Extensible with 'x-' ids for site-specific rules.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `HIGH_UTILIZATION_WITH_DELAY` | High utilization with delay | Link utilization and latency or jitter are both abnormal. | active | agents/performance.py |  |
| `DELAY_WITH_NORMAL_LOCAL_UTILIZATION` | Delay with normal local utilization | Delay is abnormal although the device's own link load is normal. | active | agents/performance.py |  |
| `LOSS_WITHOUT_LOAD` | Loss without load | Packet loss is abnormal without high link utilization. | active | agents/performance.py |  |
| `DEVICE_REPORTS_CRITICAL` | Device reports critical | The device's own status is Critical. | active | agents/infrastructure.py |  |
| `HIGH_CPU` | High CPU | CPU utilization is abnormal. | active | agents/infrastructure.py |  |
| `INTERFACE_ERRORS` | Interface errors | Interface error counts are abnormal. | active | agents/infrastructure.py |  |
| `QUEUE_DROPS` | Queue drops | Egress queue drops are abnormal. | active | agents/infrastructure.py |  |
| `SERVICE_PROBES_FAIL` | Service probes fail | Team-authored DNS/DHCP probes from the device fail or time out. | active | agents/connectivity.py |  |

### Vocabulary: recommendation_mode

How the reporting agent framed its recommendations.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `corrective` | Corrective | Diagnosed: actions that address the probable cause. | active | doc 07 §9 |  |
| `monitoring` | Monitoring | No fault: keep monitoring and collect what could not be assessed. | active | doc 07 §9 |  |
| `diagnostic_next_steps` | Diagnostic next steps | Insufficient evidence: steps that would settle the question. | active | doc 07 §9 |  |
| `fix_input` | Fix input | Failed: correct the input or failing component and re-run. | active | doc 07 §9 |  |

### Vocabulary: recommendation_priority

Priority of a recommendation (PROVISIONAL, D-19; not used yet).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `high` | High | Act first. | active | PROPOSAL |  |
| `medium` | Medium | Act after high-priority items. | active | PROPOSAL |  |
| `low` | Low | Optional. | active | PROPOSAL |  |

### Vocabulary: report_status

Value of the official report key `status` (PROVISIONAL, open decision D-03).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `diagnosed` | Diagnosed | A probable cause is named with supporting evidence. | active | SRC-1 p5 §6 |  |
| `insufficient_evidence` | Insufficient evidence | Evidence does not support a single probable cause. | active | D-03 default |  |
| `no_fault_detected` | No fault detected | Assessed measurements are within expected ranges. | active | D-03 default |  |
| `failed` | Failed | No diagnosis was possible: input rejected or an internal failure. | active | D-03 default |  |

### Vocabulary: score_method

How a score was produced.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `heuristic` | Heuristic | The documented scoring method of doc 08 §4; a ranking, not a probability. | active | doc 08 §4; CD-6 |  |
| `agent_local_heuristic` | Agent-local heuristic | A specialist's own rough score for its hypothesis; never the final confidence. | active | doc 05 §4 |  |
| `calibrated` | Calibrated | Validated against ground truth; blocked until the doc 08 §9 gate is recorded. | **blocked** | doc 08 §9 |  |

### Vocabulary: severity

How abnormal one observation is.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `normal` | Normal | Within the expected range set in config/diagnosis.toml. | active | doc 05 §4; doc 08 §11 |  |
| `elevated` | Elevated | Above the expected range but below the critical level. | active | doc 05 §4; doc 08 §11 |  |
| `critical` | Critical | At or above the critical level. | active | doc 05 §4; doc 08 §11 |  |
| `unknown` | Unknown | Could not be graded; never treated as normal. | active | doc 05 §4; CD-10 |  |

### Vocabulary: task_kind

Kind of work a task asks for (PROVISIONAL, D-19; carried as `goal` today).

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `investigate` | Investigate | A specialist examines its scope (goals assess_performance, assess_device_health, assess_connectivity_scope). | active | doc 04 §3 |  |
| `correlate` | Correlate | The correlation agent weighs findings (goal correlate). | active | doc 04 §3 |  |
| `report` | Report | The reporting agent builds the report (goal report). | active | doc 04 §3 |  |

### Vocabulary: topology_provenance

Provenance label carried by a topology file.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `SIMULATED` | Simulated | Team-authored synthetic topology. | active | doc 11 §2; ID-04 |  |
| `VERIFIED-PUBLIC` | Verified public | Not available in this build. | **blocked** | doc 11 §2 |  |
| `VERIFIED-IITBBS` | Verified IIT Bhubaneswar | Needs network-team access. | **blocked** | doc 11 §2 |  |

### Vocabulary: trust_label

How far user reports are confirmed by telemetry.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `reported_unverified` | Reported, unverified | Users reported a problem; telemetry does not show a matching fault. | active | doc 08 §6; doc 10 §6 |  |
| `detected` | Detected | Telemetry shows a fault that no user report refers to. | active | doc 08 §6 |  |
| `corroborated` | Corroborated | User reports and a diagnosed telemetry fault point to the same devices. | active | doc 08 §6 |  |

### Vocabulary: unit

Units the code reads or emits. `factor` converts to the canonical unit of the dimension.

| Id | Label | Definition | Status | Source | Attributes |
|---|---|---|---|---|---|
| `millisecond` | ms | Thousandth of a second; canonical time unit. | active | doc 06 §2 | symbol=ms, dimension=time, factor=1.0, canonical=True, spellings=[ms, millisecond] |
| `second` | s | One second. | active | config/aliases.toml (team-authored) | symbol=s, dimension=time, factor=1000.0, canonical=False, spellings=[s, second] |
| `microsecond` | us | Millionth of a second. | active | config/aliases.toml (team-authored) | symbol=us, dimension=time, factor=0.001, canonical=False, spellings=[us, microsecond] |
| `percent` | % | Parts per hundred; canonical ratio unit. | active | doc 06 §2 | symbol=%, dimension=ratio, factor=1.0, canonical=True, spellings=[pct, percent, %] |
| `ratio` | ratio | Fraction of one (0.94 means 94 percent); only ever used when declared. | active | config/aliases.toml (team-authored) | symbol=ratio, dimension=ratio, factor=100.0, canonical=False, spellings=[ratio, fraction] |
| `count` | count | Number of events reported in one sample. | active | doc 06 §2 | symbol=count, dimension=count, factor=1.0, canonical=True, spellings=[count] |
| `none` | - | No unit: a named state such as device status. | active | doc 06 §2 | symbol=-, dimension=categorical, factor=1.0, canonical=True, spellings=[] |
| `outcome` | outcome | Result of a service probe: success, failure or timeout. | active | doc 08 §3.3 | symbol=outcome, dimension=categorical, factor=1.0, canonical=False, spellings=[] |

<!-- END GENERATED: vocabulary -->
