# 15 — Future Campus Deployment (Design Notes)

> Version 0.1 · 2026-10-31 · `FUTURE` — **nothing in this file is implemented or promised.** Every item that touches the real network is `NEEDS-ACCESS`: it requires authorization from, and cooperation with, the IIT Bhubaneswar network team. We have no such access and no contact is assumed (D-13).

## 1. What stays the same

The agents, message protocol, report format, scoring structure and safety rules are mode-independent ([doc 02 §5](02-architecture.md)). Deployment mode replaces data sources and adds operational controls; it is not a redesign.

## 2. What would have to change

| Area | Hackathon mode | Deployment mode | Dependency |
|---|---|---|---|
| Telemetry sources | Synthetic files | Adapters for whatever monitoring systems and device interfaces the campus actually uses — **unknown to us** | `NEEDS-ACCESS` |
| Topology and inventory | Simulated | Verified inventory with device roles, locations, redundancy | `NEEDS-ACCESS` |
| Field dictionary | From the generator | From the real sources; new aliases and unit rules | `NEEDS-ACCESS` |
| Baselines and thresholds | Set on synthetic data | Learned and reviewed on real, long-run data | `NEEDS-ACCESS` |
| Confidence | Heuristic, uncalibrated | Validated against labelled real incidents before any "calibrated" claim | needs real incident history |
| Complaints | Synthetic via web form | Authorized channels (web form; Telegram; WhatsApp Business) with privacy review | `NEEDS-ACCESS`, institutional approval |
| Map | Simulated positions | Verified building and device geometry | `NEEDS-ACCESS` |
| Remediation | Simulated | Not proposed; any change execution needs change control, rollback and explicit authorization | out of scope |

## 3. Production-readiness gaps

- **Security:** authentication and role-based access, audit of who approved what, secret management, hardening of intake endpoints, rate limiting.
- **Data governance:** retention limits, access rules for complaint data, review of what telemetry may be stored.
- **Reliability:** persistent storage beyond SQLite where needed, restart/resume of in-flight incidents, health monitoring of the diagnosis system itself.
- **Scale:** many concurrent incidents and far larger topologies; not tested or targeted in the hackathon.
- **Quality:** continuous evaluation on real incidents; drift in baselines; maintenance of the hypothesis catalog.
- **Agent transport:** the in-process bus could be replaced by a networked transport without changing the envelope (`FUTURE`; not planned now).

## 4. Suggested adoption path (`PROPOSAL`)

1. **Offline replay:** run on exported historical data approved by the network team.
2. **Shadow/advisory mode:** read-only, diagnoses shown to engineers, who judge accuracy; collect labelled outcomes.
3. **Calibration:** only then evaluate whether the confidence score can honestly be called calibrated.
4. **Assisted operations:** recommendations in the existing ticketing/runbook flow with human approval. Automated change execution is not recommended without a separate safety case.

## 5. Questions for the network team (all `UNKNOWN` today)

1. Which monitoring and telemetry systems exist, and what data may be shared?
2. Is there an authoritative device and link inventory, and who owns it?
3. How are building/zone/hostel names mapped to network segments?
4. What data-protection rules cover student complaints and device logs?
5. Which complaint channels are acceptable to the institution?
6. Who may approve operational recommendations, and through which process?
7. Is there an incident history with confirmed causes we could validate against?
