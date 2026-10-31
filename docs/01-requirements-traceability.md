# 01 — Requirements Traceability Matrix

> Version 0.1 · 2026-10-31 · Draft for review
> **Implementation status: see §10** (updated 2026-10-31 after milestone M9). Rows in §2–§9 keep the original design mapping.

Every official requirement from `SRC-1` (`Agentic_AI_Hackathon.pdf`) is listed with its page and section, and mapped to the architecture component, documentation file, planned implementation module, planned test and planned demonstration evidence. Official requirements are never merged with our extensions or project rules (§8–§9).

## 1. How to read this file

- **Source:** `p<page> §<section>` in `SRC-1`.
- **Requirement:** a close paraphrase of the PDF wording. If the wording matters it is quoted.
- **Component:** IDs defined in [doc 02 §2](02-architecture.md). **Module:** paths in [doc 02 §7](02-architecture.md).
- **Doc:** file number in `docs/`. **Test:** families defined in [doc 09](09-scenarios-and-testing.md) (`*` = several tests). **Demo:** segments defined in [doc 14](14-demo-and-submission.md).
- A row is only ticked "done" in a later version after its test passes and its demo evidence exists.

## 2. Official requirements — what to build (`SRC-1 p1–p5`)

| ID | Source | Requirement | Component | Doc | Module (planned) | Test | Demo |
|---|---|---|---|---|---|---|---|
| R-01 | p1 §2 | Identify the probable root cause of a network issue | A-CORR, C-DIAG | 08 | `agents/correlation`, `diagnosis/` | T-SCN-*, T-DIAG-01 | Demo-2 |
| R-02 | p1 §2 | Identify affected devices or network segments where possible | A-CONN, C-TOOL | 03, 08 | `agents/connectivity`, `tools/topology` | T-AGT-CONN-* | Demo-2, 8 |
| R-03 | p1 §2 | Provide supporting evidence from telemetry and agent findings | all agents, C-RPT | 05, 07 | `core/messages`, `report/` | T-RPT-EVID-01 | Demo-2 |
| R-04 | p1 §2 | Include alternative explanations or uncertainty where appropriate | A-CORR | 08 | `diagnosis/scoring` | T-DIAG-ALT-01 | Demo-2, 5 |
| R-05 | p1 §2 | Provide a confidence estimate or a clearly defined confidence category | A-CORR, C-DIAG | 07, 08 | `diagnosis/scoring` | T-DIAG-CONF-* | Demo-2 |
| R-06 | p1 §2 | Recommend practical corrective actions | A-REPT | 03, 07 | `agents/reporting` | T-RPT-ACT-01 | Demo-2, 6 |
| R-07 | p2 §2 | "The system must not claim an exact root cause when the available evidence is insufficient" | A-CORR (decision gate) | 08 | `diagnosis/gate` | T-DIAG-INSUF-* | Demo-5 |
| R-08 | p2 §3, p3 §4 | At least two functional agents with distinct responsibilities collaborate in the minimum prototype; four to five encouraged; listed roles are examples, not rigid | A-PERF, A-INFRA, A-CONN, A-CORR, A-REPT, C-ORC | 03, 04 | `agents/*`, `orchestrator/` | T-ORCH-COLLAB-*, T-AGT-* | Demo-2 |
| R-09 | p3 §4 | Agent interoperability: document message formats, field meanings and units; provide a way to exchange and interpret findings | C-BUS, C-ING | 05, 06 | `core/messages`, `ingestion/normalize` | T-PROTO-*, T-ING-* | Demo-2, 4 |
| R-10 | p3 §4 | Agent orchestration: coordinate agent tasks and consolidate findings into one result | C-ORC | 04 | `orchestrator/` | T-ORCH-* | Demo-2 |
| R-11 | p3 §4 | Network fault diagnosis: analyze supplied telemetry and identify probable root causes with supporting evidence | agents, C-DIAG | 08 | `agents/*`, `diagnosis/` | T-SCN-* | Demo-1, 2 |
| R-12 | p3 §4 | Unified diagnostic report: probable cause, evidence, affected devices where identifiable, uncertainty, recommended actions | C-RPT, A-REPT | 07 | `report/`, `agents/reporting` | T-RPT-* | Demo-2 |
| R-13 | p3 §4 | Basic validation and error handling: handle relevant malformed, missing or incompatible inputs; report failures clearly | C-ING | 05, 09 | `ingestion/validate` | T-ERR-* | Demo-3, 4 |
| R-14 | p3 §4 | Reproducible testing and documentation: sample inputs, test scenarios, setup instructions, demonstration | `sample_data/`, `tests/` | 09, 13, 14 | `sample_data/`, `tests/`, `scripts/` | T-REPRO-* | Demo-1 |
| R-15 | p5 §6 | Application must generate a structured JSON report; a Markdown report or dashboard may be added | C-RPT | 07 | `report/` | T-RPT-SCHEMA-* | Demo-2 |
| R-16 | p5 §6 | Confidence based on a documented scoring method or calibrated model; able to report insufficient evidence | C-DIAG | 08 | `diagnosis/scoring` | T-DIAG-CONF-*, T-DIAG-INSUF-* | Demo-5 |
| R-17 | p4 §5 | Use synthetic telemetry, organizer scenarios, or data from an authorized test environment; production campus access not required | C-CFG, C-SRC | 00, 12 | `ingestion/sim_source`, `config/` | T-MODE-* | all (banner) |
| R-18 | p4 §5 | Suggested test scenarios: normal operation, link congestion, weak Wi-Fi, Ethernet/interface fault, DNS/DHCP failure, interoperability failure. *(Suggested — see doc 00 §6.3)* | `sample_data/scenarios` | 09 | `sample_data/` | T-SCN-01..06 | Demo-1..5 |
| R-19 | p4 §5 | Dataset "may include" metric categories, device status, wireless signal "where available", timestamps and topology. *(Not a field list — doc 06 pending)* | C-ING | 06 | `ingestion/` | T-ING-FIELDS-* | Demo-1 |
| R-20 | p3 §4 | Remediation "may simulate" corrective actions; do not modify production infrastructure without explicit authorization | C-RPT, A-REPT | 12 | `agents/reporting` (simulated actions) | T-SAFE-* | Demo-6 |

