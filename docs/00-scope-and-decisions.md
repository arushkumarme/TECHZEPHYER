# 00 — Scope, Decisions and Open Questions

> Version 0.1 · 2026-10-31 · Draft for review · Team size, roles, deadline: **TBD**

This is the single place for scope, labels, decisions, source disagreements and open questions. Other documents refer here instead of repeating it.

## 1. Source register

| ID | Source | Notes |
|---|---|---|
| SRC-1 | `Agentic_AI_Hackathon.pdf` — "NetCoop AI — Multi-Agent Network Fault Diagnosis and Interoperability", 7 pages | **Authoritative.** Cited as `SRC-1 p<page> §<section>` |
| SRC-2 | `da2e9cd9-attachment.txt` — "Project Master Instruction — NetCoop AI" | Working rules and a second evaluation list. Incomplete (see §6). Cited as `SRC-2 l.<line>` |
| SRC-3 | Project owner's decisions and corrections in conversation, 2026-10-31 | Cited as `SRC-3` |
| SRC-4 | Synthetic telemetry generator (Google Colab notebook linked at `SRC-1 p4 §5`) | **Not provided and not accessible** (needs sign-in). Nothing in this repository is derived from it |

## 2. Label legend (used in every document)

**What kind of statement is this?**

| Tag | Meaning |
|---|---|
| `CONFIRMED` | Stated in an authoritative source (SRC-1 or SRC-3). The source is cited. |
| `OBSERVED` | Found by inspecting a supplied artifact (dataset, notebook, code). *Currently none: no dataset has been inspected.* |
| `INTERPRETATION` | Our reading of confirmed material. May be wrong; flagged so it can be checked. |
| `PROPOSAL` | Our suggested design. Not a requirement. |
| `UNKNOWN` / `PENDING` | Information we do not have. Never filled by guessing. |

**Where does it live in the project?**

| Tag | Meaning |
|---|---|
| `PLANNED` | We intend to build it in the hackathon |
| `SIMULATED` | Built, but using synthetic or invented stand-ins, always labelled as such |
| `FUTURE` | Described only; not built |
| `NEEDS-ACCESS` | Requires authorization or access from the IIT Bhubaneswar network team |

## 3. Refined scope

**Core — mandatory, scored.** `PLANNED`
Five collaborating agents; a deterministic orchestrator; a documented message protocol; validation and normalization; evidence-based diagnosis; a documented heuristic confidence score; a structured JSON report; a CLI; reproducible scenarios and tests; a demo.

**Extension A — Community Signal Intelligence.** `PLANNED` (after core) — see doc 10.
**Extension B — Geospatial Network Intelligence.** `PLANNED` (after core) — see doc 11.

**Out of scope** `CONFIRMED` (SRC-3, earlier project rules): access to the real campus network; any claim of live monitoring; automatic or unapproved remediation; additional agents without architectural justification; LangGraph, Kafka and MCP at this stage; a production WhatsApp integration.

**Protection of the core.** `PROPOSAL` Extensions live in separate packages behind feature flags. They add data to reports only under one additive key (doc 07) and never rename or remove official fields. Test `T-ISO-01` runs the full core suite with both extensions disabled.

## 4. Operating modes

| Capability | Hackathon simulation mode | Future campus deployment mode |
|---|---|---|
| Telemetry | Synthetic files — `PLANNED`, `SIMULATED` | Authorized feeds — `FUTURE`, `NEEDS-ACCESS` |
| Topology | Simulated, labelled `SIMULATED` | Verified inventory — `FUTURE`, `NEEDS-ACCESS` |
| Scenarios | Reproducible, scripted | Real incidents — `FUTURE` |
| Complaints | Synthetic complaints from synthetic test reporters — `SIMULATED` | Authorized student channels — `FUTURE`, `NEEDS-ACCESS` |
| Remediation | Simulated, human approval recorded — `SIMULATED` | Human-approved change process — `FUTURE` |
| UI wording | "Scenario playback" — never "live" | "Live" only once real feeds exist |

Agents, protocol and report format are the same in both modes; only the data source adapter differs (doc 02 §5). `PROPOSAL`

