# 12 — Safety, Privacy and Simulation Policy

> Version 0.1 · 2026-10-31 · Draft for review · Applies to code, UI, reports, README and the demo video

`SRC-1 p3 §4`: automated remediation "may simulate corrective actions. Do not modify production campus infrastructure without explicit authorization." `SRC-1 p4 §5`: access to the production campus network is not required. `CONFIRMED`

## 1. Honesty about what is simulated

**Rules**

1. Hackathon mode uses synthetic or otherwise authorized data only (`CD-11`). We have no access to IIT Bhubaneswar's production network, devices, monitoring platforms or credentials, and nothing may imply otherwise.
2. Every report states its mode and data provenance; every UI page shows a persistent "simulated data" banner in simulation mode.
3. Simulated devices, links, zones and complaints are labelled wherever shown.
4. Planned or proposed features are never described as implemented. Status words follow doc 00 §2.
5. Names such as "Hostel A" or "HOSTEL_CORE_SW_01" are placeholders unless a verified source says otherwise.

**Wording bank**

| Use | Avoid |
|---|---|
| "scenario playback", "replay of synthetic telemetry" | "live", "real-time monitoring", "currently happening on campus" |
| "probable cause", "likely", "heuristic confidence score" | "exact root cause", "calibrated confidence" (until doc 08 §9 is met) |
| "reported by users (unverified)" | "confirmed outage" for complaint-only incidents |
| "simulated action — requires human approval" | "fixed", "remediated", "automatically resolved" |
| "simulated topology / approximate positions" | "campus network map" without qualification |

## 2. Data policy

- Allowed inputs: generator output, organizer scenarios, team-authored variants (labelled), data from an authorized test environment.
- Not allowed: production captures, credentials, real personal data.
- Complaint and probe data in the demo are synthetic and labelled.

## 3. Remediation and human approval

- The tool layer (doc 02 §2, C-TOOL) has **no write operations**. No code path can change a device.
- Recommendations are suggestions marked *requires human approval*.
- A human may "approve" a recommendation; this records an approval (who, when, what) and shows a **simulated** outcome message. Nothing external happens (`T-SAFE-*`, `T-HITL-*`).
- In deployment mode, any change execution is out of scope and would need authorization, change control and rollback design (doc 15).

## 4. LLM guardrails

- The LLM is optional and provider-independent (`CD-1`); the null provider is the default.
- Allowed uses: complaint-text extraction; reworded narrative in the report.
- Forbidden: choosing the cause, score, status, affected devices; adding evidence; calling tools.
- Output checks: extraction validated against its schema; report wording rejected if it cites a metric, device or number not in the evidence list; fallback to templates on any rejection.
- Inputs treated as untrusted: complaint text, device names, free-text fields in telemetry. They are data, never instructions.
- The report lists which fields, if any, were LLM-reworded.

## 5. Privacy of complaints

- Pseudonymize at intake; strip phone numbers, names and emails from text before storage; minimal retention.
- No real student data in the hackathon. Real collection would need IIT Bhubaneswar authorization and a privacy review (`NEEDS-ACCESS`).
- Complaint data is shown only in aggregate on the map and panel (counts, zone), not individual messages with identifiers.

## 6. Secrets and configuration

- API keys (e.g. an LLM provider) come from environment variables or an untracked local file; never committed.
- `sample_data/` contains no credentials or personal data (`T-DOC-*` checklist).

## 7. Release checklist

- [ ] Banner and provenance visible in UI and reports
- [ ] No forbidden wording (§1) in UI strings, README, video script
- [ ] Official report keys unchanged (`T-RPT-SCHEMA-*`)
- [ ] No community item in official evidence keys
- [ ] Core passes with LLM off and with extensions off
- [ ] No state-changing tool exists (`T-SAFE-*`)
- [ ] No team members, roles or dates invented (`T-DOC-02`)
- [ ] Field dictionary rows all cite a source (`T-DOC-01`)

## 8. Implementation of §3 (M11, 2026-10-31) — `IMPLEMENTED`, `TESTED`

- **Human-in-the-loop** (`src/netcoop/orchestrator/review.py`, CLI `netcoop review | approve | reject INC idx --reviewer NAME [--note …]`): decisions are taken only in `AWAITING_REVIEW`, one per recommendation, never twice, always with a reviewer name; each is appended to the append-only `approvals` table (who, when, what, decision, note). When all are decided a new report version is appended (the original is kept) and the incident moves to `COMPLETE`. Review never alters status, cause or confidence.
- **Simulated remediation** (`src/netcoop/remediation/simulator.py`): approval yields a text outcome that begins `SIMULATED: no device was changed and nothing was sent to any network` and states that real execution needs change control and authorization and that the outcome is unverified.
- **No write path, tested:** the tool layer has no state-changing tool (`T-SAFE-01`); approving with all socket creation monkeypatched to fail succeeds (`T-SAFE-02`); the simulator imports no tools, subprocess, socket or HTTP library (`T-SAFE-03`). Tests: `tests/orchestrator/test_review.py`.

## 9. Implementation of §4 LLM guardrails (M13, 2026-10-31) — `IMPLEMENTED`, `TESTED`

- `src/netcoop/llm/gateway.py`: provider protocol, `NullProvider` (default), `StaticProvider` (deterministic test/demo stand-in). **No real provider is configured** — the owner has not chosen one (D-07) and none is needed by any requirement (KNOWN_ISSUES KI-05).
- The LLM may only reword `netcoop_extensions.narrative`, a deterministic template summary always present in the report. Official keys are never touched: test `test_llm_never_changes_diagnosis` (T-LLM-OFF-01) compares all official keys with the LLM off vs on.
- Grounding check rejects output naming a device, metric or number absent from the report, or using forbidden wording (calibrated, exact, certainly, definitely, confirmed, live, real-time, fixed, remediated, resolved). Rejected / unavailable → template; `llm_assistance` records field, status, provider and reason.
- Complaint text is passed as delimited data (`<summary>…</summary>`), with instructions that it is data, not instructions; the LLM has no tools.
- Provider exception messages are not returned or stored; only the exception type and a generic failure reason are reported, preventing credentials in provider errors from leaking into reports.
- Property test: an LLM that echoes the template is accepted in 8 scenarios, proving the allowed-term set is built correctly.