## 3. Optional capabilities and guidance (`SRC-1 p3 §4, p7 §10`)

| ID | Source | Item (PDF status) | Our decision | Component | Doc | Test | Demo |
|---|---|---|---|---|---|---|---|
| O-01 | p3 §4 | Model Context Protocol — OPTIONAL | **Not used at this stage** (CD-2) | — | 00 | — | — |
| O-02 | p3 §4 | Human-in-the-loop workflow — OPTIONAL; no approval workflow required | Adopted minimally: recommendations require recorded human approval; actions simulated | C-ORC, C-API | 04, 12 | T-HITL-* | Demo-6 |
| O-03 | p3 §4 | Persistent workflow state / pause-resume — OPTIONAL; basic message and finding logs encouraged | Message and finding logs: yes. Pause/resume: not promised | C-BUS | 04, 13 | T-LOG-* | Demo-2 |
| O-04 | p3 §4 | Interactive dashboard — OPTIONAL, ENCOURAGED; a CLI is acceptable | CLI first; React dashboard after core (CD-3) | C-API, C-DASH, CLI | 02, 14 | T-UI-* | Demo-2 |
| O-05 | p3 §4 | Automated remediation — OPTIONAL, may simulate | Simulated only, with human approval | A-REPT | 12 | T-SAFE-* | Demo-6 |
| G-01 | p3 §4 note, p7 §10 | "The central focus is reliable multi-agent interoperability and evidence-based diagnosis"; the primary innovation is agents exchanging, reconciling and explaining findings | Design guidance (`INTERPRETATION`), not a requirement | all | 02, 03 | — | Demo-2 |

## 4. Minimum acceptance criteria (`SRC-1 p6 §9`)

| ID | Criterion | Satisfied through | Test | Demo |
|---|---|---|---|---|
| M-01 | At least two collaborating agents with distinct responsibilities | R-08 | T-ORCH-COLLAB-01 | Demo-2 |
| M-02 | Structured communication between agents | R-09 | T-PROTO-* | Demo-2 |
| M-03 | Evidence from multiple agents contributes to a single diagnosis | R-08, R-11 | T-DIAG-MULTI-01 | Demo-2 |
| M-04 | At least one malformed, missing or incompatible input case is handled | R-13 | T-ERR-* | Demo-3, 4 |
| M-05 | A report with probable root cause, supporting evidence and recommended action | R-12 | T-RPT-* | Demo-2 |
| M-06 | A reproducible run using supplied or documented test data | R-14 | T-REPRO-01 | Demo-1 |

