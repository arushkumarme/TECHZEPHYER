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
- **Files:** `src/netcoop/core/{vocab,blocks,messages,ids,schema_export}.py`, `schemas/protocol/*.schema.json`, `tests/core/{test_messages,test_ids_schema}.py`, doc 05 §10.
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
