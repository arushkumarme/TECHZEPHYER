# 04 — Orchestration and Workflow

> Version 0.1 · 2026-10-31 · Draft for review · `CONFIRMED` (CD-2): custom deterministic state machine. Concurrency mechanism TBD (D-14).

## 1. Role

The orchestrator is ordinary code, not an AI. It coordinates the five agents, enforces limits, and guarantees that every incident ends in a defined state. Same input and same settings give the same sequence of states. `SRC-1 p3 §4`: "Coordinate agent tasks and consolidate findings into one result." `CONFIRMED`

## 2. Incident states

| State | Entered when | Orchestrator actions | Next states |
|---|---|---|---|
| `RECEIVED` | Telemetry bundle submitted, or a community candidate arrives (extension) | Assign incident ID; record mode, provenance, trigger | `VALIDATING` |
| `VALIDATING` | After receipt | Run ingestion (doc 05 §6) | `READY`, `READY_WITH_WARNINGS`, `REJECTED` |
| `REJECTED` | Bundle unusable | Emit error report; stop | terminal |
| `READY` / `READY_WITH_WARNINGS` | Bundle usable | Store normalized bundle and data-quality note | `DISPATCHED` |
| `DISPATCHED` | Tasks created | Send `task_request` to A-PERF, A-INFRA, A-CONN in parallel with deadlines | `COLLECTING` |
| `COLLECTING` | Tasks in flight | Gather findings; mark late or failed agents as missing | `CORRELATING` |
| `CORRELATING` | All findings in, or deadline passed | Send findings (and community evidence) to A-CORR | `CLARIFYING`, `DECIDED` |
| `CLARIFYING` | A-CORR issued a valid clarification request and the round limit is not reached | Route request to target agent; return the answer | `CORRELATING` |
| `DECIDED` | A-CORR returned decision | Record `diagnosed` or `insufficient_evidence` | `REPORTING` |
| `REPORTING` | Decision recorded | Send to A-REPT; validate the report | `AWAITING_REVIEW`, `FAILED` |
| `AWAITING_REVIEW` | Report contains recommendations | Hold actions until a human decision is recorded; actions remain simulated | `COMPLETE` |
| `COMPLETE` | Report delivered | Close incident | terminal |
| `FAILED` | An unrecoverable internal error | Emit a failure report with clear errors | terminal |

Every transition is logged with timestamp, trigger and (if any) message ID.

## 3. Workflow

1. **Trigger.** CLI/file submission of a bundle; or (extension) a candidate incident from complaints, which may start a run scoped to the reported zone or add context to a running incident.
2. **Validate and normalize** (doc 05 §6). Outcome: usable, usable with warnings, or rejected with a specific error.
3. **Create the incident** with ID, mode (`simulation`), and data provenance.
4. **Phase 1 — parallel specialists.** Task messages go to A-PERF, A-INFRA, A-CONN. Each task states scope, window, tool-call budget and deadline.
5. **Collect.** Findings are stored. A late or failed agent is recorded as missing; the run continues.
6. **Phase 2 — correlation.** A-CORR receives all findings, the data-quality note and any community evidence.
7. **Clarification loop.** If A-CORR sees a conflict, a narrow margin, or missing expected evidence it may ask typed questions (doc 03 §3). Maximum rounds per incident is configuration.
8. **Decision gate** (doc 08 §4.5): `diagnosed` or `insufficient_evidence`.
9. **Phase 3 — report.** A-REPT builds the report; it is validated against the report schema before release.
10. **Human review.** Recommendations are shown as *requires human approval*. If an operator approves, the approval is logged and the action is *simulated*; nothing external is changed.
11. **Log.** The full message and state-transition log is retained and can be rendered as a trace.

## 4. Parallelism and ordering

- Phase 1 agents are independent and may run concurrently; the orchestrator is the only writer of the incident state.
- A-CORR never starts before Phase 1 completes or its deadline passes.
- Clarification answers are processed one at a time, in request order, so replay is deterministic.
- Timeouts and tool budgets are configuration values (not fixed here).

