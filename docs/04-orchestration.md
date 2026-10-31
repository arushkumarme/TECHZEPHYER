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

## 7. Replay and reproducibility

- The log contains enough to replay an incident without re-running agents: task messages, tool-call records with results, findings, clarifications, decision.
- Re-running a scenario with the same configuration and data must give the same states, decision and score (`T-REPRO-*`). Whether the generator supports fixed seeds is `UNKNOWN` (doc 09).
- Pause/resume across restarts is **not** promised (`SRC-1 p3 §4`: optional).

## 8. Extension hooks

- `community_candidate` messages enter at `RECEIVED` (doc 10). They are stored with the incident and passed to A-CORR as *unverified* evidence.
- If the extension is disabled the hook is never invoked (`T-ISO-01`).
