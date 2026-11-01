# 03 — Agents: Responsibilities, Communication and Agent-Like Behaviour

> Version 0.1 · 2026-10-31 · Draft for review · Metric names are written as categories; real field names are pending ([doc 06](06-field-dictionary.md))

## 1. Why these are agents and not five rule modules

`CONFIRMED` (CD-7): the five components must show agent-like behaviour, not be unrelated rule modules.

An agent here must satisfy all of this checklist. Each item is a named test family (`T-AGT-BEHAV-*`, doc 09).

| # | Property | What it means in NetCoop AI | How it is shown |
|---|---|---|---|
| 1 | **Explicit goal and scope** | Acts on a *task message* stating the goal, entities and time window — not on a global data dump | Task message in the log |
| 2 | **Own view of the world** | Reads data only through the tool layer, within its allowed tools | Tool-call records |
| 3 | **Autonomous investigation** | Chooses what to examine next from what it has found so far (e.g. widen the time window to find onset; inspect neighbours of an anomalous device), within a call budget, and decides when it has enough | Sequence of tool calls differs by scenario |
| 4 | **Independent finding** | Returns its own observations, hypotheses and limitations *without seeing other agents' results* | Finding message; a test runs each specialist alone |
| 5 | **Self-assessment and abstention** | States what it could not assess; returns "not assessable" instead of guessing | `not_assessable` entries |
| 6 | **Bounded clarification** | May ask, and may be asked, typed questions — capped in rounds and calls | Clarification messages (§3) |
| 7 | **Message-only coordination** | Never reads another agent's state; communicates through the orchestrator | Message log |
| 8 | **Adapts output to uncertainty** | What it reports (and what A-REPT recommends) changes with its confidence and data quality | Scenario comparison tests |

**Honest limitation.** Agent autonomy here is *bounded and rule-driven*: choice of investigation steps, stopping rules and questions are coded, not free-form LLM planning. That is deliberate (reproducibility, testability, `P-15`). It may look less "agentic" to a judge expecting LLM-driven agents; the mitigation is showing the task → tool-call → finding → clarification trace in the demo, and allowing optional LLM assistance only for wording. `INTERPRETATION`

Each agent can also run **stand-alone** against a recorded task message — that is how independence is tested.

## 2. The five agents

Identifiers `performance_agent` and `infrastructure_agent` appear in the official report example (`SRC-1 p5 §6`, `evidence_sources`); the other three identifiers are `PROPOSAL`.

### 2.1 Telemetry & Performance Agent — `performance_agent` (A-PERF)

- **Mission:** decide whether performance measurements of the scoped entities are normal, degraded or critical, and what pattern they show.
- **Examines (`SRC-1 p2 §3`):** latency, jitter, packet loss, throughput, bandwidth, link utilization; wireless signal if the data has it.
- **Tools:** telemetry query, coverage query.
- **Autonomous decisions:** which entities and metrics to screen first; whether an anomaly is a spike, sustained, or trending; whether to look further back to find onset; when to stop.
- **Finding contents:** graded observations (entity, metric category, value, unit, time window, severity, data-quality flags); performance-oriented hypotheses it supports or contradicts; `not_assessable` list; limitations.
- **May ask (via orchestrator):** a wider time window; additional entities such as neighbours of an anomalous device.
- **Failure handling:** a metric that is missing, unreadable or of unclear unit becomes `not_assessable` with a reason — never "normal". Timeout → orchestrator marks the agent missing (doc 04 §5).
- **Must not:** name a root cause as established; read other agents' findings.

### 2.2 Infrastructure Health Agent — `infrastructure_agent` (A-INFRA)

