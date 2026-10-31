# NetCoop AI

**Multi-Agent Network Fault Diagnosis and Interoperability** — a project for the IIT Bhubaneswar Agentic AI Hackathon.

> **Status (2026-10-31): the mandatory core is implemented and tested** (five agents, orchestrator, protocol, validation, diagnosis, report, CLI, 13 scenarios). Optional components and extensions are in progress — see [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) and [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md).
> Team size, roles and deadline are **TBD**.
> The organizer's generator has been inspected and vendored; field names are `OBSERVED` ([`docs/06`](docs/06-field-dictionary.md)).

## What NetCoop AI is

Five cooperating agents, coordinated by a deterministic orchestrator, examine network telemetry, exchange structured messages, weigh competing explanations, and produce **one** evidence-based diagnostic report. When the evidence is too thin, the system says so instead of guessing a root cause.

## What it is not

- **Not connected to IIT Bhubaneswar's network.** Hackathon mode uses synthetic data only.
- **Not live monitoring.** Dashboards and maps show *scenario playback*.
- **Not an auto-fixer.** Every remediation is simulated and needs human approval.
- **Not dependent on an LLM.** The diagnostic core runs without one.

## Scope

| Part | What | Priority |
|---|---|---|
| **Core** | Five agents, orchestrator, interoperability protocol, validation, diagnosis, confidence method, JSON report, CLI, tests, demo | Mandatory (official requirements) |
| **Extension A** | Community Signal Intelligence: student complaints → candidate incidents → correlated with telemetry, always labelled *unverified* | After core passes its tests |
| **Extension B** | Geospatial Network Intelligence: campus map, dependency and blast-radius view | After core; builds on A's output |

Extensions are feature-flagged. The core must pass all of its tests with both extensions switched off.

## Two operating modes

| | Hackathon simulation mode | Future campus deployment mode |
|---|---|---|
| Data | Synthetic telemetry, simulated topology, reproducible scenarios | Authorized telemetry and verified inventory — **needs access from the IIT Bhubaneswar network team** |
| Status | The only mode we plan to build | Design notes only ([`docs/15`](docs/15-future-deployment.md)) |

## Documentation map

| File | Answers the question |
|---|---|
| [`00-scope-and-decisions.md`](docs/00-scope-and-decisions.md) | What are we building, what is confirmed vs proposed, what is still undecided? |
| [`01-requirements-traceability.md`](docs/01-requirements-traceability.md) | Where does every official requirement land (component, doc, module, test, demo)? |
| [`02-architecture.md`](docs/02-architecture.md) | What are the components and the technology stack? |
| [`03-agents.md`](docs/03-agents.md) | What does each of the five agents do, and why are they agents? |
| [`04-orchestration.md`](docs/04-orchestration.md) | How does one incident flow from input to report? |
| [`05-protocol-spec.md`](docs/05-protocol-spec.md) | What messages do agents exchange; how is bad input handled? |
| [`06-field-dictionary.md`](docs/06-field-dictionary.md) | What do the telemetry fields mean? **Pending generator inspection.** |
| [`07-report-spec.md`](docs/07-report-spec.md) | What exactly is in the diagnostic report? |
| [`08-diagnosis-and-confidence.md`](docs/08-diagnosis-and-confidence.md) | How are causes ranked and confidence scored? |
| [`09-scenarios-and-testing.md`](docs/09-scenarios-and-testing.md) | Which scenarios and tests prove it works? |
| [`10-community-signal-intelligence.md`](docs/10-community-signal-intelligence.md) | Extension A |
| [`11-geospatial-network-intelligence.md`](docs/11-geospatial-network-intelligence.md) | Extension B |
| [`12-safety-privacy-simulation-policy.md`](docs/12-safety-privacy-simulation-policy.md) | What must we never claim or do? |
| [`13-setup-and-operations.md`](docs/13-setup-and-operations.md) | How will it be installed and run? (skeleton until implementation) |
| [`14-demo-and-submission.md`](docs/14-demo-and-submission.md) | Demo script, submission checklist, judge Q&A |
| [`15-future-deployment.md`](docs/15-future-deployment.md) | What would real deployment need? |
| [`16-mcp.md`](docs/16-mcp.md) | How is the MCP interface exposed and tested? |

Suggested reading order: 00 → 01 → 02 → 03 → 04 → 05 → 07 → 08.

## Source of truth

1. The official problem statement (`Agentic_AI_Hackathon.pdf`) overrides everything else.
2. Decisions the project owner confirmed in conversation (2026-10-31).
3. The project master instruction (`da2e9cd9-attachment.txt`).
4. Our own proposals — useful, but never treated as requirements.

Where sources disagree, the disagreement is recorded in [`docs/00`](docs/00-scope-and-decisions.md) §6 rather than silently resolved.

## Quick start (commands verified 2026-10-31)

```bash
uv sync                                    # Python 3.12 + locked dependencies
uv run netcoop run --scenario S-02 --trace # diagnose the link-congestion scenario, show the agent trace
uv run netcoop scenarios run-all           # all 13 scenarios with expected-outcome checks
uv run pytest -q                           # full test suite
```

Full instructions: [`docs/13-setup-and-operations.md`](docs/13-setup-and-operations.md). Latest suite results: [`docs/results/scenario-results.md`](docs/results/scenario-results.md).
