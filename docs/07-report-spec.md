# 07 — Diagnostic Report Specification

> Version 0.1 · 2026-10-31 · Draft for review · Field names, types and example verified against `SRC-1 p5 §6` on 2026-10-31

## 1. The official report (`CONFIRMED`)

`SRC-1 p5 §6`: "The application must generate a structured JSON report." The PDF gives this *illustrative* example and states the values "do not represent actual campus network measurements":

```json
{
  "incident_id": "INC-8832",
  "status": "diagnosed",
  "suspected_root_cause": "Likely link congestion causing egress queue drops",
  "confidence": 0.86,
  "affected_devices": ["HOSTEL_CORE_SW_01"],
  "supporting_evidence": [
    { "metric": "link_utilization_pct", "value": 94, "interpretation": "High link utilization" },
    { "metric": "queue_drops", "value": 160, "interpretation": "Elevated packet drops" },
    { "metric": "latency_ms", "value": 280, "interpretation": "Elevated network latency" }
  ],
  "alternative_causes": ["Upstream link congestion"],
  "recommended_actions": [
    "Inspect upstream and egress link utilization",
    "Review queue configuration and traffic distribution"
  ],
  "evidence_sources": ["performance_agent", "infrastructure_agent"],
  "limitations": ["Root cause requires further verification"]
}
```

(Layout condensed; keys, values and nesting are as in the PDF.)

### 1.1 What the PDF fixes and what it does not

| Key | Type *as shown in the example* | Allowed values stated in PDF? |
|---|---|---|
| `incident_id` | string | No (format not mandated) |
| `status` | string | **No** — only `"diagnosed"` is shown |
| `suspected_root_cause` | string | No |
| `confidence` | number | No range stated; example 0.86 |
| `affected_devices` | array of strings | No |
| `supporting_evidence` | array of objects with `metric` (string), `value` (number), `interpretation` (string) | No |
| `alternative_causes` | array of strings | No |
| `recommended_actions` | array of strings | No |
| `evidence_sources` | array of strings (agent identifiers) | No |
| `limitations` | array of strings | No |

- The PDF does **not** mark individual keys mandatory. The mandatory *content* is: probable cause, evidence, affected devices where identifiable, uncertainty, recommended actions (`SRC-1 p3 §4, p6 §9`).
- `metric` names in the example (`link_utilization_pct`, `queue_drops`, `latency_ms`) are illustrative and are **not** confirmed dataset fields.
- Types above are read from the example only (`INTERPRETATION`); they are not stated rules.

## 2. How required content maps onto the keys (`INTERPRETATION`)

| Required content | Key(s) |
|---|---|
| Probable root cause | `suspected_root_cause` |
| Supporting evidence | `supporting_evidence`, `evidence_sources` |
| Affected devices where identifiable | `affected_devices` |
| Uncertainty | `confidence`, `alternative_causes`, `limitations` |
| Recommended actions | `recommended_actions` |
| Status of the diagnosis | `status` |

## 3. Emission rules (`PROPOSAL`)

1. **Always emit all ten official keys, unrenamed, with the types shown.** Where nothing applies, emit an empty array (e.g. `affected_devices: []` when no device is identifiable); never omit a key.
2. **Two output modes:**
   - **Strict-official:** exactly the ten keys.
   - **Extended (default for the dashboard):** the ten keys plus **one** additional top-level key, `netcoop_extensions` (§5). Extended output never alters the meaning of an official key.
3. `supporting_evidence` contains **telemetry-derived evidence only**. Complaint-based evidence goes in the extension block so verified and unverified information are never mixed (`X-CSI-08`).
4. `evidence_sources` lists the agent identifiers whose observations actually back the listed evidence.
5. Every `supporting_evidence` entry must trace to an observation ID in the message log (§8).

## 4. Open conventions — decisions needed

The PDF is silent on these; each default is a `PROPOSAL`.

