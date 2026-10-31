# M0 Foundation Implementation Plan

> **For agentic workers:** executed natively (owner asked for autonomous execution). Steps use checkbox syntax.

**Goal:** A runnable, tested Python package skeleton with the organizer's generator vendored verbatim, a seeded generator runner, and a machine-readable field dictionary whose every entry cites an observed source.

**Architecture:** `uv`-managed Python 3.12 project, `src/netcoop` layout. Configuration in TOML (`tomllib`, stdlib). The generator notebook is stored unchanged; a runner extracts its code cell, verifies its SHA-256, and executes it with a seeded `random.Random` and a fixed clock so scenario inputs can be regenerated deterministically.

**Tech Stack:** Python 3.12, pydantic 2, networkx, pytest, hypothesis, ruff, mypy.

**Spec:** `docs/06-field-dictionary.md`, `docs/13-setup-and-operations.md`, `IMPLEMENTATION_PLAN.md` (ID-02, ID-03, ID-08).

## Global Constraints
- No telemetry field, unit or range without a citation to the generator (P-06, T-DOC-01).
- Generator code is never edited; any change in hash fails the test.
- Nothing requires internet at test time.

## Review Focus
- Notebook replaced by a different version → runner must refuse (hash mismatch), not silently run.
- Unknown `fault_type` → the generator itself falls back to "normal"; runner must record the requested and effective profile honestly.
- Config file with a field missing its `source` → T-DOC-01 fails.

### Task 1: Toolchain and package skeleton
**Files:** `pyproject.toml`, `src/netcoop/__init__.py`, `tests/test_smoke.py`
- [ ] Test `test_package_version` asserts `netcoop.__version__ == "0.1.0"`.
- [ ] `uv sync`, run pytest (fail → pass), ruff, mypy.

### Task 2: Vendored generator + seeded runner
**Files:** `sample_data/generator/organizer_generator.ipynb`, `sample_data/generator/PROVENANCE.md`, `src/netcoop/scenarios/generator.py`, `tests/scenarios/test_generator.py`
**Produces:** `load_generator(path: Path = DEFAULT_NOTEBOOK) -> GeneratorHandle`; `GeneratorHandle.generate(fault_type: str, *, seed: int, at: datetime) -> dict`; `EXPECTED_SHA256: str`; `FAULT_TYPES = ("normal", "latency_spike", "hardware_failure")`; `GeneratorIntegrityError`.
- [ ] Tests: hash mismatch raises `GeneratorIntegrityError`; same seed → identical record; record keys are exactly `{"timestamp","device_id","metrics","status"}`; `hardware_failure` record has `interface_errors` and no `jitter_ms`; `normal` status is `"Healthy"`; timestamp equals `at` in ISO + `Z`.

### Task 3: Field dictionary config + doc 06
**Files:** `config/telemetry_fields.toml`, `src/netcoop/config/fields.py`, `tests/config/test_fields.py`, `docs/06-field-dictionary.md`
**Produces:** `load_field_dictionary(path) -> FieldDictionary` with `.fields: dict[str, FieldSpec]` (`name, category, unit, type, observed_range, present_in: list[str], source`).
- [ ] T-DOC-01: every field has non-empty `source`; every field name appears verbatim in the vendored notebook source.
- [ ] Every metric emitted by the runner across all three fault types is in the dictionary (and vice versa).
