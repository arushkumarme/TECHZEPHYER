# 02 — System Architecture

> Version 0.1 · 2026-10-31 · Draft for review · Everything here is `PROPOSAL` unless tagged `CONFIRMED` (see [doc 00 §2](00-scope-and-decisions.md))

## 1. Design principles

1. **The problem statement drives the design.** `SRC-1 p3 §4` says the central focus is reliable multi-agent interoperability and evidence-based diagnosis. Features that do not serve that come after the core. `CONFIRMED`
2. **Agents only where judgement and adaptive investigation help; ordinary software everywhere else.** Validation, normalization, orchestration, graph traversal and report assembly are deterministic code.
3. **Diagnosis is deterministic and testable.** An LLM may help with wording and complaint-text extraction, never with the diagnosis or the confidence number. `CONFIRMED` (CD-1)
4. **Missing data is never healthy data.** Every layer carries "not assessable" forward instead of guessing. `CONFIRMED` (CD-10)
5. **Everything agents say to each other is a logged, validated message.** That log is the proof of interoperability.
6. **Honest labelling.** Simulated things are labelled simulated, everywhere.

## 2. Components

| ID | Component | Kind | Responsibility | Scope |
|---|---|---|---|---|
| C-CFG | Configuration and mode | Deterministic | Selects mode, thresholds, field aliases, unit rules, scoring parameters, feature flags | `PLANNED` |
| C-SRC | Telemetry source adapter | Deterministic | Reads telemetry into the ingestion stage. `sim_source` reads generator output; a live adapter is not built | `sim_source`: `PLANNED`/`SIMULATED`; live: `FUTURE`/`NEEDS-ACCESS` |
| C-ING | Ingestion, validation, normalization | Deterministic | Structure check, schema-version check, field mapping, unit conversion, plausibility, data-quality note, bundle acceptance (doc 05 §6) | `PLANNED` |
| C-TOOL | Read-only tool layer | Deterministic | The only way agents read data: telemetry query, coverage query, topology neighbours/path, what-if failure, data-quality report. No write operations exist | `PLANNED` |
| C-BUS | Message bus and log store | Deterministic | Routes JSON messages; validates each (envelope, payload rules, conversation guard); appends **every attempt, accepted or rejected**, to an append-only SQLite log with verdict, plain-English violations, warnings, snapshot id and per-incident sequence; read API by message id; replay of the conversation state from the log (doc 05 §16) | `IMPLEMENTED` |
| C-ORC | Orchestrator | Deterministic state machine | Creates incidents, assigns tasks, enforces timeouts and clarification limits, collects findings, drives the workflow (doc 04) | `PLANNED` |
| A-PERF | Telemetry & Performance Agent (`performance_agent`) | Agent | Performance behaviour: latency, jitter, loss, throughput, bandwidth, utilization, wireless signal if present | `PLANNED` |
| A-INFRA | Infrastructure Health Agent (`infrastructure_agent`) | Agent | Device status, CPU, memory, interface errors, queue drops | `PLANNED` |
| A-CONN | Connectivity Analysis Agent (`connectivity_agent`) | Agent | Topology, affected devices and segments, scope, blast radius, what-if answers | `PLANNED` |
| A-CORR | Fault Correlation Agent (`correlation_agent`) | Agent | Combines findings, scores competing hypotheses, resolves conflicts, asks clarifications, decides diagnosed / insufficient | `PLANNED` |
| A-REPT | Recommendation & Reporting Agent (`reporting_agent`) | Agent | Builds the report, evidence trail, limitations, recommendations (simulated, approval-gated) | `PLANNED` |
| C-DIAG | Diagnosis knowledge | Deterministic | Hypothesis catalog, scoring, decision gate, conflict rules — used by the agents (doc 08) | `PLANNED` |
| C-RPT | Report builder and schemas | Deterministic | Official report + additive extension block, Markdown rendering, schema validation | `PLANNED` |
| C-LLM | LLM gateway | Optional | Provider-independent interface; a null provider is the default | Interface `PLANNED`; providers TBD (D-07) |
| C-API | Backend API | Deterministic | FastAPI: read-only incident/topology/community/map resources, complaint submission, approval recording | `PLANNED` (after core) |
| C-DASH | Dashboard | UI | React + Leaflet: incidents, message log, report, map | `PLANNED` (after core) |
| C-CSI | Community Signal Intelligence | Mostly deterministic | Intake adapters, pseudonymization, extraction, location resolution, clustering (doc 10) | `PLANNED` (extension) |
| C-GEO | Geospatial Network Intelligence (backend) | Deterministic | Campus layers, provenance labels, blast-radius presentation data (doc 11) | `PLANNED` (extension) |

**Why only five agents and no sixth.** The validator, orchestrator, community pipeline and map are fixed procedures where identical input must give identical output; making them "agents" would add unpredictability and no capability (rule P-14). The community module feeds evidence to the existing Correlation and Connectivity agents. `PROPOSAL`

## 3. Data flow

1. **Source → ingestion.** C-SRC reads telemetry; C-ING validates, normalizes and produces a *normalized bundle* plus a data-quality note, or a rejection with a specific error.
2. **Orchestrator creates the incident** and sends task messages through C-BUS.
3. **Specialist agents** (A-PERF, A-INFRA, A-CONN) work in parallel. They read data only through C-TOOL, decide what to examine, and reply with findings.
4. **A-CORR** receives all findings, scores hypotheses via C-DIAG, and may ask bounded clarification questions (routed by the orchestrator).
5. **Decision gate** → `diagnosed` or `insufficient_evidence` (doc 08).
6. **A-REPT** builds the report; C-RPT validates it.
7. **Human review gate** — recommendations are marked as needing approval; any approval is recorded and the action stays simulated.
8. **Outputs:** JSON report, Markdown report, CLI view; with the extensions on, API/dashboard/map.