### 4.1 Which messages are legal in which state (protocol 1.1)

Each incident state allows only certain messages. The conversation guard (doc 05 §15, generated authority matrix) enforces this against the orchestrator's current state:
- `READY` / `READY_WITH_WARNINGS` / `DISPATCHED` / `COLLECTING`: investigate tasks (sent before the `DISPATCHED` transition; retries during `COLLECTING`). Specialist findings arrive in `DISPATCHED` / `COLLECTING`.
- `CORRELATING`: correlate tasks, and the correlation agent's answer, either a `clarification_request` (counted toward the round limit) or the single `decision`.
- `CLARIFYING`: the relayed question to the named target, and its `clarification_response`.
- `REPORTING`: the report task and the single `report_ready`, only after a decision.
- Any open state: `agent_error` (either direction) and, with the extension on, `community_candidate`.
- `COMPLETE` / `FAILED` / `REJECTED`: nothing (`INCIDENT_CLOSED`).

## 5. Degraded operation and failure handling

| Situation | Orchestrator behaviour | Effect on result |
|---|---|---|
| Bundle unparseable / unsupported major schema / no identifiable entity, time, or usable metric | `REJECTED`, specific error code | Error report, no diagnosis |
| Some metrics, devices or records missing | `READY_WITH_WARNINGS`; items tagged `not_assessable` | Evidence reduced; confidence ceiling lowered; limitations listed |
| One specialist times out or errors | Retry once if configured; else mark missing | Diagnosis on remaining evidence; missing agent in limitations |
| All specialists fail | Skip to `DECIDED` with `insufficient_evidence` | Report states no evidence was available |
| A-CORR fails | Retry once; else `FAILED` | Failure report; specialist findings still attached |
| A-REPT fails | Retry once; else use deterministic fallback report builder | Report without narrative polish |
| Malformed or invalid agent message | Reject message, log `agent_error`, treat as missing | As above |
| Clarification round limit hit | Stop asking; A-CORR decides | Unanswered question recorded as a limitation |
| LLM unavailable or rejected by the grounding check | Fall back to template text | No change to diagnosis |
| Extension fails | Core run continues unaffected | Extension data absent |

## 6. Conflict resolution

Authority: A-CORR applies the rules; the orchestrator only ensures every conflict is recorded. Rules and precedence are in [doc 08 §5](08-diagnosis-and-confidence.md). Summary: direct measurement beats inference beats user report; fresher beats staler within a tolerance; topology-consistent beats inconsistent; unresolved conflicts keep both explanations, lower confidence, and drop nothing.

**Conflict exchange (protocol 1.2, `IMPLEMENTED`):** when A-CORR answers a `correlate` task with a `conflict_report`, the orchestrator moves to `CLARIFYING`, relays the report unchanged to the party it names, and records the party's `conflict_response` in the same context slot as a clarification answer; A-CORR's resolution logic is unchanged. The guard enforces sender, recipient, reply and round limit (doc 05 §15, §19). The decision's `conflict_trail` records every conflict and its rule.

## 7. Replay and reproducibility

- The log contains enough to replay an incident without re-running agents: task messages, tool-call records with results, findings, clarifications, decision.
- Re-running a scenario with the same configuration and data must give the same states, decision and score (`T-REPRO-*`). Whether the generator supports fixed seeds is `UNKNOWN` (doc 09).
- Pause/resume across restarts **is implemented** (optional in `SRC-1 p3 §4`; built in M10, §10 below), and is not extended by the protocol upgrade.
- The conversation state (open tasks, questions, rounds used, decision/report sent) is rebuilt from the message log alone: `MessageBus.rebuild_state(incident)` equals the live state (`tests/core/test_bus_v11.py`). Replaying a run with the same clock, ids and configuration gives a byte-identical log export (`LogStore.export_jsonl`).

