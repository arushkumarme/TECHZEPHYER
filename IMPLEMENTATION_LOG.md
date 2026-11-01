# NetCoop AI — Implementation Log

Newest entry last. Each entry records actual commands and results. See `IMPLEMENTATION_PLAN.md` for the roadmap.

## M0 — Foundation · 2026-10-31 · VERIFIED

- **Objective:** toolchain, package skeleton, vendored generator, observed field dictionary.
- **Requirements:** R-14, R-17, R-19, P-06 (T-DOC-01).
- **Key finding:** the generator (`SRC-4`), previously recorded as inaccessible, downloads publicly via Drive export. Fields recorded as OBSERVED (doc 06 v0.2). It provides no topology, wireless, DNS/DHCP, memory, throughput or seed → decisions ID-04..ID-06.
- **Files:** `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `.gitattributes`, `src/netcoop/{__init__,scenarios/generator,config/fields}.py`, `config/telemetry_fields.toml`, `sample_data/generator/{organizer_generator.ipynb,PROVENANCE.md}`, `docs/06-field-dictionary.md`, tests under `tests/`.
- **Tests added:** `tests/test_smoke.py` (1), `tests/scenarios/test_generator.py` (8 incl. parametrized), `tests/config/test_fields.py` (5).
- **Executed:** `uv run pytest -q` → 15 passed. `ruff check .` → clean. `ruff format --check .` → clean. `mypy` (strict) → no issues in 5 files.
- **Gates:** G1 ✔ G2 ✔ (runner + loader public API) G3 ✔ G4 ✔ (whole suite) G5 ✔ G6 ✔ (runner executes the real vendored notebook) G7 ✔ (doc 06, PROVENANCE).
- **Remaining issues:** none new (see KNOWN_ISSUES).
- **Next:** M1 protocol models.

## M1 — Protocol models · 2026-10-31 · VERIFIED

- **Objective:** typed, versioned, validated envelope + all eight payload types; JSON Schemas.
- **Requirements:** R-09, M-02 (T-PROTO-*).
- **Files:** `src/netcoop/core/{vocab,blocks,messages,ids,schema_export}.py`, `schemas/protocol/*.schema.json` (moved to `conformance/schemas/` in protocol upgrade P6), `tests/core/{test_messages,test_ids_schema}.py`, doc 05 §10.
- **Tests added:** 31 (round trip ×8, missing envelope field ×5, missing payload field, unknown-field reporting, type/payload mismatch, naive time, `in_reply_to` ×4, version rules, unknown sender, closed enums, bad JSON, window order, ids, clock, schema freshness).
- **Executed:** `uv run pytest -q` → 46 passed. `ruff check`/`format --check` clean. `mypy --strict` clean (11 files).
- **Failures met:** schema-freshness test failed before the first export (expected red); mypy flagged a redundant cast and an untyped dict — fixed.
- **Gates:** G1–G7 ✔ (G6: models used via the real `parse_message` JSON path; bus integration follows in M2).
- **Next:** M2 message bus + SQLite log store.

## M2 — Message bus + append-only log store · 2026-10-31 · VERIFIED

- **Objective:** validated, logged, hub-and-spoke in-process transport; durable append-only log of messages and state transitions (foundation for replay and pause/resume).
- **Requirements:** R-09, O-03 (T-PROTO-BUS-*, T-LOG-*).
- **Files:** `src/netcoop/core/{bus,log_store}.py`, `tests/core/test_bus_log.py`; schema exporter now writes LF.
- **Behaviour:** every request *and* reply is serialized → `parse_message` → logged → delivered. Invalid or misrouted messages are logged with `valid=0` and an error code (`MESSAGE_INVALID`, `MESSAGE_ROUTING_INVALID`) and raised. Replies must match the request's id, parties and incident. SQLite triggers make both tables append-only.
- **Tests added:** 10. **Executed:** `uv run pytest -q` → 56 passed; ruff, format, mypy strict clean.
- **Process note:** tests were written before the code, but the red run was not observed separately (the first file write failed and was redone after the implementation existed).
- **Gates:** G1–G7 ✔ (G6: real SQLite file, reopen-persistence test).
- **Next:** M3 ingestion.

## M3 — Ingestion, validation, normalization · 2026-10-31 · VERIFIED

- **Objective:** `ingest(raw) -> IngestResult` with bundle acceptance, error taxonomy, assessability per device-item, data-quality note.
- **Requirements:** R-13, R-19, M-04, P-11, T-MODE-01.
- **Files:** `src/netcoop/ingestion/{issues,models,aliases,normalize}.py`, `src/netcoop/config/settings.py`, `config/{netcoop,aliases}.toml`, `tests/ingestion/test_ingest.py`, `tests/config/test_settings.py`, doc 05 §11.
- **Tests added:** 34 (E-01..E-12 incl. variants, no entity / no timestamp / no usable metric / live mode, probes, record traceability, real-generator bundle, a Hypothesis property test that absent/corrupt metrics are never "assessed", settings/mode refusal).
- **Executed:** red observed (collection error, module absent) → `uv run pytest -q` → 90 passed; ruff + format + mypy strict clean (19 files).
- **Failures met:** 3 long lines, 1 mypy narrowing error — fixed.
- **Gates:** G1–G7 ✔ (G6: real generator records + real config files).
- **Next:** M4 simulated topology + read-only tool layer.

## M4 — Simulated topology + read-only tool layer · 2026-10-31 · VERIFIED

- **Objective:** deterministic topology analysis (paths, neighbours, zones, what-if blast radius) and the only data-access path for agents, with permissions, budgets and call records.
- **Requirements:** R-02, R-20 (T-TOOL-*, T-SAFE-01), groundwork for X-GEO-05.
- **Files:** `sample_data/topology/{campus_v1.json,README.md}` (SIMULATED, team-authored), `src/netcoop/tools/{topology,toolbox}.py`, `tests/tools/{test_topology,test_toolbox}.py`; dev dep `types-networkx`.
- **Tests added:** 16. **Executed:** `uv run pytest -q` → 106 passed; ruff, format, mypy strict clean (22 files).
- **Failure met (real bug, caught by test):** degraded nodes were never detected because every path to the core shared one virtual sink edge (edge connectivity always 1). Fixed by a max-flow with unlimited capacity on core→sink edges. Also: lint findings, networkx stubs/generics.
- **Gates:** G1–G7 ✔ (G6: tool layer over a real ingested bundle + real topology file).
- **Next:** M5 diagnosis knowledge (catalog, scoring, gate, conflict rules).

## M5 — Diagnosis knowledge · 2026-10-31 · VERIFIED

- **Objective:** hypothesis catalog, availability matrix, severity grading, conflict rules, heuristic scoring with ceiling, decision gate, confidence category.
- **Requirements:** R-01, R-04, R-05, R-07, R-16, P-07, P-10 (T-DIAG-*, T-DNS-01/03, T-CSI-COR-01 unit level).
- **Files:** `src/netcoop/diagnosis/{params,severity,catalog,evidence,scoring}.py`, `config/diagnosis.toml`, `tests/diagnosis/test_scoring.py`; `ScoredHypothesis` gained `base`, `unexplained` (additive, schemas re-exported); doc 08 §11.
- **Tests added:** 33 (grading ×10, outcomes for normal/congestion/hardware/spike/interface/insufficient/upstream/weak-Wi-Fi/DNS ±probes/ambiguity/partial explanation, ceiling, missing agent, 3 conflict rules, community bound + 2 Hypothesis property tests, determinism).
- **Executed:** `uv run pytest -q` → 139 passed; ruff, format, mypy strict clean (28 files).
- **Process deviation:** scoring code was written before its tests in this milestone (TDD order broken). Mitigation: tests were written from doc 08's stated behaviour, and they caught 5 real design flaws (ID-11..ID-15) plus a float-rounding bug at the threshold — all fixed in code, not by relaxing tests. One test fixture (the "ambiguous" case) was replaced because the original fixture had a defensible single answer; the replacement is a true two-candidate tie.
- **Gates:** G1–G7 ✔ (G6 integration with real agents comes in M6/M7).
- **Next:** M6 specialist agents.

## M6 — Specialist agents · 2026-10-31 · VERIFIED

- **Objective:** performance, infrastructure and connectivity agents: task → budgeted tool calls → independent finding; clarification answers.
- **Requirements:** R-02, R-08, R-11, P-08 (T-AGT-*, T-AGT-BEHAV-01/02/03/04/05, T-AGT-CONN-*).
- **Skill used:** agent-workflow-designer — confirmed orchestrator + parallel fan-out + bounded evaluator loop; its scaffold generator was not used (would duplicate the typed contracts).
- **Files:** `src/netcoop/agents/*.py`, `tests/agents/{conftest,test_specialists}.py`; `TopologyInfo.zones` added; doc 03 §4.
- **Tests added:** 14, using real seeded generator records ingested through M3.
- **Executed:** red (collection error) → `uv run pytest -q` → 153 passed; ruff, format, mypy strict clean (33 files).
- **Failures met:** lint/type only (lambda default-arg inference → `functools.partial`; loop-variable closure; long lines).
- **Gates:** G1–G7 ✔ (G6: agents run on the real bus, real tool layer, real topology).
- **Next:** M7 correlation + reporting agents, report builder.

## M7 — Correlation + reporting agents, report contract · 2026-10-31 · VERIFIED

- **Objective:** stateless correlation agent with bounded clarification; reporting agent; official report + extension block; validator; Markdown.
- **Requirements:** R-03..R-06, R-12, R-15, M-05, P-09 (T-AGT-CORR-*, T-RPT-SCHEMA/EVID/ACT, doc 07 §8 rules).
- **Files:** `src/netcoop/agents/{correlation,reporting}.py`, `src/netcoop/report/{builder,validate,markdown}.py`, `tests/agents/test_correlation_reporting.py`; docs 03 §5, 07 §9, 08 ID-16.
- **Tests added:** 14 (hardware/spike/normal end-to-end through the real bus; narrow-margin clarification with a team-authored variant; round limit 0; missing specialist; official keys exact/typed; evidence traceability; actions adapt to uncertainty; forbidden wording; failure report; validator; separate issue not dropped).
- **Executed:** `uv run pytest -q` → 166 passed; ruff, format, mypy strict clean (39 files).
- **Real defects found by tests and fixed:** (1) my first clarification test only asserted an upper bound and passed with zero clarifications — replaced by a test that requires one, using a team-authored S-09 variant; (2) per-cause merge hid a separate same-cause fault on another device (ID-16); (3) report omitted unexplained anomalies on other devices → "possible separate issue" limitation; (4) clarification summaries were indistinguishable → now name device and metric.
- **Process note:** the test file was written before the implementation, but its red run was not executed separately before the code existed.
- **Observed outcomes on generator profiles (pipeline level):** `normal` → no_fault_detected; `latency_spike` → diagnosed link congestion (conf 0.66, medium); `hardware_failure` → diagnosed device/hardware failure (conf 0.95, margin 0.114 over overload/interface fault).
- **Gates:** G1–G7 ✔.
- **Next:** M8 orchestrator state machine.

## M8 — Orchestrator state machine · 2026-10-31 · VERIFIED

- **Objective:** deterministic incident workflow with parallel specialists, deadlines, retries, bounded clarification loop, degraded operation, failure reports.
- **Requirements:** R-10, M-01, M-03 (T-ORCH-*, T-ORCH-COLLAB-01, T-REPRO-02).
- **Files:** `src/netcoop/orchestrator/{states,workflow,faults}.py`; bus: `send_request`/`deliver`, deterministic reply ids; `IdFactory(namespace)`; `LogStore` incidents/reports tables; settings `[orchestration]`; doc 04 §9.
- **Tests added:** 14 (transition table, full run + collaboration, normal READY run, rejected input, missing topology, specialist timeout/error/invalid with retry, all specialists failing, correlation failure, reporting fallback, parallel = sequential determinism, incident id sequence and global message-id uniqueness, CLARIFYING bounded).
- **Executed:** red (collection error) → `uv run pytest -q` → 180 passed; ruff, format, mypy strict clean (43 files).
- **Failure met:** my test expected `READY` for a hardware-failure bundle; ingestion correctly reports `READY_WITH_WARNINGS` because the generator's hardware profile omits `jitter_ms` (METRIC_MISSING). Test corrected to assert that warning; a separate normal-run test asserts `READY`.
- **Gates:** G1–G7 ✔ (G6: full real stack — ingestion, tools, five agents, bus, SQLite).
- **Next:** M9 scenario packages, CLI, end-to-end + reproducibility.

## M9 — Scenarios, CLI, end-to-end · 2026-10-31 · VERIFIED (mandatory core complete)

- **Objective:** frozen + regenerable scenario packages S-01..S-12 (+S-06b), expected-outcome checker, CLI (`run`, `scenarios`, `trace`, `validate-report`), trace renderer, e2e and reproducibility tests, setup docs with verified commands.
- **Requirements:** R-14, R-18, M-05, M-06, DLV-3, DLV-5 (T-SCN-*, T-REPRO-01/03, T-DNS-*).
- **Files:** `src/netcoop/scenarios/{catalog,runner}.py`, `src/netcoop/cli/main.py`, `src/netcoop/orchestrator/trace.py`, `scripts/build_scenarios.py`, `sample_data/scenarios/*`, `tests/e2e/test_scenarios.py`, docs 01 §10, 09 §7, 13 v0.2, README quick start, `docs/results/`.
- **Executed:** `uv run pytest -q` → 215 passed; `uv run netcoop scenarios run-all` → 13/13 PASS (exit 0); ruff, format, mypy strict clean (48 files).
- **Defects found while checking outcomes for correctness (not just PASS):**
  1. S-12 reported `no_fault_detected` despite an unresolved conflicting critical latency reading — normal-operation scoring ignored partially-abnormal conflicts. Fixed (+ unit test) and S-12's expectation tightened (it had been too permissive).
  2. Undetermined reports listed "Normal operation" as a leading candidate although anomalies had ruled it out, and showed its missing-evidence list. Fixed: ruled-out normal operation excluded; anomalous devices named.
  3. Internal item names (`@probe_failures`) leaked into limitations. Fixed (plain-language names).
  4. Regression from an earlier blanket rename: recommendation mode `diagnostic_next_todo` instead of `diagnostic_next_steps`; the original test only checked it conditionally. Fixed and pinned by an unconditional test.
  5. Malformed agent replies without their own header were logged without an incident id and vanished from the trace. Bus now attributes them to the request they answer (+ test).
- **Gates:** G1–G7 ✔ (G6: CLI subprocess against the real stack; G7: docs 13/09/01 updated with run commands and results).
- **Next:** M10 persistent workflow state / pause-resume.

## M10 — Persistent workflow state / pause-resume · 2026-10-31 · VERIFIED

- **Objective:** official optional component 10: durable state, recovery, resumable sessions.
- **Files:** `src/netcoop/orchestrator/workflow.py` (restructured into resumable stages with checkpoints), `states.py` (`RESUMABLE`, resume self-transition), `faults.py` (`crash`, `SimulatedCrash`), `core/log_store.py` (`checkpoints` table, `max_message_seq`), `core/ids.py` (`seed`), CLI `resume`, `incidents`, `--pause-after`; `tests/orchestrator/test_persistence.py`; doc 04 §10; doc 01 O-03.
- **Tests added:** 11 (pause at 4 states + restart/resume equivalence, no re-run of completed findings, crash mid-correlation, crash mid-phase-1, non-resumable states, append-only checkpoints, unknown incident, CLI pause/list/resume).
- **Executed:** red (ImportError: `SimulatedCrash`) → `uv run pytest -q` → 226 passed; ruff, format, mypy strict clean.
- **Real defect found:** findings were checkpointed only after all three specialists replied, so a crash while waiting for the third lost the first two. Now each finding is made durable on arrival.
- **Gates:** G1–G7 ✔ (G6: a separate Orchestrator instance on the same SQLite file = restart).
- **Next:** M11 HITL review + simulated remediation.

## M11 — HITL review + simulated remediation · 2026-10-31 · VERIFIED

- **Objective:** official optional components 9 (HITL) and 12 (automated remediation, simulated).
- **Files:** `src/netcoop/orchestrator/review.py`, `src/netcoop/remediation/simulator.py`, `approvals` table in `core/log_store.py`, Markdown shows decisions/outcomes, CLI `review`/`approve`/`reject`; `tests/orchestrator/test_review.py`; docs 12 §8, 01.
- **Tests added:** 8 (pending list, approval recorded + simulated outcome, double/out-of-range/blank reviewer refused, completion → COMPLETE with versioned report and unchanged diagnosis, review only in AWAITING_REVIEW, no network during approval, simulator has no write path, CLI flow).
- **Executed:** red (collection error) → `uv run pytest -q` → 234 passed; ruff, format, mypy strict clean (51 files).
- **Failures met:** a shell heredoc quoting error aborted one write step (nothing applied); redone with file tools.
- **Gates:** G1–G7 ✔.
- **Next:** M12 MCP server.

## M12 — Model Context Protocol · 2026-10-31 · VERIFIED

- **Objective:** official optional component 8: expose diagnostic tools/telemetry/resources via MCP, and let agents use them.
- **Skill used:** mcp-builder (Python path; tool naming prefix, read-only annotations, actionable errors). SDK docs fetched with ctx7 for `mcp` 2.3.0 (v2 renamed FastMCP → `MCPServer`; in-memory `Client(server)` testing).
- **Files:** `src/netcoop/mcp/{server,adapter}.py`, `netcoop-mcp` entry point, `tool_transport` setting, `ToolBox.window`, `mcp_gateway` permission profile, `tests/mcp/test_mcp.py`, doc 16, docs 01/README.
- **Tests added:** 9 (+ updated pinned surface test). **Executed:** red (collection) → `uv run pytest -q` → 243 passed; ruff, format, mypy strict clean (54 files).
- **Defects found and fixed:**
  1. **False pass caught:** the orchestrator-over-MCP test first passed because `tool_transport` did not exist (`model_copy` skips validation) — both runs were direct. Implemented the setting and made the test assert the dispatch record says `mcp`.
  2. MCP v2 hides unexpected exceptions, so the "call netcoop_list_sources" hint never reached clients → `SourceError` now subclasses the SDK's deliberate `ToolError`.
  3. Circular import (MCP server → scenario runner → orchestrator → MCP server) → lazy import in the MCP transport branch.
  4. Agent clarification read the raw bundle window; replaced by `ToolBox.window`, which the MCP toolbox also provides.
- **Gates:** G1–G7 ✔ (G6: real stdio subprocess server; agents end-to-end through MCP).
- **Next:** M13 LLM gateway.

## M13 — LLM gateway · 2026-10-31 · VERIFIED (interface + guardrails; no real provider)

- **Objective:** CD-1 provider-independent LLM interface, null default, grounding check, template fallback; prove the diagnosis is LLM-independent.
- **Files:** `src/netcoop/llm/gateway.py`; report builder `template_narrative`; reporting agent `_reword`; orchestrator `llm=` parameter (null provider when `features.llm` is on without a provider); Markdown summary line; `tests/llm/test_gateway.py`; doc 12 §9; KI-05.
- **Tests added:** 22 (6 grounding rejections, faithful rephrase accepted, disabled/unavailable/rejected/accepted paths, T-LLM-OFF-01 official keys identical, hallucination rejected in a real run, off by default, echo-template accepted in 8 scenarios).
- **Executed:** red (collection) → `uv run pytest -q` → 265 passed; ruff, format, mypy strict clean (56 files).
- **Decision recorded:** no LLM SDK dependency added — no provider was chosen (D-07) and a provider could not be verified without credentials; documented as KI-05 rather than shipping unverified code.
- **Gates:** G1–G7 ✔.
- **Next:** M14 FastAPI backend.

## M14 — FastAPI backend · 2026-10-31 · VERIFIED

- **Objective:** API for the dashboard (component 11 server side): read-only incidents/scenarios/reports/traces/topology + run, upload, resume and review endpoints.
- **Skill used:** fastapi (Annotated deps, sync endpoints for blocking orchestrator, return types, router prefixes/tags, app factory, `[tool.fastapi]` entrypoint). FastAPI 0.162.0.
- **Files:** `src/netcoop/api/{app,models}.py`, `trace.summarize_message`, pyproject deps/entrypoint, `tests/api/test_api.py`, doc 13 §3a, doc 01.
- **Tests added:** 11 (health banner, scenarios, run + read report/strict/markdown/trace/raw message, upload + rejected bundle, review flow with 409 on repeat and 422 on blank reviewer, pause/resume, fault validation, topology/fields, 404s, CORS, no device-changing endpoint).
- **Executed:** red (collection) → `uv run pytest -q` → 276 passed; ruff, format, mypy strict clean (59 files). **Real HTTP check:** `uv run fastapi run --port 8765` + curl: health, POST run S-02 (diagnosed link congestion), strict report — all correct; server stopped via its task id.
- **Process note:** a first attempt to stop the server used a broad process kill and was (correctly) blocked by the permission classifier; redone by running the server as a tracked background task and stopping only that task.
- **Gates:** G1–G7 ✔.
- **Next:** M15 Extension A — community signal intelligence.

## M15 — Extension A: Community Signal Intelligence · 2026-10-31 · VERIFIED

- **Objective:** doc 10 pipeline: web-form intake, pseudonymization, PII stripping, screening, extraction (rules + validated optional LLM), zone resolution, distinct-reporter clustering, candidate → orchestrator via `community_candidate`, trust labels.
- **Files:** `src/netcoop/community/`, `src/netcoop/api/community.py`, `LogStore.add_tables/insert_row/rows`, orchestrator `_admit_community`, report `_community` trust labels, CLI `community`, `config/community.toml`, `sample_data/complaints/hostel_a_demo.json`, tests `tests/community/` (23), doc 10 §11, doc 01, KI-06/07.
- **Executed:** red (collection) → `uv run pytest -q` → 299 passed; ruff, format, mypy strict clean (63 files).
- **Failures met:** two shell heredoc quoting failures (no partial writes) → patches via scratch scripts; a local `import netcoop.api.community` shadowed the module-level `netcoop` name inside `create_app` → `importlib.import_module`; mypy implicit re-export.
- **Not built (recorded):** Telegram stretch channel, WhatsApp (future).
- **Gates:** G1–G7 ✔ (G6: real orchestrator, real bus message, API and CLI subprocess).
- **Next:** M16 Extension B — geospatial backend.

## M16 — Extension B: geospatial backend · 2026-10-31 · VERIFIED

- **Objective:** doc 11 map data: provenance-labelled layers, reported vs detected vs corroborated, blast radius, incident panel, API behind `features.geospatial`.
- **Decision ID-17:** schematic non-geographic layout (no verified coordinates; offline-capable).
- **Files:** `sample_data/topology/campus_v1_layout.json`, `src/netcoop/geo/layers.py`, `src/netcoop/api/geo.py`, `tests/geo/test_geo.py` (10), doc 11 §11.
- **Executed:** red (collection) → `uv run pytest -q` → 309 passed; ruff, format, mypy strict clean (66 files).
- **Test-quality fix:** replaced a tautological zone assertion with a concrete expected-zone test.
- **Gates:** G1–G7 ✔.
- **Next:** M17 React + Leaflet dashboard.

## M17 — React + Leaflet dashboard · 2026-10-31 · VERIFIED

- **Objective:** official component 11 (interactive dashboard) and the Extension B map UI.
- **Skills used:** frontend-design (token system from cabling vernacular; one bold element = agent exchange swimlane; checked against generic defaults), webapp-testing (Python Playwright, reconnaissance → selectors → assertions, screenshots for critique).
- **Files:** `dashboard/` (api client, swimlane + layout lib, incident/map/community views, styles, Vitest), backend: `NETCOOP_ENABLE` feature override, `/api/health` features, optional `app.frontend()` serving of the built UI; `tests/ui/test_dashboard_e2e.py` (7, marker `ui`), `tests/config` (+2); docs 11 §12, 13 §3b, 01; screenshots.
- **Executed:** `uv run pytest -q` → 311 passed (7 ui deselected); `uv run pytest -m ui` → 7 passed (real backend + Chromium); `npx vitest run` → 4 passed; `tsc -b` clean; ruff/format/mypy clean.
- **Found via browser + screenshots and fixed:** ambiguous accessible names in my selectors; zero-height SVG lines never "visible" (assert attachment instead); narrative repeated the headline cause (now shown only when it adds something); unlabelled map zones and small map (permanent offset labels, fractional zoom); threshold tick only explained on hover (now labelled).
- **Process note:** the swimlane layout tests were written with the code, not run red first.
- **Gates:** G1–G7 ✔.
- **Next:** M18 release verification.

## M18 — Release verification · 2026-10-31 · VERIFIED

- Clean clone of `develop` (`111627c`) → documented install → all checks of brief §11. Report: `docs/results/release-verification.md`.
- **Executed in the clean clone:** `uv sync`; `npm --prefix dashboard ci`; config load; `ruff check`, `ruff format --check`, `mypy` (66 files) clean; `uv run pytest -q` → 311 passed; `npm run build` (tsc + vite) ok; Vitest 4 passed; `uv run pytest -m ui` → 7 passed (Chromium); `netcoop scenarios run-all` → 13/13 PASS, table identical to the committed results.
- **Not done (recorded, not claimed):** demo video (DLV-4), GitHub push (needs owner authorization), real LLM provider (KI-05), Telegram channel (KI-06).
- README status, doc 14 deliverables and demo commands updated.

## Release prep for GitHub · 2026-10-31

- **Generator licence:** the organizers' notebook states no licence → owner chose *fetch, don't vendor*. `ensure_notebook()` downloads it from the PDF's public link and keeps it only if the SHA-256 matches; `scripts/fetch_generator.py`; session fixture in `tests/conftest.py`; notebook git-ignored. Live download verified byte-identical to the inspected copy. +3 tests (fetch, tampered download refused, offline error).
- **History:** owner approved filtering only that file out of local history before the first push (remote empty, no force push); original history kept locally as `backup/pre-licence-filter` (not pushed).
- **CI:** `.github/workflows/ci.yml` — backend (uv locked sync, generator fetch+cache, ruff, mypy, pytest, 13-scenario suite) and dashboard (npm ci, build, Vitest, Playwright Chromium E2E).
- **Secrets scan:** tracked files and full history — no keys, tokens, credentials or `.env`; only a deliberately fake email/phone in a PII-stripping test.
- **Executed:** ruff/format/mypy clean; `pytest -q` → 314 passed; `pytest -m ui` → 7 passed; Vitest 4 passed; scenarios 13/13, identical to committed results.

## Protocol upgrade P1 — Controlled vocabulary registry · 2026-11-01 · VERIFIED (branch feature/protocol-upgrade)

- 35 vocabularies in `config/vocabulary/*.toml` (definition, status, source, attributes per term) layered over the existing Literals; app term names kept (owner ruling). Metric terms carry category, unit, dimension from doc 06.
- `src/netcoop/core/vocabulary/` registry (`require` with suggestions, blocked terms, `x-` extensions, `VocabTerm` pydantic marker), unit registry (`convert`, `unit_fits_metric`), renderers; `scripts/generate_docs.py` (idempotent) writes doc 05 Appendix A and `conformance/vocabularies.json`.
- Drift guards: linked vocabularies equal the code's Literals; metric terms equal the field dictionary; every emitted error code registered (and none unused); ingestion severities agree; gate checks ↔ abstention reasons; scenario provenance values; report builder values; generated outputs current. Mutation check: deleting a term makes the drift and docs tests fail.
- E2E proof: `tests/e2e/test_vocabulary_in_runs.py` checks every vocabulary-controlled value of every logged message in real S-05, S-09, S-12 runs.
- Docs: doc 05 §12 + Appendix A, doc 00 D-16..D-21 (PROVISIONAL), doc 01 R-09.
- Executed: `pytest -q` 339 passed (314 + 25 new); `pytest -m ui` 7; Vitest 4; scenarios 13/13; ruff, format, mypy (70 files) clean; `generate_docs.py --check` up to date. No existing test changed.

## Protocol upgrade P2 — envelope 1.1, data snapshot, safe parsing (2026-11-01)

- Protocol 1.1: optional `snapshot_id`, `mode`, `data_provenance`, `seq`, stamped by the bus; 1.0 messages still parse; a newer minor is accepted with `PROTOCOL_MINOR_NEWER`.
- `core/snapshot.py` (canonical hash + `DataSnapshot`, checkpointed, in `netcoop_extensions.data_snapshot`), `core/parse.py` (`try_parse`, never raises; `MESSAGE_TOO_LARGE`), `core/versioning.py`, `core/clock.py` (re-export), `validate_id` in `core/ids.py`, configurable incident prefix.
- Determinism: specialist replies are now logged by the orchestrator in fixed agent order (handlers still run in parallel), so `seq` is identical in parallel and sequential runs. Late replies after a timeout are no longer logged (the timeout stays as `agent_error`).
- New error codes registered: `MESSAGE_TOO_LARGE`, `MODE_NOT_ALLOWED`, `UNKNOWN_TERM`, `PROTOCOL_MINOR_NEWER`. Decisions D-22 (incident id), D-23 (size limit).
- No existing test changed. `docs/results/example-S-02-report.json` refreshed to the current output (it also lacked the earlier `narrative` and `community_trust` keys).

## Protocol upgrade P3 — payload models and semantic rules (2026-11-01)

- New building blocks: `EntityRef`, `EvidenceRef`, `Abstention`, `IncidentContext`, `Recommendation`; strict ten-key `OfficialReport` (`report/official.py`), used by `validate_report`.
- 1.1 optional payload fields (no renames); 1.0 payloads still parse (evidence refs, `answerable`, abstention derived from the old fields, with agreement checks).
- The 7 semantic rules plus clarification/abstention rules, each a registered error code reported with its field path.
- Real agents fill the new fields: task ids/kinds/input references, not-assessable reasons, clarification and decision ids, abstention block, structured recommendations.
- Existing test changed (setup only, listed before the change): `tests/diagnosis/test_scoring.py::_obs` fixture `value=None` -> `value=1.0` (rule 1; scoring reads severity only). No assertion changed.
- Decision D-24 (recommendation priority by order).

## Protocol upgrade P4 — authority matrix and conversation guard (2026-11-01)

- Rules as data (`config/protocol/authority.toml`), describing the app's measured real flow; `core/guard/` (`ConversationGuard`, immutable `ConversationState`, `rebuild_state`); generated authority matrix + conversation rules in doc 05 §15.
- The orchestrator's bus enforces the guard on every message (check + state + seq + log under one lock); rejections are logged with code and plain-English reason and raise `GuardViolationError`.
- New codes: SENDER_NOT_AUTHORIZED, RECIPIENT_NOT_ALLOWED, MESSAGE_OUT_OF_SEQUENCE, REPLY_MISMATCH, DUPLICATE_MESSAGE, INCIDENT_CLOSED, CLARIFICATION_LIMIT_EXCEEDED, DIRECT_AGENT_MESSAGE_FORBIDDEN, EXTENSION_DISABLED; MESSAGE_ROUTING_INVALID deprecated.
- Owner decision (Conflict 16, option a): community input needs the community_signals flag. Existing tests changed (setup only, listed before the change; no assertion changed): `tests/community/test_community.py` (3 tests: corroborated, reported_unverified, detected_without_matching_complaints), `tests/community/test_community_api_cli.py` (test_demo_file_end_to_end, test_cli_community), `tests/geo/test_geo.py` (`_incident` helper used by test_reported_and_detected_layers_are_separate, test_corroborated_layer). New test: `test_community_message_is_rejected_when_the_flag_is_off`.

## Protocol upgrade P5 — message bus and append-only log (2026-11-01)

- Log rows gain attempt_seq, received_at, snapshot/mode/provenance, status, verdict, violations_json, warnings_json, payload_json, protocol_seq; automatic migration of older databases (recorded in schema_migrations, append-only).
- Store API additions: append, get_incident_messages, get_message, iter_trace, export_jsonl; no update/delete. Bus: every parse error and warning recorded (try_parse), read API get_message / messages_for, rebuild_state from the log.
- Existing tests changed (method rename only, listed in the plan): `tests/core/test_bus_log.py`, `tests/orchestrator/test_persistence.py`, `tests/orchestrator/test_review.py` now call `_execute_raw_for_tests` (was the public `execute_unsafe_for_tests`).
- Stale docs corrected: doc 02 C-BUS was `PLANNED`; doc 05 §8 said "no MCP" and `PLANNED`; doc 04 §7 said pause/resume was not promised.

## Protocol upgrade P6 — conformance kit (2026-11-01)

- `conformance/`: schemas (moved from `schemas/protocol/`, each stating its protocol version, plus `official_report`), vocabularies, 12 valid / 14 invalid messages, 7 conversations, `manifest.json`, one-page README.
- `src/netcoop/conformance/` (kit runner, deterministic builder with `--check`, `assert_agent_conforms`); CLIs `python -m netcoop.cli.conformance` / `netcoop conformance` and `python -m netcoop.cli.validate` / `netcoop validate`.
- Schema move (#22): repo-wide grep for `schemas/protocol` (CI, API, dashboard, docs, code): updated `core/schema_export.py` (single constant), docs 01 and 05; historical mentions in `docs/results/release-verification.md` and this log annotated. `tests/core/test_ids_schema.py` reads the constant: no change needed.
- Parser reasons no longer quote whole objects (short scalar inputs only); stale doc 14 statements corrected (DLV-1 pushed by the owner; test count).
- No existing test changed.

## Protocol upgrade P7 — protocol inspector (2026-11-01)

- `core/inspector/` pure renderers: table, sequence lanes, json, evidence chain (with explicit UNRESOLVED), explain (vocabulary definitions, metric units/categories), banner `SIMULATED DATA - scenario playback`, footer counts.
- CLI `python -m netcoop.cli.trace` and the same flags on `netcoop trace` (its default output is unchanged, so the existing trace tests are untouched). ANSI colour off by default.
- Golden files for the three formats from a fixture log built through the real bus (kit conversation + one rejected message); golden review caught and fixed a time-format slip and a plural. No existing test changed.

## Protocol upgrade P8 — conflict messages, protocol 1.2 (2026-11-01)

- `PROTOCOL_VERSION` 1.1 -> 1.2 (owner ruling: stay on 1.x). New message types `conflict_report` / `conflict_response`; optional `Hypothesis.relations`; `Decision.conflict_trail`. `VERSION_ADDITIONS` lets a reader pinned to 1.1 accept 1.2 messages with unknown-field warnings.
- Vocabularies `conflict_type`, `hypothesis_relation`, `conflict_status`, `conflict_stance`; codes `CONFLICT_RELATION_NOT_CONFLICTING`, `CONFLICT_TARGET_NOT_PARTY`; rationale `CONFLICTING_READINGS`.
- Authority (`authority.toml` 1.2): only `correlation_agent` raises a conflict; the orchestrator relays it to the named party; only that party responds; conflict reports share the clarification round counter. Decision D-25 (PROVISIONAL, prompt-pack default).
- Detection and resolution are unchanged: the existing unresolved-conflict re-check (S-12) is now stated as a conflict exchange. S-09 (narrow margin) correctly raises none.
- Conformance kit: 15 valid / 17 invalid / 11 conversations (real conflict; compatible disagreement raising no conflict; report from a specialist; response from a non-party). Inspector shows conflicts in table and sequence views.
- Existing tests changed (version constant only, no logic): `tests/core/test_envelope_v11.py::test_current_version_is_1_1` -> `_1_2`, `tests/orchestrator/test_stamping.py` and `tests/conformance/test_kit.py` expect "1.2". Each change is commented in place.
- Review fixes on resume: the compatible-disagreement kit conversation built a performance finding with a `compatible` relation but never sent it (it reused the default finding); now sent. Removed an unused `type: ignore` (mypy).

## Campus dashboard redesign (2026-11-01)

- Frontend only (`dashboard/`): Incidents tab is now a hero campus-artwork map with diagnosis panel, agent strip and message replay; User reports restyled to the panel system (classes only, same labels, roles and flow). Decision D-26 (PROVISIONAL) records the zone-to-building placement table; doc 11 notes the refinement of ID-17 (display only); doc 14 demo path updated; screenshots regenerated.
- Spec deviations (recorded so reviewers do not flag them): limitations and "What could not be assessed" stay expanded (a browser test reads them without a click); not-assessable devices are not drawn hollow (the popover lists their not-assessable metrics instead, so missing data is never shown as healthy); campus features ship as a typed TS module (`src/campus/features.ts`) rather than public JSON. Also: the hero map reuses the switch/building lists (spec section 10), and violet stays as a semantic colour for clarification/corroborated.
- No backend file changed: `git diff --stat ead6b40 -- src config sample_data` is empty (ead6b40 is the merge-base with `feature/protocol-upgrade`).
- No existing test changed.
