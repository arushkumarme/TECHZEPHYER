# 13 — Setup and Operations

> Version 0.1 · 2026-10-31 · **SKELETON.** Nothing is implemented, so there are no verified commands. This file records the contract the real instructions must meet (`R-14`, `DLV-1`, `DLV-5`); commands and versions are added only after they have been run.

## 1. Setup contract

A reviewer with a fresh checkout must be able to, following only this file:

1. install the backend and (for the dashboard) the frontend dependencies;
2. run the core on a bundled scenario from the command line;
3. see the JSON report, the Markdown report and the message trace;
4. run the full test suite;
5. optionally enable the LLM, the dashboard, and the extensions — each off by default.

## 2. Prerequisites — `TBD`

Python and Node versions, package manager and operating-system notes are decided at implementation (D-14) and listed here with the versions actually tested. No internet connection is required for the core run.

## 3. Configuration

Configuration lives in `config/` (doc 02 §7). It will contain, as separate files or sections:

- operating mode (only `simulation` is accepted; unknown values are refused);
- feature flags: extensions A and B, LLM, dashboard;
- field aliases and unit rules (empty until the generator is inspected; entries cite their source);
- thresholds and baselines; scoring parameters (doc 08 §10);
- orchestration limits: timeouts, retries, clarification rounds, tool budgets;
- gazetteer and zone mapping (synthetic).

Environment variables are used only for secrets (e.g. an LLM provider key). **The LLM is disabled by default.**

## 4. Run modes — commands `TBD`

| Mode | Purpose |
|---|---|
| CLI, single scenario | Core demo and tests; prints report and trace |
| CLI, scenario suite | Runs all scenarios; produces the test and traceability report |
| Backend API | Serves the dashboard and complaint form |
| Dashboard | React app against the API |

## 5. Outputs and logs

- JSON report (strict-official or extended) and Markdown report per incident.
- Append-only message and state log (SQLite and/or JSONL) per incident.
- Suite summary: pass/fail by test ID.
- Locations to be fixed at implementation.

## 6. Reproducibility rules

- Scenario inputs are frozen in `sample_data/scenarios/`; tests never depend on regeneration.
- Dependency versions are pinned once chosen.
- Whether the generator can be re-run deterministically is `UNKNOWN` (doc 06 §3, item 7).
- A clean-checkout run is part of the test suite (`T-REPRO-01`).

## 7. Troubleshooting — `TBD`

Filled in from problems actually encountered.
