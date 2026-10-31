"""Human-in-the-loop review of recommendations (component 9; doc 04 §3 step 10, doc 12 §3).

Recommendations are suggestions that *require human approval*. A reviewer approves or
rejects each one; the decision (who, when, what, why) is appended to the ``approvals``
table. Approval triggers only a **simulated** outcome (:mod:`netcoop.remediation`). When
every recommendation has been decided, a new report version records the decisions and the
incident moves ``AWAITING_REVIEW -> COMPLETE``. Review never changes the diagnosis.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Literal

from netcoop.core.ids import Clock, SystemClock
from netcoop.core.log_store import LogStore
from netcoop.orchestrator.states import check_transition
from netcoop.remediation.simulator import simulate_action
from netcoop.report.markdown import render_markdown

Choice = Literal["approve", "reject"]


class ReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PendingAction:
    index: int
    action: str
    approval_state: str
    reviewer: str | None = None


@dataclass(frozen=True)
class ApprovalRecord:
    incident_id: str
    action_index: int
    action: str
    decision: Choice
    reviewer: str
    note: str
    decided_at: str
    simulated_outcome: str | None


class ReviewService:
    def __init__(self, store: LogStore, *, clock: Clock | None = None) -> None:
        self.store = store
        self.clock: Clock = clock or SystemClock()

    def state(self, incident: str) -> str | None:
        t = self.store.transitions(incident)
        return t[-1].to_state if t else None

    def _report(self, incident: str) -> dict[str, Any]:
        stored = self.store.latest_report(incident)
        if stored is None:
            raise ReviewError(f"{incident} has no report")
        return stored[0]

    def pending(self, incident: str) -> list[PendingAction]:
        report = self._report(incident)
        decided = {a["action_index"]: a for a in self.store.approvals(incident)}
        out = []
        for i, action in enumerate(report["recommended_actions"]):
            a = decided.get(i)
            if a is None:
                state = "pending"
            else:
                state = "approved" if a["decision"] == "approve" else "rejected"
            out.append(PendingAction(i, action, state, a["reviewer"] if a else None))
        return out

    def decide(
        self, incident: str, index: int, decision: Choice, *, reviewer: str, note: str = ""
    ) -> ApprovalRecord:
        state = self.state(incident)
        if state != "AWAITING_REVIEW":
            raise ReviewError(f"{incident} is {state}; decisions are only taken in AWAITING_REVIEW")
        if decision not in ("approve", "reject"):
            raise ReviewError(f"decision must be approve or reject, not {decision!r}")
        if not reviewer.strip():
            raise ReviewError("a reviewer name is required (who decided is recorded)")
        report = self._report(incident)
        actions: list[str] = report["recommended_actions"]
        if not 0 <= index < len(actions):
            raise ReviewError(f"{incident} has no recommendation [{index}]")
        if any(a["action_index"] == index for a in self.store.approvals(incident)):
            raise ReviewError(f"recommendation [{index}] of {incident} was already decided")
        cause = report.get("netcoop_extensions", {}).get("top_cause_type")
        outcome = simulate_action(actions[index], cause) if decision == "approve" else None
        record = ApprovalRecord(
            incident_id=incident,
            action_index=index,
            action=actions[index],
            decision=decision,
            reviewer=reviewer.strip(),
            note=note,
            decided_at=self.clock.now().isoformat(),
            simulated_outcome=outcome,
        )
        self.store.append_approval(asdict(record))
        if len(self.store.approvals(incident)) == len(actions):
            self._complete(incident, report)
        return record

    def _complete(self, incident: str, report: dict[str, Any]) -> None:
        decided = {a["action_index"]: a for a in self.store.approvals(incident)}
        updated = copy.deepcopy(report)
        ext = updated.setdefault("netcoop_extensions", {})
        status = []
        for i, action in enumerate(updated["recommended_actions"]):
            a = decided[i]
            status.append(
                {
                    "action": action,
                    "requires_human_approval": True,
                    "approval_state": "approved" if a["decision"] == "approve" else "rejected",
                    "reviewer": a["reviewer"],
                    "decided_at": a["decided_at"],
                    "note": a["note"],
                    "simulated": True,
                    "simulated_outcome": a["simulated_outcome"],
                }
            )
        ext["recommendation_status"] = status
        now = self.clock.now()
        ext["review_completed_at"] = now.isoformat()
        self.store.append_report(incident, updated, render_markdown(updated), at=now)
        check_transition("AWAITING_REVIEW", "COMPLETE")
        approved = sum(1 for s in status if s["approval_state"] == "approved")
        self.store.append_transition(
            incident,
            "AWAITING_REVIEW",
            "COMPLETE",
            trigger="review_complete",
            at=now,
            detail={"approved": approved, "rejected": len(status) - approved},
        )