Extension input joins at step 1 as an additional *candidate incident* message (doc 10); extension output reads reports at step 8 (doc 11).

## 4. Technology stack

| Layer | Choice | Status | Why |
|---|---|---|---|
| Orchestration | Custom deterministic state machine | `CONFIRMED` (CD-2) | Protocol and orchestration are directly scored; frameworks hide the messaging we need to show |
| LLM access | Provider-independent interface, null provider by default | `CONFIRMED` (CD-1) | Core must run without an LLM; provider is undecided (D-07) |
| Backend API | FastAPI | `CONFIRMED` (CD-3) | Separate from the frontend |
| Frontend | React | `CONFIRMED` (CD-3) | Separate from the backend; build tooling TBD |
| Map | Leaflet | `CONFIRMED` (CD-3) | Tile source and offline fallback TBD (D-08) |
| Language | Python for the backend | `PROPOSAL` | Implied by FastAPI |
| Message and report models | Pydantic | `PROPOSAL` | Models validate data and can export formal JSON Schemas later |
| Storage | SQLite for message log, incidents, complaints | `PROPOSAL` | File-based, no server, easy to inspect |
| Graph analysis | `networkx` | `PROPOSAL` | Deterministic traversal for blast radius and what-if |
| Testing | `pytest`, golden scenario files | `PROPOSAL` | Makes "reproducible" literal |
| Telegram | Bot API client | `PROPOSAL` (stretch) | Optional channel |
| **Not used now** | LangGraph, Kafka, MCP | `CONFIRMED` (CD-2) | — |

Versions of Python, Node and packages are deliberately left open (D-14).

## 5. Operating-mode switch

Only the **source adapter** and a few labels differ between modes.

| | Simulation mode | Deployment mode |
|---|---|---|
| Source adapter | `sim_source` reads generator output — `PLANNED` | Live collector adapters — `FUTURE`, `NEEDS-ACCESS` |
| Topology | Simulated file, labelled — `SIMULATED` | Verified inventory — `FUTURE`, `NEEDS-ACCESS` |
| Report provenance | `data_provenance` = synthetic | Set by adapter |
| UI banner | "Simulated data — scenario playback" | Removed only when feeds are real |
| Remediation | Simulated | Out of scope (doc 15) |

The report and every message state their mode; an unrecognized mode is refused, never defaulted to "live".

## 6. Extension isolation

- Extensions sit in `community/` and `geo/`, behind flags in C-CFG.
- They communicate only through the same message envelope (a `community_candidate` message in; reports read out).
- Core code never imports extension code.
- `T-ISO-01`: the full core suite passes with both flags off. `T-ISO-02`: an extension failure leaves a core run unchanged.

## 7. Planned repository layout

```
netcoop-ai/
├── README.md
├── docs/                    # the 16 files in this set
├── config/                  # mode, thresholds, aliases, unit rules, scoring parameters, gazetteer
├── sample_data/
│   ├── scenarios/           # one folder per scenario: input, metadata, expected outcome
│   ├── complaints/          # synthetic complaint sets (labelled synthetic)
│   └── topology/            # simulated topology and campus layers (labelled)
├── src/netcoop/
│   ├── core/                # messages (envelope, payloads), IDs, errors, log_store
│   │   └── vocabulary/      # controlled-vocabulary registry over the term Literals
│   ├── ingestion/           # sim_source, validate, normalize, data_quality
│   ├── tools/               # read-only tools: telemetry, topology
│   ├── agents/              # performance, infrastructure, connectivity, correlation, reporting
│   ├── diagnosis/           # catalog, scoring, gate, conflict rules
│   ├── orchestrator/        # workflow (state machine), review
│   ├── report/              # official + extended builders, markdown renderer
│   ├── llm/                 # provider interface, null provider, optional adapters
│   ├── community/           # Extension A
│   ├── geo/                 # Extension B backend
│   ├── api/                 # FastAPI
│   └── cli/
├── dashboard/               # React + Leaflet
├── conformance/             # protocol conformance kit: schemas, examples, manifest
├── scripts/
└── tests/
```

## 8. Decisions and alternatives considered

| Decision | Chosen | Alternatives | Reason |
|---|---|---|---|
| Orchestrator | Custom state machine | LangGraph or similar; free-form LLM planner | Confirmed by owner; deterministic, testable, shows the protocol |
| Agent-to-agent transport | In-process, every message serialized to JSON and validated on every hop | Separate processes over REST; message broker | Real protocol without operational cost. REST/broker not planned; the envelope would carry over unchanged |
| Agents read data | Through a read-only tool layer | Direct file access | Tool calls are logged and budgeted; supports agent-like behaviour (doc 03) and a clean mode switch |
| Diagnosis logic | Deterministic catalog + scoring | LLM judges the cause | Reproducibility, testability, no hallucinated evidence |
| Confidence | Heuristic score, parameters in config | Calibrated model | No ground-truth data yet; calibration claimed only after validation (doc 08 §9) |
| Storage | SQLite | Postgres; plain files | Zero setup; adequate for a prototype |
| Number of agents | Five | Two minimum; more | Matches `SRC-1` suggested roles; each has a distinct data view and task. Extra agents unjustified |
