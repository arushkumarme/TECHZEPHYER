# 13 — Setup and Operations

> Version 0.2 · 2026-10-31 · Commands below were **actually run** on Windows 11 (Git Bash / PowerShell) with the versions listed. Sections marked `TBD` are not implemented yet.

## 1. Prerequisites (tested)

| Tool | Version tested | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.11.2 | Installs Python and dependencies from `uv.lock` |
| Python | 3.12.11 (installed by uv; `.python-version` pins 3.12) | `requires-python = ">=3.12,<3.13"` |
| Node.js | 22.x | Only for the dashboard (M17, `TBD`) |

No internet connection is needed to run the core once dependencies are installed. Nothing connects to any real network.

## 2. Install

```bash
uv sync                                   # creates .venv and installs the locked dependencies
uv run python scripts/fetch_generator.py  # one-time: download + verify the organizers' generator
```

The organizers' generator notebook has no stated licence, so it is **not** in the repository. It is downloaded from the public link in the hackathon PDF and kept only if its SHA-256 matches the inspected copy (tests also fetch it automatically). The committed scenario inputs in `sample_data/scenarios/` work without it; only regeneration and generator tests need it.

## 3. Run the core (CLI)

```bash
uv run netcoop scenarios list                         # the 13 frozen scenario packages
uv run netcoop run --scenario S-02 --trace            # one diagnosis: report on stdout, trace on stderr
uv run netcoop run path/to/bundle.json --json-out report.json --md-out report.md
uv run netcoop run --scenario S-02 --strict           # only the ten official report keys
uv run netcoop run --scenario S-02 --inject-fault performance_agent:timeout   # degraded run
uv run netcoop scenarios run-all --report scenario-results.md                 # whole suite
uv run netcoop trace INC-0001                         # replay a stored incident's trace
uv run netcoop validate-report report.json            # check a report against doc 07 §8
```

- Exit codes: `0` success; `1` a scenario expectation failed (run-all) or a report is invalid; `2` the input was rejected (`status: failed`).
- Every run prints `SIMULATED DATA - scenario playback` on stderr.
- State lives in `var/netcoop.sqlite3` (git-ignored); use `--db PATH` for another file.

## 3a. Backend API (FastAPI) and MCP server

```bash
uv run fastapi dev                     # http://127.0.0.1:8000, docs at /docs (entrypoint in pyproject)
uv run fastapi run --port 8765         # production-style server (verified 2026-10-31 with curl)
NETCOOP_DB=path/to.sqlite3 uv run fastapi run   # choose the log database
uv run netcoop-mcp                     # MCP server over stdio (doc 16)
```

Endpoints (all under `/api`): `GET health`, `GET scenarios`, `GET scenarios/{id}`, `POST scenarios/{id}/run` (`{"fault_injection": {...}, "pause_after": STATE}`), `GET incidents`, `POST incidents` (raw bundle), `GET incidents/{id}`, `GET incidents/{id}/report[?strict=true]`, `GET incidents/{id}/report.md`, `GET incidents/{id}/trace`, `GET incidents/{id}/messages/{message_id}`, `POST incidents/{id}/resume`, `GET incidents/{id}/review`, `POST incidents/{id}/review/{index}` (`{"decision": "approve|reject", "reviewer": "...", "note": "..."}`), `GET topology/{id}`, `GET field-dictionary`. CORS allows the Vite dev server (`localhost:5173`). No endpoint can change a network device (test `test_no_device_changing_endpoint`).

## 3b. Dashboard (React + Vite + Leaflet, separate app — CD-3)

```bash
npm --prefix dashboard install          # Node 22 tested
npm --prefix dashboard run build        # type-check (TypeScript 7) + production build -> dashboard/dist
npm --prefix dashboard test             # Vitest unit tests

# Development: two processes; Vite proxies /api to the backend
NETCOOP_ENABLE=community_signals,geospatial uv run fastapi dev      # backend :8000
npm --prefix dashboard run dev                                       # UI :5173

# Demo / E2E: one process serving the built UI
NETCOOP_ENABLE=community_signals,geospatial NETCOOP_DASHBOARD_DIST=dashboard/dist uv run fastapi run
```

`NETCOOP_ENABLE` switches optional features on without editing `config/netcoop.toml` (unknown names are refused). Fonts are bundled (no internet needed). Browser tests: `uv run playwright install chromium` once, then `uv run pytest -m ui` (excluded from the default run).

## 4. Configuration (`config/`)

| File | Content |
|---|---|
| `netcoop.toml` | `mode = "simulation"` (anything else is refused); feature flags (community, geospatial, LLM — all off); ingestion and orchestration limits |
| `telemetry_fields.toml` | Field dictionary observed in the organizer generator (doc 06) |
| `aliases.toml` | Team-authored aliases and unit rules for incompatible variants |
| `diagnosis.toml` | Thresholds, weights and gate parameters (doc 08 §11) — all heuristic |

Environment variables are reserved for secrets (none are needed today).

## 5. Tests and quality checks

```bash
uv run pytest -q                 # unit, contract, integration, e2e (scenarios + CLI)
uv run pytest -q -m e2e          # end-to-end only
uv run ruff check . && uv run ruff format --check .
uv run mypy                      # strict
uv run python scripts/build_scenarios.py   # regenerate scenario packages (byte-identical)
uv run python -m netcoop.core.schema_export   # regenerate protocol JSON Schemas
```

## 5a. Continuous integration

`.github/workflows/ci.yml` (GitHub Actions, `ubuntu-latest`, no secrets): job **backend** — `uv sync --locked`, fetch + verify generator (cached by hash), `ruff check`, `ruff format --check`, `mypy`, `pytest -q`, `netcoop scenarios run-all` (results uploaded as an artifact); job **dashboard** — Node 22 `npm ci`, `npm run build` (type-check), Vitest, Playwright Chromium, `pytest -m ui` (screenshots uploaded). Triggers: pushes to `develop`/`main`, pull requests, manual.

## 6. Outputs

- JSON report (extended, or `--strict` official-only) and Markdown report per incident; also stored in the SQLite `reports` table.
- Append-only `messages`, `transitions`, `incidents`, `reports` tables (database triggers forbid UPDATE/DELETE).
- Example artefacts from a real run: [`docs/results/`](results/).

## 7. Reproducibility

- Scenario inputs are frozen in `sample_data/scenarios/` **and** regenerable byte-for-byte from the vendored generator with fixed seeds (test `test_committed_scenarios_are_reproducible`).
- Dependencies are pinned in `uv.lock`.
- Runs are deterministic: same input and configuration give the same states, decision, scores and report (apart from `generated_at`), in parallel or sequential mode.

## 8. Troubleshooting (from problems actually met)

- **`ruff` flags the generator notebook** — it is excluded on purpose (`extend-exclude`); the organizer's code is never edited.
- **`GeneratorUnavailable`** — no internet on first run: run `scripts/fetch_generator.py` once with access, or copy the notebook into `sample_data/generator/`.
- **Python 3.15 on the machine** — uv uses the pinned 3.12; do not run with a system Python outside the venv.