- **Mission:** decide whether the devices themselves are healthy.
- **Examines (`SRC-1 p2 §3`):** device status, CPU and memory utilization, interface errors, queue drops, other infrastructure metrics the data provides.
- **Tools:** telemetry query, coverage query.
- **Autonomous decisions:** which devices look unhealthy; whether an interface problem is rising or steady; whether queue pressure points to load or to a faulty element; whether to inspect an adjacent interface or device.
- **Finding contents:** as above, with hypotheses such as device overload, interface fault, device/hardware failure, queue-related congestion.
- **May ask:** wider window; more devices.
- **Failure handling:** a device with no status data is itself recorded as an observation ("status unknown"), not as healthy.
- **Must not:** infer topology effects (that is A-CONN's job).

### 2.3 Connectivity Analysis Agent — `connectivity_agent` (A-CONN)

- **Mission:** establish *where* a problem can reach: which entities depend on which, which are affected, and how far a failure would spread.
- **Examines (`SRC-1 p2 §3`):** topology, affected devices, link relationships, scope of connectivity failures.
- **Tools:** topology neighbours/path, what-if failure, coverage query, telemetry query for any link/device state the data provides.
- **Autonomous decisions:** the dependency structure of the scope; which entities share an upstream element; for a what-if question, which downstream entities become isolated vs degraded.
- **Initial scope:** for a telemetry bundle, all entities in it; for a community candidate, the entities mapped to the reported zone plus their upstream dependencies. A-CONN does not wait for other agents' conclusions, which avoids circular dependence.
- **Finding contents:** dependency facts, redundancy facts, scope, any link/reachability state present in the data, and `not_assessable` items.
- **Answers (clarification):** "if entity X is the cause, which entities should be affected?" — the answer is compared with observed damage by A-CORR.
- **Failure handling:** missing topology → scope reported as `unknown`; a telemetry entity absent from the topology is flagged; nothing is guessed. A-CORR then loses the topology-consistency evidence and its confidence ceiling drops (doc 08).
- **Must not:** assert an entity is faulty from structure alone.

### 2.4 Fault Correlation Agent — `correlation_agent` (A-CORR)

- **Mission:** turn independent findings into one reasoned, ranked set of explanations — or conclude that the evidence is insufficient.
- **Inputs:** all findings, the data-quality note, optional community candidate evidence.
- **Tools:** the diagnosis knowledge (C-DIAG), plus clarification requests.
- **Autonomous decisions:** which hypotheses are worth scoring; whether specialists agree; whether a conflict, a narrow margin, or a missing piece of expected evidence justifies a clarification, and which agent to ask; when to stop asking.
- **Output:** ranked hypotheses with score, supporting and contradicting evidence IDs, missing expected evidence, the decision (`diagnosed` / `insufficient_evidence`), and the conflict-resolution trail.
- **May ask:** A-CONN a what-if question; A-PERF/A-INFRA to re-check a metric or widen the window.
- **Failure handling:** a missing specialist → proceed on reduced evidence with a lower ceiling; all specialists missing → `insufficient_evidence`.
- **Must not:** use an LLM to set score or decision; treat community reports as verified; discard a specialist finding silently.

### 2.5 Recommendation & Reporting Agent — `reporting_agent` (A-REPT)

- **Mission:** produce the final report so that a human operator can understand and challenge it.
- **Inputs:** A-CORR's result, all findings, data-quality note, community context.
- **Autonomous decisions:** which recommendations to include and in what mode — *corrective* when confidence is high, *diagnostic next steps* when evidence is insufficient or ambiguous (behaviour adapts to uncertainty); which limitations to state.
- **Output:** official report fields + the additive extension block ([doc 07](07-report-spec.md)); Markdown rendering. Recommendations are marked as requiring human approval, and any action stays simulated.
- **Optional LLM:** may reword narrative text. A deterministic check rejects any wording that cites a metric, device or number not present in the evidence list; on rejection it falls back to the template text.
- **Failure handling:** if A-CORR's result is missing or invalid it still emits a schema-valid report with a failure status and clear errors (D-03).
- **Must not:** change status, cause or confidence set by A-CORR; invent evidence.

## 3. Communication design

All communication is **hub-and-spoke through the orchestrator**; agents never message each other directly. Message types and fields: [doc 05](05-protocol-spec.md).

| Message | From → To | Purpose |
|---|---|---|
| `task_request` | Orchestrator → agent | Goal, scope, time window, tool budget, deadline |
| `finding` | Agent → Orchestrator | Independent observations, hypotheses, limitations |
| `clarification_request` | A-CORR (or a specialist) → Orchestrator → target agent | Typed question, with reason |
| `clarification_response` | Target agent → Orchestrator → requester | Answer or "cannot answer" |
| `conflict_report` (1.2) | A-CORR → Orchestrator → one party | A real conflict: parties, evidence on each side, proposed rule (doc 05 §19) |
| `conflict_response` (1.2) | That party → Orchestrator | Stance after a re-check: maintain, revise, withdraw or cannot assess |
| `agent_error` | Agent or Orchestrator | Failure, timeout or invalid message |
| `community_candidate` | Community module → Orchestrator (extension) | Unverified candidate incident |

**Clarification rules** `PROPOSAL`
- Allowed question types (closed list): *widen time window*, *assess additional entities*, *what-if cause*, *re-check a metric*.
- Maximum rounds per incident and maximum tool calls per agent per task are configuration values (initial default: 2 rounds; values set at implementation).
- A request must state a reason (conflict, narrow margin, missing expected evidence). Free-form questions are not part of the protocol.
- The loop always terminates: when the round limit is reached, A-CORR decides on what it has and records the unanswered question as a limitation.

**Conflicts** (protocol 1.2, `IMPLEMENTED`, D-25 PROVISIONAL): only A-CORR raises a conflict, and only for relations `competes`/`contradicts` or disagreeing readings; hypotheses that are `compatible` or `refine` each other never do. A specialist answers a conflict addressed to it by re-checking and reporting a stance derived from the result (`SpecialistAgent.respond_to_conflict`). Conflict reports count toward the same round limit.

**What the demo shows** (doc 14): the ordered trace of task → tool calls → finding → clarification → decision, which is the visible evidence of items 1–8 in §1.

## 4. Implementation status — specialists (M6, 2026-10-31) — `IMPLEMENTED`, `TESTED`

Code: `src/netcoop/agents/{base,performance,infrastructure,connectivity}.py`; tests `tests/agents/test_specialists.py` (run stand-alone against real ingested generator records).

| Agent | Items it observes (doc 06 names) | Investigation it chooses |
|---|---|---|
| `performance_agent` | `latency_ms`, `jitter_ms`, `packet_loss_pct`, `link_utilization_pct` | screen scope → coverage → deep-dive each anomalous device over the whole bundle (widened window): pattern `spike`/`sustained`/`rising`/`intermittent` and onset |
| `infrastructure_agent` | `status`, `cpu_utilization_pct`, `queue_drops`, `interface_errors` | same loop; a device without status is observed as **status unknown** (`severity=unknown`, not assessable) |
| `connectivity_agent` | topology facts + team-authored probe results (`probe_dns`/`probe_dhcp`) | topology info → own status/latency screen to find suspicious devices → **what-if first for suspicious devices** → upstream path per device → probes. Status/latency it reads stay in `facts` so one raw metric never counts twice |

Checklist evidence (§1): goal/scope from the task (scope test); tools only through a budgeted session (budget test, tool-call records in every finding); adaptive path (a fault scenario makes more, targeted calls than a normal one); independent and reproducible findings; abstention (`jitter_ms` absent in generator `hardware_failure` → `not_assessable MISSING`); clarification answers (`recheck_metric`, `assess_additional_entities`, `widen_time_window`; `what_if_cause` only by connectivity; others decline with a reason); message-only coordination (bus enforces hub-and-spoke). Any exception inside an agent becomes an `agent_error` reply, never a crash.

## 5. Implementation status — correlation and reporting (M7, 2026-10-31) — `IMPLEMENTED`, `TESTED`

- `correlation_agent` (`src/netcoop/agents/correlation.py`) is **stateless**: the orchestrator sends a `task_request` whose `context` holds all findings, the data-quality note, missing agents, community candidates, and every clarification question/answer so far with the round number. Its reply is either a `decision` or a `clarification_request`. It asks only when the gate failed on an **unresolved conflict** (→ `recheck_metric` to the observing agent) or a **narrow margin** (→ `what_if_cause` to `connectivity_agent` for topology-type causes, else `recheck_metric` of the competing causes' key metric). It never repeats a question and stops at `max_rounds`, recording `CLARIFICATION_LIMIT_REACHED`.
- `reporting_agent` (`src/netcoop/agents/reporting.py`) builds, validates and renders the report (doc 07 §9); on an unusable correlation result it emits a schema-valid `failed` report.
- Honest note: with the generator's three profiles the margin is never narrow, so clarifications occur in team-authored variants (S-09); the test `test_narrow_margin_triggers_bounded_clarification` uses one.
