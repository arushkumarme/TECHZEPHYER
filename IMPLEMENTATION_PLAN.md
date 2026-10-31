# NetCoop AI — Implementation Plan (milestone roadmap)

> Living document. Started 2026-10-31. Progress per milestone is in [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md); open problems in [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).
> Detailed task plans per milestone: `docs/superpowers/plans/`.
> Status values: `NOT_STARTED` · `IN_PROGRESS` · `BLOCKED` · `IMPLEMENTED` · `TESTED` · `VERIFIED`.
> A milestone is `VERIFIED` only when all seven quality gates (below) have recorded evidence in the log.

## 1. Method

Iterative and incremental, test-driven. For each milestone: understand → acceptance criteria → tests → implement → verify → fix → integrate → document. Local git commit at every completed milestone on branch `develop` (never pushed without authorization).

**Quality gates per milestone:** G1 requirements · G2 functionality via public interface · G3 automated tests · G4 regression (full suite) · G5 code quality (`ruff check`, `ruff format --check`, `mypy`) · G6 integration with real dependencies · G7 documentation.

## 2. Scope (official component table, `SRC-1 p3 §4`) + extensions

| # | Component | PDF status | Milestones |
|---|---|---|---|
| 1 | Multiple collaborating agents | MANDATORY | M6, M7 |
| 2 | Agent interoperability | MANDATORY | M1, M2, M3 |
| 3 | Agent orchestration | MANDATORY | M8 |
| 4 | Network fault diagnosis | MANDATORY | M5, M6, M7 |
| 5 | Unified diagnostic report | MANDATORY | M7 |
| 6 | Basic validation and error handling | MANDATORY | M3, M8 |
| 7 | Reproducible testing and documentation | MANDATORY | M0, M9, M18 |
| 8 | Model Context Protocol (MCP) | OPTIONAL | M12 |
| 9 | Human-in-the-loop workflow | OPTIONAL | M11 |
| 10 | Persistent workflow state / pause-resume | OPTIONAL | M2, M10 |
| 11 | Interactive dashboard | OPTIONAL, ENCOURAGED | M14, M17 |
| 12 | Automated remediation (simulated) | OPTIONAL | M11 |
| A | Community Signal Intelligence | project extension | M15 |
| B | Geospatial Network Intelligence | project extension | M16, M17 |

## 3. Implementation decisions (ID-xx)

These refine the design docs; each is mirrored into the relevant doc when its milestone lands.

| ID | Decision | Reason |
|---|---|---|
| ID-01 | **Scope change from owner (2026-10-31):** all 12 components are built, including MCP (M12) and pause/resume (M10). Supersedes doc 00 CD-2 "no MCP" and doc 04 §7 "pause/resume not promised". The in-process bus stays the agent transport; MCP is an *additional* read-only tool/resource interface | Owner instruction in implementation brief |
| ID-02 | Generator obtained 2026-10-31 via public Drive export of the Colab link in `SRC-1 p4 §5`; vendored verbatim with SHA-256 under `sample_data/generator/`. Field dictionary (doc 06) filled from it as `OBSERVED` | Unblocks D-02 |
| ID-03 | Generator emits **single records**; a *telemetry bundle* is a JSON document `{"records": [...], "topology_ref"?, "schema_version"?}` or a bare JSON array of generator records. Wrapper keys are a team-defined container (`PROPOSAL`), record fields are the generator's | Generator has no multi-record format |
| ID-04 | Topology, zones and campus layout are **team-authored synthetic** (`SIMULATED`), covering the generator's device IDs `SW_CAMPUS_1..10` | Generator provides no topology (D-09) |
| ID-05 | Severity thresholds derived from the generator's own value ranges (normal-profile upper bounds), recorded in `config/` with citation. Circularity risk (doc 08 §8) stated in docs and mitigated with team-authored variants | Doc 08 §2 says thresholds come from inspected data |
| ID-06 | Weak Wi-Fi: generator has no wireless signal → cause type marked *not diagnosable*; never output (test). DNS/DHCP: implement the optional, separately labelled **probe input** (doc 08 §3.3) with team-authored probe data; never diagnosed from generator telemetry alone | CD-9, D-11 default |
| ID-07 | Report status values: `diagnosed`, `insufficient_evidence`, `no_fault_detected`, `failed`; `supporting_evidence[].value` number or string; extension block `netcoop_extensions` | D-03/D-04/D-05 defaults |
| ID-08 | Python 3.12 (uv-managed), `uv` for env/lock; Pydantic v2; SQLite (stdlib `sqlite3`); `networkx`; `pytest`, `hypothesis` (property tests), `ruff`, `mypy`. Node 22 + Vite + React + Leaflet for the dashboard | D-14 |
| ID-09 | Phase-1 specialists run in a thread pool with per-agent deadlines; results are always processed in fixed agent order, so the log is deterministic | Doc 04 §4 |
| ID-11..15 | Scoring refinements found by tests: unexplained-anomaly penalty, margin on pre-ceiling base, key-evidence requirement, strict no-fault rule, community excluded from ranking/gate — doc 08 §11 | Each fixed a failing test that exposed a real flaw |
| ID-10 | LLM gateway: null provider default; any real provider is optional and off; no external account required for any test | CD-1, D-07 |

