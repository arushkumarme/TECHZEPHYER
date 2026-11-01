# Agent Interoperability and Protocol Design

## 1. Goal

Interoperability was treated as a first-class design goal. NetCoop AI's five agents — three specialists, a correlation agent and a reporting agent — never call each other's functions: every request, reply, question, conflict and decision crosses a message bus as a JSON envelope, is validated, and is written to an append-only log before delivery. The protocol is therefore an inspectable artefact a judge, or a future non-Python agent, can read without reading agent code.

## 2. Core Protocol Decisions

- **Message envelope.** Every message carries `protocol_version`, `message_id`, `incident_id`, `in_reply_to`, `sender`, `recipient`, `message_type`, `sent_at`, `payload_schema_version`, `status` and a typed `payload`. Version 1.1 added `snapshot_id`, `mode`, `data_provenance` and a bus-assigned `seq`. Versions are `MAJOR.MINOR`: any minor of a supported major is accepted, other majors are rejected (1.0–1.2 all parse today).
- **Shared controlled vocabulary.** 39 TOML term dictionaries under `config/vocabulary/` define causes, severities, relations, stances and statuses. Fields annotated with `VocabTerm` are rejected if they use an unregistered term, so a cause cannot mean different things in different agents.
- **Authority matrix.** Who may send which type, to whom, in which incident state, is declared as data in `config/protocol/authority.toml` and enforced by the conversation guard.
- **Explicit conflict handling.** Protocol 1.2 adds `conflict_report` / `conflict_response`. A conflict may only be raised for relations `competes` or `contradicts`, and the party asked to respond must be a party to it. Every conflict, resolved or not, is kept in the decision's `conflict_trail`.
- **Evidence provenance.** Observations carry structured `EvidenceRef`s (message id, metric, entity, window), so any claim in the report traces back to its producing message.
- **Snapshot ID.** `SNAP-<12 hex>` fingerprints the data bundle every agent of an incident analysed; it is stamped on every envelope and in the trace banner, so a run can be reproduced.
- **Validation on every hop.** Even in-process delivery serializes to JSON and re-parses through `parse_message`, exercising the same contract an external transport would.

## 3. Message Types Supported

| Type | Purpose |
|---|---|
| `task_request` | Orchestrator delegates an investigation, correlation or report task. |
| `finding` | Specialist's independent result: observations, hypotheses, gaps, tool calls. |
| `clarification_request` | Correlation agent asks one targeted question (recheck metric, what-if, widen window). |
| `clarification_response` | Specialist answers, partially answers or declines, with a reason. |
| `conflict_report` | Correlation agent states a real disagreement and names the party to respond. |
| `conflict_response` | That party maintains, revises, withdraws or reports it cannot assess. |
| `decision` | Ranked hypotheses, margin, gate checks and abstention (exactly one per incident). |
| `report_ready` | Reporting agent's official ten-key report; legal only after a decision. |
| `agent_error` | Structured timeout, crash or malformed-reply record. |
| `community_candidate` | Extension A: aggregated synthetic complaints; needs the flag on. |

## 4. How Interoperability is Enforced

Each transmission runs a fixed pipeline: size limit → JSON/schema validation → routing check → reply-linkage check → conversation guard → sequence stamp → log append → delivery.

Routing is strictly hub-and-spoke. An envelope with neither side set to `orchestrator` is rejected with `DIRECT_AGENT_MESSAGE_FORBIDDEN`. The guard then checks the authority row: sender, recipient, incident state, task kind, `once` constraints, `requires_decision`, reply semantics (a `finding` must answer an *open* `task_request` addressed to that agent) and clarification round limits. Responses must reference their request; duplicate ids are refused.

Invalid or unauthorised messages are **never delivered**. They are logged with `valid = 0`, the error code and a plain-English reason — `SENDER_NOT_AUTHORIZED: only correlation_agent may send a decision; performance_agent tried` — and then raised, so the orchestrator records the failure instead of continuing on bad input. `--show-rejected` keeps them visible in the trace.

## 5. Protocol Inspection

Run a scenario, then inspect its conversation:

```bash
uv run netcoop run --scenario S-02 --trace
uv run netcoop trace INC-0001
```

Useful flags: `--format table|sequence|json`, `--show-rejected`, `--type finding`, `--sender correlation_agent`, `--evidence HYP-...`, and `--explain INC-0001-MSG-000005` to decode one message's fields.

The trace is read from the append-only SQLite log (`var/netcoop.sqlite3`) and interleaves state transitions with messages in accepted order:

```
seq=4 INC-0001-MSG-000001.R performance_agent -> orchestrator finding:
      40 observations, 0 not assessable, hypotheses=['link_congestion']
      [SNAP-a1526c22b3df synthetic-generator]
```

Each line shows sequence number, message id, sender, recipient, type, a payload summary and the snapshot/provenance stamp. `--format json` adds a banner (incident, mode, provenance, snapshot), full envelopes, and accepted/rejected counts by type. `uv run netcoop validate <file>` runs one message or conversation through the same parser and guard.

## 6. Conformance & Testing

```bash
uv run netcoop conformance
```

The kit runs 43 declared examples against the real parser and guard: 15 valid messages that must be accepted, 17 invalid messages that must be rejected with a specific error code, and 11 multi-step conversations that must fail at a declared step. Current result: **15/15, 17/17, 11/11 — PASS**.

The cases are falsifiable rather than illustrative: a specialist sending a decision, a message after the incident is closed, a third clarification round, a direct agent-to-agent message, a non-party conflict response, and an extension message with its flag off. Beyond the kit, 501 automated tests cover round-tripping, version compatibility, guard rules, replay determinism and log integrity.

## 7. Deliberate Design Choices

A custom protocol was chosen over framework messaging because the requirement was an *auditable* message layer: typed payloads, named senders, authority rules and a durable log. Framework messaging usually hides the transport inside call orchestration, which would have made "validate every hop" and "replay by sequence number" claims we could describe but not demonstrate. Writing the bus, guard and schemas directly kept the protocol small enough to test exhaustively, deterministic under parallel specialists (reply ids derive from request ids; logging happens under one lock), and explicitly versioned.

MCP is used deliberately at the boundary: `src/netcoop/mcp` exposes the same read-only tool layer and resources (`netcoop://incidents/{id}/trace`) to outside clients — a transport surface for consumers, not the internal agent protocol.

## 8. Limitations

- **In-process transport only.** Envelopes are JSON and transport-agnostic, but no networked or cross-language transport is implemented.
- **No message signing or authentication.** Authority comes from the guard and configured roles, not cryptographic identity.
- **Single-writer assumption.** Sequence stamping and log appends share one SQLite file and one lock; multiple workers are not supported.
- **Simulation only.** `mode` accepts only `simulation`; complaint ingestion is off by default and excluded from ranking and decision gates.
- **Three protocol versions coexist.** The 1.0–1.2 compatibility shims add behaviour that is easy to overlook in a single message.