| ID | Question | Proposed default |
|---|---|---|
| D-03 | `status` values beyond `diagnosed` | `diagnosed`; `insufficient_evidence`; `no_fault_detected` (normal operation); `failed` (internal failure or rejected input) |
| D-04 | `confidence` when evidence is insufficient | Still a number (type preserved): the leading hypothesis's heuristic score, capped at a low configured ceiling; `confidence_category` in the extension block = `insufficient` |
| D-05 | `supporting_evidence[].value` for non-numeric evidence such as device status | Allow number or string; document it. If the owner prefers numbers only, non-numeric evidence is expressed in `interpretation` |

Conventions for non-diagnosed results (using the defaults above):

| Status | `suspected_root_cause` | `confidence` | `alternative_causes` |
|---|---|---|---|
| `diagnosed` | The leading cause, worded as "likely/probable" | Heuristic score | Runners-up |
| `insufficient_evidence` | States the cause is undetermined and names the leading candidates, e.g. "Undetermined — leading candidates: …" | Capped low number | The candidates |
| `no_fault_detected` | States that assessed metrics are within expected ranges, and for what share of the scope | Score for the "normal" hypothesis (needs assessed evidence) | `[]` or residual risks |
| `failed` | States that no diagnosis was possible and why | `0` | `[]` |

## 5. The extension block `netcoop_extensions` (`PROPOSAL`)

Absent in strict-official output. Content (names provisional):

| Part | Content |
|---|---|
| `schema_version` | Version of this extension layout |
| `mode`, `data_provenance` | `simulation` / `deployment`; e.g. synthetic, team-authored synthetic — drives the "simulated data" banner |
| `confidence_method` | `heuristic` (until the validation gate in doc 08 §9 is met, then may say otherwise) |
| `confidence_category` | high / medium / low / insufficient |
| `data_quality` | Completeness, freshness, consistency, bundle acceptance level and warnings |
| `not_assessable` | Entity-metric pairs that could not be assessed, with reasons |
| `hypotheses` | Ranked hypotheses with score, supporting/contradicting observation IDs, missing expected evidence |
| `agent_contributions` | Per agent: findings count, tool calls, whether it timed out |
| `clarifications` | Questions asked and answers, or unanswered at the limit |
| `conflicts` | Conflicts found and which rule resolved them |
| `blast_radius` | Isolated and degraded entities (from A-CONN) — extension B |
| `community_signals` | Candidate incidents, cluster size, trust label (`reported_unverified` / `detected` / `corroborated`) — extension A |
| `recommendation_status` | Each recommendation: requires human approval; approval state; simulated |
| `llm_assistance` | Which text fields, if any, were LLM-reworded |
| `generated_at` | UTC timestamp |

## 6. Failure and rejection reports

A rejected bundle (`REJECTED`) or internal failure produces a schema-valid report with `status: failed`, the ten keys filled per §4, and the error codes (doc 05 §7) in `limitations` (and fully in the extension block). The system never emits a diagnosis after a fatal input error.

## 7. Markdown report (optional, `SRC-1 p5 §6`)

Rendered from the JSON, never the other way round. Sections: header (incident, status, **data-provenance banner**); conclusion and confidence with its method label; evidence table; affected devices; alternatives; what could not be assessed; recommendations (marked requiring approval); agent trace summary; limitations.

## 8. Validation rules

- Official keys present, correct types (`T-RPT-SCHEMA-01`).
- No extra top-level keys in strict-official mode; exactly one (`netcoop_extensions`) in extended mode.
- Every evidence entry traces to an observation ID; every ID resolves in the log.
- `evidence_sources` ⊆ agents that sent a `finding` for this incident.
- `status = diagnosed` ⇒ decision gate passed (doc 08 §4.5).
- `status = insufficient_evidence` ⇒ `suspected_root_cause` must not assert a single established cause.
- No community-sourced item inside the official keys.
- The word "calibrated" appears nowhere unless the doc 08 §9 gate is recorded as met.
