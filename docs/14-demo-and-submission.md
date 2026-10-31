# 14 — Demo and Submission

> Version 0.1 · 2026-10-31 · Draft for review · Deadline and team: **TBD**. Scenario availability depends on the generator ([doc 06](06-field-dictionary.md)); segments below refer to scenario *slots* in [doc 09](09-scenarios-and-testing.md).

## 1. Submission deliverables (`SRC-1 p6 §7`)

| ID | Deliverable | Status |
|---|---|---|
| DLV-1 | GitHub repository: implementation, dependencies, setup instructions, test scripts | Not started |
| DLV-2 | Architecture README: agent responsibilities, communication interfaces, orchestration, evidence correlation, error handling, workflow | Skeleton README + docs written (design only) |
| DLV-3 | Sample data and test cases: normal operation and multiple fault scenarios | Not started — needs generator |
| DLV-4 | Demo video, 3–5 minutes: end-to-end diagnosis, inter-agent communication, final report | Not started |
| DLV-5 | Working prototype: CLI with optional dashboard demonstrating the complete workflow | Not started |

## 2. Demo script (target 4:30, limit 5:00)

The demo shows the mandatory workflow first; extensions come after. Every segment states that data is simulated.

| Time | ID | Segment | Shows | Requirements |
|---|---|---|---|---|
| 0:00–0:15 | — | Opening | What NetCoop AI is and is not; "simulated data — scenario playback" | R-17 |
| 0:15–0:40 | Demo-1 | Normal operation, one-command reproducible run | `no_fault_detected` with coverage stated; no false alarm | R-14, M-06 |
| 0:40–1:50 | Demo-2 | Fault scenario end-to-end with trace | Tasks → tool calls → findings → clarification → decision → report; evidence from ≥2 agents; alternatives; confidence labelled heuristic | R-01..R-12, M-01..M-03, M-05 |
| 1:50–2:25 | Demo-3 / Demo-4 | Partially missing metric; interoperability failure | Accepted with warnings; "not assessable"; incompatible input handled; no false network diagnosis | R-13, M-04 |
| 2:25–2:45 | Demo-5 | Insufficient evidence | The system declines to name a cause and says what is missing | R-07, R-16 |
| 2:45–3:30 | Demo-7 | Community flow (extension A) | Two synthetic complaints → candidate incident → investigation → trust label; both `corroborated` and "reported, not verified" outcomes | X-CSI-* |
| 3:30–4:05 | Demo-8 | Map and blast radius (extension B) | Reported vs detected layers; incident panel; isolated vs degraded | X-GEO-* |
| 4:05–4:20 | Demo-6 | Simulated remediation with approval | Recommendation → human approval recorded → simulated outcome | R-20, O-02 |
| 4:20–4:30 | — | Close | Limitations and future deployment (needs network-team access) | — |

**If time is short:** cut Demo-8, then Demo-7, then Demo-6. Never cut Demo-1..5. Without extensions the video is about 3:00.

**Video checklist**
- [ ] Banner "simulated data" visible in every segment
- [ ] Message trace readable on screen
- [ ] Confidence described as a heuristic score
- [ ] No forbidden wording (doc 12 §1)
- [ ] Complaints identified as synthetic test submissions; no WhatsApp integration claimed
- [ ] Length 3:00–5:00

## 3. README review checklist (DLV-2)

- [ ] Each agent: responsibility, inputs, outputs, failure handling (doc 03)
- [ ] Communication interfaces and message formats (doc 05)
- [ ] Orchestration and workflow (doc 04)
- [ ] Evidence correlation and confidence method (doc 08)
- [ ] Error handling (docs 05 §6–7, 09 §5)
- [ ] Status labels: implemented / simulated / future / needs-access
- [ ] Traceability matrix updated with passing tests (doc 01)

## 4. Likely judge questions — prepared answers

| Question | Honest answer (grounded in the docs) |
|---|---|
| Is this real campus data? | No. Synthetic telemetry and simulated topology; we have no access to the campus network. Deployment would need the network team's authorization (doc 15). |
| Is the confidence a probability? | No. It is a documented heuristic score; calibration is claimed only after validation against ground truth (doc 08 §9). |
| Why not let an LLM diagnose? | Diagnosis must be reproducible and testable, and evidence must be traceable. The LLM is optional and only helps with wording and complaint extraction. |
| Are these really agents? | Each takes a task, investigates with tools within a budget, returns an independent finding with stated uncertainty, abstains when it cannot assess, and can ask bounded clarification questions — all visible in the trace (doc 03 §1). Their autonomy is bounded and rule-driven by design. |
| What if telemetry is missing or inconsistent? | Partial gaps are accepted with warnings and marked "not assessable"; missing is never treated as healthy; poor data caps confidence (docs 05, 08). |
| What happens when evidence is insufficient? | Status `insufficient_evidence`; no single cause is asserted; candidates and missing evidence are listed. |
| How are fake or duplicate complaints handled? | Distinct-reporter counting, rate limits, duplicate merging, and complaints can never alone produce a diagnosis (docs 08 §6, 10 §7). |
| Why not WhatsApp? | It needs business verification and institutional authorization. The channel is an adapter; web form works now and WhatsApp is future scope (doc 10 §2). |
| Does it fix problems automatically? | No. Recommendations need recorded human approval and remain simulated (doc 12 §3). |
