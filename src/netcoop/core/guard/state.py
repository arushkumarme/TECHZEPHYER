"""Per-incident conversation state: what has been asked and answered so far.

Immutable: :meth:`ConversationState.apply` returns a NEW state, so checking a message can
never change anything, and replaying the same accepted messages from a fresh state always
gives an identical (JSON-serializable) state.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from netcoop.core.guard.rules import AuthorityRules, load_rules
from netcoop.core.messages import Envelope


class OpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    recipient: str
    kind: str | None = None


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str | None = None
    incident_state: str | None = Field(
        default=None, description="Current incident state (doc 04 §2), from the orchestrator"
    )
    closed: bool = False
    seen_message_ids: tuple[str, ...] = ()
    open_tasks: dict[str, OpenRequest] = Field(default_factory=dict)
    #: The correlation agent's questions not yet relayed: message id -> target named.
    pending_questions: dict[str, str] = Field(default_factory=dict)
    #: Relayed questions not yet answered: relay message id -> target it went to.
    relayed_questions: dict[str, str] = Field(default_factory=dict)
    clarification_rounds: int = 0
    decision_sent: bool = False
    report_sent: bool = False

    def with_incident_state(
        self, state: str | None, rules: AuthorityRules | None = None
    ) -> ConversationState:
        rules = rules or load_rules()
        return self.model_copy(
            update={"incident_state": state, "closed": state in rules.closed_states}
        )

    def apply(self, msg: Envelope, rules: AuthorityRules | None = None) -> ConversationState:
        """The state after an ACCEPTED message (never called for a rejected one)."""
        hub = (rules or load_rules()).hub
        tasks = dict(self.open_tasks)
        pending = dict(self.pending_questions)
        relayed = dict(self.relayed_questions)
        update: dict[str, Any] = {
            "incident_id": self.incident_id or msg.incident_id,
            "seen_message_ids": (*self.seen_message_ids, msg.message_id),
        }
        t, irt, p = msg.message_type, msg.in_reply_to, msg.payload
        if t == "task_request":
            tasks[msg.message_id] = OpenRequest(recipient=msg.recipient, kind=p.get("task_kind"))
        elif t == "clarification_request" and msg.sender == hub:
            if irt is not None:
                pending.pop(irt, None)
            relayed[msg.message_id] = msg.recipient
        elif t in ("finding", "decision", "report_ready", "clarification_request"):
            if irt is not None:
                tasks.pop(irt, None)
            if t == "clarification_request":
                pending[msg.message_id] = str(p.get("target"))
                update["clarification_rounds"] = self.clarification_rounds + 1
            update["decision_sent"] = self.decision_sent or t == "decision"
            update["report_sent"] = self.report_sent or t == "report_ready"
        elif t == "clarification_response" and irt is not None:
            relayed.pop(irt, None)
        elif t == "agent_error" and irt is not None:
            for open_map in (tasks, pending, relayed):
                open_map.pop(irt, None)
        update |= {"open_tasks": tasks, "pending_questions": pending, "relayed_questions": relayed}
        return self.model_copy(update=update)


def rebuild_state(
    messages: Iterable[Envelope],
    *,
    incident_state: str | None = None,
    rules: AuthorityRules | None = None,
) -> ConversationState:
    """Replay accepted messages (in log order) from a fresh state."""
    state = ConversationState()
    for m in messages:
        state = state.apply(m, rules)
    return state.with_incident_state(incident_state, rules)
