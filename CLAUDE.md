# NetCoop AI — ground rules for Claude Code

Project: NetCoop AI, multi-agent network fault diagnosis and interoperability, for the IIT Bhubaneswar Agentic AI Hackathon.
Status: the application is **built and verified** on synthetic data (all 12 official components + extensions A and B; see `IMPLEMENTATION_PLAN.md`, `IMPLEMENTATION_LOG.md`, `docs/results/release-verification.md`). Current work: the **protocol upgrade** on branch `feature/protocol-upgrade`, driven by the prompt pack (`../../netcoop-cli-prompts.md`, Prompts 0–8).

## Precedence when sources conflict

1. The official problem statement (`SRC-1`, summarised and cited in docs/00 and docs/01).
2. What is built and tested in this app, plus the owner's later instructions. MCP and pause/resume stay exactly as they are; do not extend them.
3. The prompt pack. Treat it as a description of capabilities to **add**, not a spec that overwrites the app. Where the pack's docs are stale ("design stage", "generator pending"), the repository's own docs and code are the truth; correct the stale statements.

## Rules

1. **Field names come from docs/06 (observed from the organizer generator); never invent more.** No new telemetry fields, units, aliases, topology fields, ground-truth labels or DNS/DHCP signals. Problem-statement metric *categories* (latency, packet loss, …) are semantic attributes attached to the observed field names, not new fields.
2. The official report has exactly the ten keys in docs/07 §1. Never rename, remove or reinterpret them.
3. Agent-to-agent transport is the in-process, deterministic message bus. MCP exists only as the read-only tool/resource interface (doc 16) and pause/resume as built (doc 04 §10); do not extend either. The core never makes network calls (the one exception is the hash-verified download of the organizers' generator notebook) and must work with no LLM.
4. Everything must be deterministic and testable: inject clocks and ID factories, no unseeded randomness, no hidden global state.
5. Honesty: data is simulated; never write "live" or "real-time monitoring"; confidence is a heuristic score and is never called "calibrated" (docs/08 §9).
6. Missing data is never healthy data. Use the "not assessable" state.
7. Do not guess unresolved decisions. Implement the documented default, mark it PROVISIONAL, and add it to docs/00 §7 with a new D-number.
8. Documentation: keep the existing docs (00–16) + README. Do not add new doc files unless a prompt says so. Update existing docs to match the code. Text between `BEGIN GENERATED` and `END GENERATED` markers is produced by scripts; never hand-edit it.
9. Traceability: in docs/01 only mark a row as done when its test passes, and name the test.
10. Do not delete files outside the current task.
11. **Dependencies: add no new ones.** Existing dependencies stay (pydantic, networkx, FastAPI, mcp, Playwright, and the dashboard's npm packages). If one seems needed, ask first.
12. Working style: begin each task with a short plan (max 15 lines, plain English) and wait for "go". End with: what changed, how to verify (exact commands you ran), and what is unresolved. Explain new concepts in plain English; the owner is a beginner in agentic AI.

## Protocol-upgrade rulings (owner, 2026-11-01)

- **Keep the app's term names** (`upstream_congestion`, `weak_wifi`, generator field names such as `latency_ms`). The pack's names were placeholders chosen before the generator was inspected. Do not mass-rename anything.
- **Vocabulary:** do not rewrite the existing Python `Literal`s (`src/netcoop/core/vocab.py` and others). Add a registry layer on top. Every existing term gets a definition, status and source; every metric term also gets its problem-statement category, unit and dimension from docs/06. Keep ONE source of truth, with a test that fails if metadata and code drift apart. Export it to JSON for the conformance kit and generate the docs appendix from it.
- **Protocol version stays on 1.x.** The new envelope fields (`snapshot_id`, `mode`, `data_provenance`, `seq`) are OPTIONAL in 1.1 and stamped by the bus, so 1.0 messages still parse. Add compatibility tests. Conflict messages (Prompt 8) would become 1.2.
- **No new dependencies** (rule 11).

## Branch, test and commit policy

- Work only on `feature/protocol-upgrade` (branched from `develop`). Never touch `develop` or `main` directly.
- Baseline: all 318 existing tests (311 default + 7 browser UI via `uv run pytest -m ui`) must still pass after every prompt. If a prompt requires changing an existing test, list which test and why **before** changing it.
- Gates per prompt: `uv run pytest -q`, `uv run pytest -m ui -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `npm --prefix dashboard run build`, `npm --prefix dashboard test`, `uv run netcoop scenarios run-all` (13/13).
- Commit once per finished prompt on the branch, only when every gate passes. Commit messages end with the session's attribution lines. Do not push unless the owner asks.