## 5. Confirmed decisions (SRC-3, 2026-10-31)

| # | Decision |
|---|---|
| CD-1 | Provider-independent LLM interface. The diagnostic core works without an LLM. An LLM may optionally assist complaint-text extraction and report wording. |
| CD-2 | Orchestration is a custom deterministic state machine. No LangGraph, Kafka or MCP at this stage. |
| CD-3 | Dashboard: React + FastAPI + Leaflet, frontend and backend separate. |
| CD-4 | Complaint channels: web form is primary; Telegram is a stretch; WhatsApp Business is future scope, not a hackathon dependency. |
| CD-5 | Team size and deadline are not confirmed — written as TBD; no members, roles or dates are invented. |
| CD-6 | Treat numeric confidence as a transparent heuristic score until validated against ground-truth scenarios. |
| CD-7 | Each agent must show agent-like behaviour (tasks, structured messages, independent findings, bounded clarification), coordinated by the deterministic orchestrator — not five unrelated rule modules. |
| CD-8 | Preserve the exact official report schema (doc 07). |
| CD-9 | DNS/DHCP diagnosis depends on evidence that actually exists; otherwise document the gap and propose an optional probe interface. |
| CD-10 | A partially missing metric never invalidates a whole bundle; missing data is never treated as healthy data. |
| CD-11 | Complaint data and campus topology in the demo are synthetic or otherwise authorized, clearly labelled, and never imply access to the production network. |

## 6. Where sources disagree or are incomplete

### 6.1 Two different evaluation lists — **unresolved** (D-01)

| `SRC-1 p6 §8` (official) | Weight | `SRC-2 l.47–51` | Weight |
|---|---|---|---|
| Agent interoperability and protocol design | 30% | Agentic Workflow & Autonomy | 30% |
| Diagnostic accuracy and evidence quality | 25% | Prototype Functionality & UX | 20% |
| Agent orchestration and conflict resolution | 15% | Tool Interaction & Technical Implementation | 20% |
| Robustness to missing, inconsistent, or incompatible data | 15% | Adaptation & Failure Recovery | 15% |
| Code quality, documentation, and demonstration | 5% | Evaluation, Verification & Robustness | 15% |
| Innovation, usability, and extensibility | 10% | | |

- **Origin of the SRC-2 list:** unstated. It could be a general hackathon rubric, an earlier round, or another problem statement. `UNKNOWN`
- **Why it matters:** SRC-2 gives UX 20%; SRC-1 gives UX no dedicated weight (only "usability" inside the 10% innovation line). If SRC-2 applies, dashboard polish matters far more.
- **Handling:** SRC-1 is treated as authoritative, per project rules. Doc 01 §7 maps our design onto the SRC-2 list as well, so the project is not exposed if SRC-2 turns out to apply. No requirement is changed.

### 6.2 `SRC-2` is incomplete

Headings 1, 9 and 10 are absent; heading 6 ("Be rigorous about diagnosis and evidence") has no body; line 7 ends with a stray backslash. Whether a fuller version exists is `UNKNOWN` (D-15).

### 6.3 Interpretation notes on `SRC-1`

- **Scenarios are suggested, not individually required.** `SRC-1 p4 §5` titles the six scenarios "Suggested test scenarios". The deliverable `SRC-1 p6 §7.3` requires inputs for "normal operation and multiple network fault scenarios". *Correction to an earlier summary:* the DNS/DHCP and interoperability-failure scenarios are suggested, not mandatory by themselves. The mandatory item is at least one malformed, missing or incompatible input case (`SRC-1 p6 §9`). `INTERPRETATION`
- **Dataset list is permissive.** `SRC-1 p4 §5` says the dataset "may include" latency, jitter, packet loss, throughput, bandwidth, link utilization, device ID and status, CPU and memory, egress queue drops, interface errors, wireless signal "where available", timestamps and topology. This is a list of categories, not field names, and not a guarantee.
- **DNS/DHCP gap.** The scenario "DNS or DHCP failure: Service-specific connectivity problems" has no corresponding signal in the dataset list. Whether the generator offers one is `UNKNOWN` (D-11).
- **Weak Wi-Fi gap.** The scenario mentions "increased retransmissions", which is not in the dataset category list. `UNKNOWN`.
- **Example values are illustrative.** `SRC-1 p5 §6` states the report values are illustrative. The metric names in that example (`latency_ms`, `link_utilization_pct`, `queue_drops`) are therefore *not* confirmed dataset fields.
- **Report-field mandatoriness.** The PDF does not mark individual JSON keys as mandatory or list allowed `status` values; it lists required report *content* (`SRC-1 p3 §4`, `p6 §9`). See doc 07.