## 5. Deliverables (`SRC-1 p6 §7`)

| ID | Deliverable | Component | Doc | Planned location | Test / check | Demo |
|---|---|---|---|---|---|---|
| DLV-1 | GitHub repository: implementation, dependencies, setup instructions, test scripts | whole repo | 13 | repo root | T-REPRO-01 | — |
| DLV-2 | Architecture README: agent responsibilities, communication interfaces, orchestration, evidence correlation, error handling, workflow | docs | 02, 03, 04, 05, 08, 09 | `README.md` + `docs/` | review checklist (doc 14 §3) | — |
| DLV-3 | Sample data and test cases: normal operation and multiple fault scenarios | `sample_data/` | 09 | `sample_data/`, `tests/` | T-SCN-* | Demo-1..5 |
| DLV-4 | Demo video, 3–5 minutes: end-to-end diagnosis, inter-agent communication, final report | — | 14 | outside repo | checklist (doc 14 §2) | all |
| DLV-5 | Working prototype: CLI with optional dashboard demonstrating the complete workflow | CLI, C-API, C-DASH | 13 | `cli/`, `api/`, `dashboard/` | T-REPRO-01 | Demo-2 |

## 6. Evaluation criteria (`SRC-1 p6 §8`)

| ID | Criterion | Weight | How the design addresses it | Evidence a judge can see |
|---|---|---|---|---|
| E-01 | Agent interoperability and protocol design | 30% | Versioned message envelope, typed messages, field dictionary, normalization policy (docs 05, 06) | Message log, protocol doc, interoperability-failure scenario |
| E-02 | Diagnostic accuracy and evidence quality | 25% | Hypothesis catalog, documented heuristic score, evidence traceable to observations (doc 08) | Report evidence trail, scenario results |
| E-03 | Agent orchestration and conflict resolution | 15% | State machine, bounded clarification, written conflict rules (docs 03, 04, 08 §5) | Orchestration trace, ambiguous-case scenario |
| E-04 | Robustness to missing, inconsistent, or incompatible data | 15% | Bundle acceptance policy, not-assessable semantics, degraded operation (docs 04, 05) | Partial-metric, stale, topology-missing, agent-failure scenarios |
| E-05 | Code quality, documentation, and demonstration | 5% | Traceability, tests, README, demo script | This matrix, test report, video |
| E-06 | Innovation, usability, and extensibility | 10% | Extensions A and B, mode separation, adapter design (docs 10, 11, 15) | Demo-7, Demo-8 |

## 7. Secondary mapping to the `SRC-2` evaluation list

`SRC-2 l.47–51` lists a different rubric of unknown origin (doc 00 §6.1, decision D-01). Mapping only; **no requirement is altered.**

| `SRC-2` criterion | Weight | Where the design addresses it |
|---|---|---|
| Agentic Workflow & Autonomy | 30% | Doc 03 (agent-like behaviour, bounded clarification), doc 04 (orchestration) |
| Prototype Functionality & UX | 20% | CLI, React dashboard, map, demo (docs 11, 14) |
| Tool Interaction & Technical Implementation | 20% | Read-only tool layer (doc 02 §2, doc 03), protocol (doc 05) |
| Adaptation & Failure Recovery | 15% | Degraded operation, clarification rounds, fallbacks (docs 04, 05) |
| Evaluation, Verification & Robustness | 15% | Scenario suite, error catalog, validation plan (doc 09) |

## 8. Project rules (not official requirements)

