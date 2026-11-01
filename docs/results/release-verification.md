# Release verification — 2026-10-31

> Clean-environment verification (implementation brief §11). The repository was cloned from branch `develop` (commit `111627c`) into an empty directory and checked using **only** the commands in [doc 13](../13-setup-and-operations.md). Windows 11, uv 0.11.2, Python 3.12.11 (uv-managed), Node 22, Chromium headless shell 156.
> **All data is synthetic; all remediation is simulated.** "Verified" below means an automated check was actually executed and passed — nothing more.

## 1. Results by check

| # | Check (brief §11) | How it was verified | Result |
|---|---|---|---|
| 1 | Clean installation from documented instructions | `git clone` → `uv sync` (1.9 s) → `npm --prefix dashboard ci` (3.1 s, 0 vulnerabilities) | PASS |
| 2 | Configuration and environment validation | `load_settings()` → `simulation`, all optional features off, `tool_transport=direct`; tests refuse any other mode and unknown `NETCOOP_ENABLE` names | PASS |
| 3 | Unit tests | `tests/{core,config,ingestion,tools,diagnosis,agents,scenarios}` (incl. Hypothesis property tests) | PASS |
| 4 | Contract tests | `tests/core/test_messages.py` (T-PROTO-01..10), schema freshness (`schemas/protocol/`, since moved to `conformance/schemas/`), report contract (`T-RPT-SCHEMA`) | PASS |
| 5 | Integration tests | bus + SQLite log, agents on real tool layer, orchestrator (`tests/orchestrator`), MCP (`tests/mcp`), API (`tests/api`) | PASS |
| 6 | End-to-end scenario tests | `tests/e2e` (13 scenarios, CLI subprocess) and `netcoop scenarios run-all` → **13/13 PASS** | PASS |
| 7 | Regression suite | full `uv run pytest -q` → **311 passed** (+ 7 browser tests run separately) | PASS |
| 8 | Backend API checks | `tests/api` (11, TestClient) + real uvicorn server in the browser suite; manual `curl` against `fastapi run` (M14) | PASS |
| 9 | Frontend build and functional checks | `npm run build` (TypeScript 7 type-check + Vite build), Vitest 4/4, **Chromium E2E 7/7** (`uv run pytest -m ui`) | PASS |
| 10 | Persistent state, pause/resume, recovery | `tests/orchestrator/test_persistence.py` (pause at 4 states + restart, crash during phase 1 and correlation, CLI) | PASS |
| 11 | MCP tool verification | `tests/mcp` incl. real stdio subprocess server and agents reading through MCP with identical findings | PASS |
| 12 | HITL and simulated remediation | `tests/orchestrator/test_review.py` (recorded approvals, network sockets blocked during approval, simulator has no write path) + browser review flow | PASS |
| 13 | Complaint ingestion and clustering | `tests/community` (23) + browser user-report flow | PASS |
| 14 | Geospatial and dashboard | `tests/geo` (10) + browser map test; screenshots in [`screenshots/`](screenshots/) | PASS |
| 15 | Error handling and malformed input | ingestion E-01..E-12, invalid/misrouted messages, agent timeout/error/invalid replies, rejected bundles over API/CLI, malformed complaints, malformed community input (T-ISO-02) | PASS |
| 16 | Reproducibility of the demonstration | scenario packages regenerate byte-for-byte from the vendored generator; parallel = sequential runs; clean-clone scenario table **identical** to the committed [`scenario-results.md`](scenario-results.md) | PASS |

Static checks in the clean clone: `ruff check` clean, `ruff format --check` clean, `mypy --strict` clean (66 files), `tsc -b` clean.

## 2. Test inventory (318 automated tests)

| Suite | Tests | Suite | Tests |
|---|---|---|---|
| core (protocol, bus, log) | 42 | e2e (scenarios, CLI) | 32 |
| config | 13 | mcp | 9 |
| ingestion | 28 | llm | 22 |
| tools / topology | 16 | api | 11 |
| diagnosis | 34 | community (ext. A) | 23 |
| agents | 28 | geo (ext. B) | 10 |
| orchestrator (+ persistence, review) | 33 | scenarios / generator | 9 |
| **browser UI** (Chromium) | 7 | dashboard unit (Vitest) | 4 |

## 3. Component status

| # | Official component (`SRC-1 p3 §4`) | Status |
|---|---|---|
| 1 | Multiple collaborating agents (five) | VERIFIED |
| 2 | Agent interoperability (versioned JSON protocol, schemas, field dictionary) | VERIFIED |
| 3 | Agent orchestration (deterministic state machine) | VERIFIED |
| 4 | Network fault diagnosis | VERIFIED on synthetic data (heuristic, see §4) |
| 5 | Unified diagnostic report (official keys exact) | VERIFIED |
| 6 | Basic validation and error handling | VERIFIED |
| 7 | Reproducible testing and documentation | VERIFIED (demo video not produced) |
| 8 | MCP (optional) | VERIFIED |
| 9 | Human-in-the-loop (optional) | VERIFIED |
| 10 | Persistent state / pause-resume (optional) | VERIFIED |
| 11 | Interactive dashboard (optional, encouraged) | VERIFIED |
| 12 | Automated remediation (optional) | VERIFIED as **simulation only** |
| A | Community Signal Intelligence | VERIFIED (web form; Telegram not built) |
| B | Geospatial Network Intelligence | VERIFIED (schematic map) |

## 4. Not verified / known limitations (honest list)

- **Diagnostic accuracy on real networks is unknown.** Thresholds were set from the organizer generator's own ranges and tested on scenarios built from it (circularity, KI-04). Confidence is a documented heuristic, not calibrated.
- **Weak Wi-Fi is never diagnosed** — the generator has no wireless signal. **DNS/DHCP** is diagnosed only from team-authored probe data.
- **No real LLM provider** is configured (KI-05); LLM paths are tested with null/static providers.
- **Telegram intake not built**; WhatsApp is future scope (KI-06).
- **Demo video (DLV-4) not produced**; a GitHub remote has not been created or pushed to (requires the owner's authorization).
- Live-submitted complaints use wall-clock time while scenarios replay fixed 2026-10-31 telemetry (KI-07).
- Team members, roles and deadline remain TBD; nothing was invented.