## 7. Open decisions register

| ID | Question | Blocks | Default if not answered |
|---|---|---|---|
| D-01 | Which evaluation list applies — `SRC-1 §8` or `SRC-2`? | Dashboard/UX priority | Follow `SRC-1`; cover `SRC-2` as hedge |
| D-02 | Provide the generator (code, parameters, sample output) | Docs 05 alias map, 06, 08 evidence matrix, 09 scenarios, topology | None — remains pending |
| D-03 | Allowed `status` values beyond `"diagnosed"`; what a normal-operation or undetermined result is called | Doc 07, 08 | `diagnosed`, `insufficient_evidence`, `no_fault_detected`, `failed` (`PROPOSAL`) |
| D-04 | Confidence output: number only (as in example) or number plus a category; what number appears when evidence is insufficient | Doc 07, 08 | Number plus category (additive), number capped low when insufficient |
| D-05 | Type of `supporting_evidence[].value` for non-numeric evidence (e.g. device status) | Doc 07 | Allow number or string; document it |
| D-06 | Team size, roles, deadline | Roadmap ownership | TBD — none invented |
| D-07 | Which LLM provider(s), venue internet, offline need | Doc 02 §4, 10 | LLM disabled by default |
| D-08 | Source and accuracy of campus building coordinates | Doc 11 | Illustrative positions, labelled approximate |
| D-09 | Does the generator provide topology and location/zone data? Who authors the simulated topology and zone-to-device mapping? | Docs 02, 10, 11 | Team-authored, labelled synthetic |
| D-10 | Complaint cluster size and time window | Doc 10 | Set in config from scenarios; demo uses a small value, labelled |
| D-11 | DNS/DHCP evidence: present in generator? If not, adopt the optional probe interface? | Docs 06, 08, 09 | Do not diagnose DNS/DHCP without evidence; propose probe interface (doc 08 §3.3) |
| D-12 | Demo flow uses web form (and Telegram if built); WhatsApp stays future. Confirm, given the WhatsApp-style demo idea | Docs 10, 14 | As stated; see doc 10 §3 |
| D-13 | Any contact with the IIT Bhubaneswar network team | Doc 15 wording | None assumed |
| D-14 | Python / Node versions and package choices | Doc 13 | TBD at implementation |
| D-15 | Is there a complete version of `SRC-2`? | Doc 00 §6.2 | Proceed with what exists |
| D-16 | Metric -> category / unit / dimension map (`config/vocabulary/metric.toml`) | Doc 05 App. A, unit checks | **PROVISIONAL**: derived from the generator fields in doc 06; revisit if another data source is added |
| D-17 | Data-rate and power-level dimensions (throughput, bandwidth, wireless signal) have no units | Doc 05 App. A | **PROVISIONAL**: no generator field uses them, so no units are defined; never guessed |
| D-18 | Names of abstention reasons (one per decision-gate check) | Doc 05 App. A, Prompt 3 | **PROVISIONAL**: names mapped 1:1 to the existing gate checks in `diagnosis/scoring.py` |
| D-19 | Registry-only vocabularies not yet carried in messages: `task_kind`, `evidence_type`, `evidence_stance`, `recommendation_priority`, `aggregation` | Prompt 3 | **PROVISIONAL**: defined now, wired into payloads in Prompt 3 |
| D-20 | Severity/kind of non-ingestion error and limitation codes (e.g. `GATE_NOT_MET` = info) | Doc 05 App. A | **PROVISIONAL**: team-chosen; ingestion codes keep doc 05 §7 severities (test-enforced) |
| D-21 | `cause_type` is **closed** (the prompt pack proposed extensible) | Doc 08 | **PROVISIONAL**: a new cause needs a catalog signature and scoring, so `x-` extensions are not accepted; `rationale_code` is the extensible vocabulary instead |
| D-22 | Incident ID format | Doc 05 §5 | **PROVISIONAL**: `<prefix>-NNNN`, prefix `INC` (configurable `[protocol] incident_prefix`); the PDF mandates no format |
| D-23 | Maximum message size | Doc 05 §13 | **PROVISIONAL**: 1 MiB (`[protocol] max_message_bytes`), about 20x the largest message of the scenario suite (~47 KB); larger messages are rejected with `MESSAGE_TOO_LARGE` |
| D-24 | Recommendation priority | Doc 05 §4, doc 07 §5 | **PROVISIONAL**: by order of the official `recommended_actions` (1st `high`, 2nd `medium`, rest `low`); the PDF defines no priority |
| D-25 | Who may raise a conflict (protocol 1.2) | Doc 05 §19, doc 03 §3 | **PROVISIONAL** (prompt-pack default; owner may switch to "any specialist"): only `correlation_agent` sends `conflict_report`; the orchestrator relays it to the named party and enforces the rules (guard pre-check); only that party answers with `conflict_response` |
| D-26 | Dashboard placement of simulated switches on the IIT BBS campus artwork | Doc 11, dashboard | **PROVISIONAL** (owner choice, option 1): frontend table dashboard/src/campus/placement.ts maps each simulated zone to a campus building; drawn with "Simulated network, illustrative placement, not real switch locations."; backend schematic layout unchanged |