## 4. Milestones

| M | Objective | Requirements | Key tests | Status |
|---|---|---|---|---|
| M0 | Foundation: repo, toolchain, package skeleton, vendored generator, field dictionary from OBSERVED data, config scaffold | R-14, R-17, R-19, P-06 | T-DOC-01, generator-vendoring test | VERIFIED |
| M1 | Protocol models: envelope, payload building blocks, all message types, version rules, JSON Schema export | R-09, M-02 | T-PROTO-* (contract) | VERIFIED |
| M2 | Message bus + append-only SQLite log store (messages, state transitions), replay reader | R-09, O-03 | T-PROTO-BUS-*, T-LOG-* | VERIFIED |
| M3 | Ingestion: sim_source, parse, structure, field mapping/aliases, units, timestamps, plausibility, dedupe, data-quality note, bundle acceptance, error taxonomy | R-13, R-19, M-04, P-11 | T-ING-*, T-ERR-01..13 | VERIFIED |
| M4 | Simulated topology + read-only tool layer (telemetry query, coverage, neighbours/path, what-if, data-quality) with call budget + records | R-02, R-20 | T-TOOL-*, T-SAFE-01 | VERIFIED |
| M5 | Diagnosis knowledge: hypothesis catalog, evidence availability matrix, scoring, ceiling, margin, decision gate, conflict rules | R-01, R-04, R-05, R-07, R-16 | T-DIAG-*, property tests | VERIFIED |
| M6 | Specialist agents: performance, infrastructure, connectivity (task → tool calls → finding) | R-02, R-08, R-11, P-08 | T-AGT-*, T-AGT-BEHAV-* | VERIFIED |
| M7 | Correlation agent (incl. clarification requests) + reporting agent; report builder, schema validation, Markdown | R-03..R-06, R-12, R-15, P-09 | T-AGT-CORR-*, T-RPT-* | VERIFIED |
| M8 | Orchestrator state machine: dispatch, collect, deadlines/retries, clarification loop, degraded operation, failure reports | R-10, M-01, M-03 | T-ORCH-*, T-ORCH-COLLAB-* | VERIFIED |
| M9 | Scenario packages S-01..S-12 (generator + team-authored variants, labelled), CLI, end-to-end + reproducibility | R-14, R-18, M-05, M-06, DLV-3, DLV-5 | T-SCN-*, T-REPRO-*, T-DNS-* | NOT_STARTED |
| M10 | Persistent workflow state: checkpoint per transition, pause at review, resume after restart, crash recovery | Component 10 | T-PERSIST-* | NOT_STARTED |
| M11 | HITL review + simulated remediation: approvals recorded, simulated outcomes, no write path | O-02, O-05, R-20 | T-HITL-*, T-SAFE-* | NOT_STARTED |
| M12 | MCP server exposing read-only diagnostic tools + resources; MCP-backed tool adapter usable by agents | O-01 / component 8 | T-MCP-* | NOT_STARTED |
| M13 | LLM gateway: provider interface, null provider, grounding check, template fallback | P-01, P-15 | T-LLM-OFF-01, T-LLM-GROUND-* | NOT_STARTED |
| M14 | FastAPI backend: incidents, runs, trace, reports, topology, approvals, scenarios | O-04, P-03 | T-API-* | NOT_STARTED |
| M15 | Extension A — community signals: intake, pseudonymize, screen, extract, gazetteer, cluster, candidate → orchestrator, trust labels | X-CSI-01..08 | T-CSI-*, T-ISO-* | NOT_STARTED |
| M16 | Extension B — geo backend: campus layers with provenance, blast radius isolated/degraded/unknown, map API | X-GEO-01..05 | T-GEO-* | NOT_STARTED |
| M17 | React + Leaflet dashboard: incidents, trace, report, approvals, complaint form, map layers, banner | O-04, X-GEO-*, X-CSI-08 | T-UI-*, Playwright E2E | NOT_STARTED |
| M18 | Release verification: clean install, all suites, demo reproducibility, docs + traceability final | §11 of brief | T-REPRO-01, full checklist | NOT_STARTED |

Dependency order: M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → (M10, M11, M12, M13 in that order) → M14 → M15 → M16 → M17 → M18.

## 5. Resume protocol

1. Read this file, `IMPLEMENTATION_LOG.md` (last entry = where work stopped), `KNOWN_ISSUES.md`.
2. `git log --oneline -20` and `git status`.
3. `uv run pytest -q` to confirm the last verified state.
4. Continue with the first milestone whose status is not `VERIFIED`.
