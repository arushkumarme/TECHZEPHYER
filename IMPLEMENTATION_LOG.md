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