| ID | Rule | Source | Component | Doc | Test |
|---|---|---|---|---|---|
| P-01 | Provider-independent LLM interface; core works with LLM off | SRC-3 CD-1 | C-LLM | 02, 12 | T-LLM-OFF-01 |
| P-02 | Custom deterministic state machine; no LangGraph/Kafka/MCP now | SRC-3 CD-2 | C-ORC | 04 | T-ORCH-* |
| P-03 | React + FastAPI + Leaflet, separated | SRC-3 CD-3 | C-API, C-DASH | 02, 11 | T-UI-* |
| P-04 | Web form primary; Telegram stretch; WhatsApp future | SRC-3 CD-4 | C-CSI | 10 | T-CSI-CH-* |
| P-05 | Team size and deadline stay TBD; nothing invented | SRC-3 CD-5 | — | 00 | T-DOC-02 |
| P-06 | No invented fields, units, aliases or topology | SRC-3, SRC-2 l.73 | C-ING | 06 | T-DOC-01 |
| P-07 | Numeric confidence is a heuristic score until validated | SRC-3 CD-6 | C-DIAG | 08 | T-DIAG-CAL-* |
| P-08 | Agents show agent-like behaviour, not isolated rule modules | SRC-3 CD-7 | A-* | 03 | T-AGT-BEHAV-* |
| P-09 | Official report schema preserved exactly | SRC-3 CD-8 | C-RPT | 07 | T-RPT-SCHEMA-* |
| P-10 | DNS/DHCP diagnosed only from available evidence | SRC-3 CD-9 | C-DIAG | 06, 08 | T-DNS-* |
| P-11 | Missing metric never invalidates a bundle or means healthy | SRC-3 CD-10 | C-ING | 05 | T-ERR-MISSING-* |
| P-12 | Synthetic or authorized data only; simulated items labelled | SRC-3 CD-11 | C-CFG, C-DASH | 12 | T-MODE-*, T-UI-LABEL-* |
| P-13 | Remediation simulated and subject to human approval | project rules | A-REPT | 12 | T-SAFE-*, T-HITL-* |
| P-14 | No additional agents without architectural justification | project rules | — | 02 §8, 03 | — |
| P-15 | Prefer deterministic, testable diagnosis; LLM only where appropriate | project rules | C-DIAG | 08 | T-LLM-OFF-01 |

## 9. Extensions (not official requirements)

Never counted toward the mandatory rows. Disabled → core must still pass (`T-ISO-01`).

| ID | Extension requirement | Component | Doc | Test | Demo |
|---|---|---|---|---|---|
| X-CSI-01 | Accept complaints through a web reporting interface (primary) | C-CSI | 10 | T-CSI-CH-01 | Demo-7 |
| X-CSI-02 | Telegram bot intake (stretch) | C-CSI | 10 | T-CSI-CH-02 | — |
| X-CSI-03 | WhatsApp Business intake (`FUTURE`, `NEEDS-ACCESS`; adapter interface only) | C-CSI | 10, 15 | — | — |
| X-CSI-04 | Extract location, symptoms, time, severity | C-CSI, C-LLM | 10 | T-CSI-EXT-* | Demo-7 |
| X-CSI-05 | Cluster similar complaints into candidate incidents | C-CSI | 10 | T-CSI-CLU-* | Demo-7 |
| X-CSI-06 | Forward candidate incidents to the orchestrator | C-CSI, C-ORC | 04, 10 | T-CSI-ORC-01 | Demo-7 |
| X-CSI-07 | Correlate user reports with technical telemetry | A-CORR | 08 §6 | T-CSI-COR-* | Demo-7 |
| X-CSI-08 | Distinguish user reports from verified technical faults | C-RPT, C-DASH | 07, 10 | T-CSI-LABEL-* | Demo-7, 8 |
| X-GEO-01 | Interactive campus map | C-DASH | 11 | T-GEO-* | Demo-8 |
| X-GEO-02 | Show buildings, devices, connections with verified or explicitly simulated data | C-GEO | 11 | T-GEO-PROV-* | Demo-8 |
| X-GEO-03 | Highlight reported areas separately from detected faults | C-DASH | 11 | T-GEO-LAYER-* | Demo-8 |
| X-GEO-04 | Show incident details, affected devices, probable causes | C-DASH, C-API | 11 | T-GEO-PANEL-01 | Demo-8 |
| X-GEO-05 | Dependency and blast-radius visualization | A-CONN, C-GEO | 11 | T-GEO-BLAST-* | Demo-8 |
| X-MODE-01 | Hackathon simulation mode | C-CFG, C-SRC | 00, 02 | T-MODE-01 | all |
| X-MODE-02 | Future deployment mode — design only | C-SRC | 15 | — | — |
| X-MODE-03 | Status labelling of implemented / simulated / future / needs-access items | docs, UI | 00, 12 | T-DOC-03 | — |

## 10. Implementation status (2026-10-31, after M9)