## 8. Assumptions and explicit non-assumptions

**Assumptions** (`INTERPRETATION`)
- A-1: The deliverable repository will be hosted on GitHub (`SRC-1 p6 §7.1`).
- A-2: `SRC-1` is the current problem statement (PDF metadata shows creation on 2026-10-15).
- A-3: Evaluation judges will inspect the message log and report, not only the final answer.

**We do not assume** — and no document may imply:
- access to IIT Bhubaneswar's network, devices, monitoring platforms or credentials;
- that the generator provides any particular field, unit, topology data, ground truth or DNS/DHCP signal;
- that complaint data is real, or that real students' data will be collected;
- any team roster, role assignment or date.

## 9. Glossary (plain English)

| Term | Meaning |
|---|---|
| Agent | A specialist component with one job: it receives a task, gathers its own evidence with tools, and returns findings with stated uncertainty. |
| Orchestrator | The coordinator. Ordinary code that hands out tasks, enforces limits, and collects results. Not an AI. |
| Deterministic | Same input, same output — so it can be tested exactly. |
| State machine | A program defined by named states and the allowed moves between them. |
| Telemetry | Measurements reported by network devices. |
| Latency / jitter / packet loss | Delay, variation in delay, and share of data that never arrives. |
| Utilization / throughput / bandwidth | How full a link is / how much data actually flows / how much it could carry. |
| Queue drops | Data discarded because a device's outgoing queue was full. |
| Topology | Which devices connect to which. |
| Root cause | The underlying reason for a symptom. |
| Hypothesis | A candidate root cause being weighed against others. |
| Blast radius | Everything that would be affected if one device or link failed. |
| Normalization | Converting differently named or measured data into one agreed form. |
| Not assessable | We cannot judge this metric (missing, unreadable, unclear unit…). Different from "healthy". |
| Heuristic score | A rule-based number that ranks options. Not a statistical probability unless proven against data. |
| Calibrated | A confidence that is validated: of cases scored 0.8, about 80% are really right. We do not claim this yet. |
| Provenance | Where a piece of data came from (synthetic, team-authored, verified…). |
| Candidate incident | A group of similar complaints that may indicate a real problem. Unverified until telemetry agrees. |
| Corroborated | Both complaints and telemetry point to the same place and time. |
| LLM | A large language model used for text tasks. Optional here. |
