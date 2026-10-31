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

## 3. Message types

| Type | Direction | Payload summary |
|---|---|---|
| `task_request` | Orchestrator → agent | Goal; scope (entities); time window; tool-call budget; deadline |
| `finding` | Agent → Orchestrator | Observations; hypotheses; not-assessable items; limitations; tool-call records; self-assessment (completeness) |
| `clarification_request` | Agent → Orchestrator → target | Question type (closed list, doc 03 §3); parameters; reason; round number |
| `clarification_response` | Target → Orchestrator → requester | Answer (observations or what-if result) or "cannot answer" with reason |
| `decision` | A-CORR → Orchestrator | Ranked hypotheses with scores; decision (`diagnosed` / `insufficient_evidence` / `no_fault_detected`); conflict trail |
| `report_ready` | A-REPT → Orchestrator | The report (doc 07) |
| `agent_error` | Any | Error code (§7), message, recoverable? |
| `community_candidate` | Community module → Orchestrator | Candidate incident (extension, doc 10) |

## 4. Payload building blocks

Names are protocol design choices. Metric categories are written in words until doc 06 exists.

**Observation** — a measured or derived fact.
`observation_id` · `entity` (device, link, or zone as identified in the normalized data) · `metric_category` · `value` · `unit` · `window` (start, end) · `severity` (`normal`, `elevated`, `critical`, `unknown`) · `assessability` (`assessed`, `assessed_with_caveat`, `not_assessable`) · `quality_flags` · `source_ref` (pointer to normalized record(s), and through them the raw record)

**Hypothesis** — an interpretation, never a fact.
`hypothesis_id` · `cause_type` (from the catalog, doc 08 §3) · `entities` · `supporting_observation_ids` · `contradicting_observation_ids` · `missing_expected_evidence` · `local_score` (agent-local heuristic, not the final confidence) · `rationale_code`

**Not-assessable item** — an unknown, stated explicitly.
`entity` · `metric_category` · `reason` (`MISSING`, `MALFORMED`, `UNMAPPED_FIELD`, `UNIT_AMBIGUOUS`, `STALE`, `INSUFFICIENT_SAMPLES`, `NO_TOPOLOGY`, `OUT_OF_SCOPE`) · `detail`

**Limitation** — free-text statement of what the agent could not conclude, with a code.

**Tool-call record** — `tool` · `arguments` summary · `result` summary · `timestamp`. Makes the agent's investigation visible.

**Self-assessment** — fraction of the assigned scope the agent could actually assess, and whether it hit its tool budget.

## 5. Identifiers, time, versions

- **Agent identifiers** are fixed strings (doc 02 §2). `performance_agent` and `infrastructure_agent` match the official example (`SRC-1 p5 §6`).
- **Incident ID** format is not mandated by the PDF (the example is `INC-8832`); format decided at implementation. `PENDING`
- **Time:** internal timestamps are UTC. Input timestamp format, timezone and sampling interval are `PENDING` (generator).
- **Versioning (semantic):**
  - *Minor* change = additive (new optional field, new enum value readers can ignore) → accepted by older readers.
  - *Major* change = breaking → rejected with `INPUT_SCHEMA_VERSION_UNSUPPORTED` unless a registered adapter exists.
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

- In-process message bus; each message is serialized to JSON, validated, appended to the log, then delivered. `PLANNED`
- No broker, no MCP, no external agent framework at this stage (`CD-2`).
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