`TESTED` = implemented and covered by passing automated tests (file named). Demo evidence (video) does not exist yet, so no row is marked fully *done*.

| ID | Status | Verified by (tests) |
|---|---|---|
| R-01 probable root cause | TESTED | `tests/diagnosis/test_scoring.py`, `tests/e2e/test_scenarios.py` (S-02, S-04, S-05) |
| R-02 affected devices | TESTED | `tests/agents/test_specialists.py` (connectivity what-if), e2e `affected_devices` checks |
| R-03 supporting evidence | TESTED | `test_evidence_traces_to_observations` |
| R-04 alternatives / uncertainty | TESTED | `test_hardware_failure_profile_prefers_device_failure` (alternatives), S-09 |
| R-05 confidence + category | TESTED | `test_congestion_is_diagnosed_from_two_agents`, `test_low_data_quality_caps_confidence` |
| R-06 corrective actions | TESTED | `test_actions_adapt_to_uncertainty` |
| R-07 no exact cause when insufficient | TESTED | `test_single_weak_symptom_is_insufficient`, S-08, S-09 |
| R-08 collaborating agents | TESTED | `test_full_run` (5 agents, ≥2 evidence sources) |
| R-09 interoperability protocol | TESTED | `tests/core/test_messages.py`, `test_bus_log.py`, `schemas/protocol/`; field meanings and units: `tests/core/test_vocabulary.py`, `tests/e2e/test_vocabulary_in_runs.py` (protocol upgrade P1) |
| R-10 orchestration | TESTED | `tests/orchestrator/test_workflow.py` |
| R-11 fault diagnosis from telemetry | TESTED | e2e S-01..S-12 |
| R-12 unified report | TESTED | `test_official_keys_exact_and_typed` |
| R-13 validation / error handling | TESTED | `tests/ingestion/test_ingest.py` (E-01..E-12), S-06, S-06b, S-10 |
| R-14 reproducible testing & docs | TESTED | `test_committed_scenarios_are_reproducible`, `test_scenario_runs_are_deterministic`, doc 13 |
| R-15 structured JSON report (+ Markdown) | TESTED | `test_cli_run_and_validate` |
| R-16 documented scoring; report insufficiency | TESTED | doc 08 §11, `test_scoring.py` |
| R-17 synthetic data / simulation mode | TESTED | `test_other_modes_are_refused`, `test_live_mode_refused` |
| R-18 suggested scenarios | TESTED (S-03 as "not assessable"; S-05 via team-authored probes) | e2e |
| R-19 dataset categories | TESTED | `tests/config/test_fields.py` (T-DOC-01) |
| R-20 remediation simulated, no write path | TESTED | `test_no_state_changing_tool_exists`, `tests/orchestrator/test_review.py` (T-SAFE-02/03) |
| M-01..M-06 minimum acceptance | TESTED | `test_full_run`, protocol tests, `test_congestion_is_diagnosed_from_two_agents`, ingestion tests, report tests, CLI test |
| O-01 MCP | TESTED | `tests/mcp/test_mcp.py` (server tools/resources, agents via MCP, stdio subprocess); doc 16 |
| O-02 HITL | TESTED | `tests/orchestrator/test_review.py` (approve/reject, recorded, completes incident, CLI) |
| O-03 persistent state / pause-resume | TESTED | `tests/orchestrator/test_persistence.py` (pause/resume after restart, crash recovery, CLI) |
| O-04 dashboard | TESTED | `tests/api/test_api.py`, `tests/ui/test_dashboard_e2e.py` (Chromium), `dashboard/src/lib/lanes.test.ts`; screenshots in `docs/results/screenshots/` |
| O-05 simulated remediation | TESTED | `test_approval_is_recorded_and_outcome_simulated`, `test_simulator_has_no_write_path` |
| X-CSI-01, 04..08 | TESTED | `tests/community/` (web form, extraction, clustering, orchestrator entry, trust labels, separation from official evidence) |
| X-CSI-02 Telegram | NOT_BUILT (stretch) — channel value reserved | |
| X-CSI-03 WhatsApp | FUTURE (not built) | |
| X-GEO-02..05 (backend) | TESTED | `tests/geo/test_geo.py` |
| X-GEO-01 interactive map (UI) | TESTED | `test_map_layers` (browser) |