## 8. Extension hooks

- `community_candidate` messages enter at `RECEIVED` (doc 10). They are stored with the incident and passed to A-CORR as *unverified* evidence.
- If the extension is disabled the hook is never invoked (`T-ISO-01`).

## 9. Implementation (M8, 2026-10-31) — `IMPLEMENTED`, `TESTED`

Code: `src/netcoop/orchestrator/{states,workflow,faults}.py`; settings `[orchestration]` in `config/netcoop.toml`; tests `tests/orchestrator/test_workflow.py`.

- **Transition table** (`states.ALLOWED`) is enforced; an illegal move raises. `COLLECTING → COLLECTING` is used only to log an agent failure/retry event.
- **Phase 1:** tasks to the three specialists are built in fixed order in the orchestrator thread; replies run in a thread pool (`parallel_specialists = true`) with a per-agent deadline (`specialist_deadline_s`). Timeout, `agent_error`, invalid message or exception → `agent_error` logged (codes `AGENT_TIMEOUT` / `AGENT_FAILED` / `MESSAGE_INVALID`), retried `agent_retries` times (default 1), then the agent is **missing**.
- **Determinism:** reply ids derive from request ids (`<request>.R`); message ids are namespaced per incident (`INC-0001-MSG-000001`); incident ids are sequential per log database. Test `test_sequential_and_parallel_runs_are_identical` shows parallel and sequential runs log identical message ids, states and reports.
- **Correlation** is retried once, else `FAILED` with a failure report that still lists specialist contributions. **Reporting** is retried once, else the deterministic fallback builder is used (transition trigger `fallback_report`).
- **Deviation from §5 (documented):** when all specialists are missing the orchestrator still runs the correlation agent (with no findings) instead of skipping to `DECIDED`; it deterministically yields `insufficient_evidence` with three `AGENT_MISSING` limitations, so the report explains itself.
- **Persistence:** `incidents` and `reports` tables (append-only) join `messages` and `transitions` in the SQLite log (groundwork for M10 pause/resume).
- **Fault injection** (`timeout`, `error`, `invalid`) exists only for scenario S-10 and tests; never active unless requested.

## 10. Persistent workflow state, pause/resume and recovery (M10, 2026-10-31) — `IMPLEMENTED`, `TESTED`

Official component 10 (`SRC-1 p3 §4`, optional) is now in scope by owner decision ID-01, superseding §7's "not promised".

- **Checkpoints** (append-only SQLite table `checkpoints`): `input` (raw bytes, base64, plus options), `finding:<agent>` written **as each finding arrives**, `phase1` (missing agents), `clarification` (each question + answer), `decision`. Each is written *before* the transition that depends on it.
- **Resume** (`Orchestrator.resume(incident)`, CLI `netcoop resume INC-…`): a new process reads the last state and the checkpoints, records a `resume` self-transition, re-derives the (deterministic) normalized bundle, and continues. Only work that never completed is re-dispatched (e.g. a crash while the third specialist worked re-runs only that specialist). Message numbering continues after the highest id already logged.
- **Pause** (`run(..., pause_after=STATE)`, CLI `--pause-after STATE`): stops cleanly once STATE is entered; `netcoop incidents` lists incidents with their state and a `resumable` flag.
- **Not resumable:** terminal states (`REJECTED`, `FAILED`, `COMPLETE`) and `AWAITING_REVIEW`, which waits for a human decision (M11).
- **Crash simulation:** fault `crash` raises `SimulatedCrash` (a `BaseException`, so no handler can swallow it), modelling the process dying mid-incident.
- **Evidence:** `tests/orchestrator/test_persistence.py` — pause at VALIDATING / COLLECTING / CORRELATING / DECIDED then resume in a fresh orchestrator gives the same status, cause, confidence, devices, evidence and actions as an uninterrupted run; crash during correlation (with clarification rounds) and during phase 1 are recovered; checkpoints are append-only; CLI pause → list → resume works.
