"""The conversation guard: checks one message against the authority matrix and the
conversation so far. Pure: it never changes the message or the state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from netcoop.core.guard.rules import AuthorityRow, AuthorityRules, load_rules
from netcoop.core.guard.state import ConversationState
from netcoop.core.messages import Envelope

#: Old code -> the code emitted now (MESSAGE_ROUTING_INVALID is a deprecated term).
DEPRECATED_CODE_ALIASES = {"MESSAGE_ROUTING_INVALID": "DIRECT_AGENT_MESSAGE_FORBIDDEN"}


@dataclass(frozen=True)
class Violation:
    code: str
    reason: str


@dataclass(frozen=True)
class GuardResult:
    violations: tuple[Violation, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return not self.violations


def _either(names: Iterable[str]) -> str:
    items = sorted(set(names))
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


class ConversationGuard:
    def __init__(
        self,
        rules: AuthorityRules | None = None,
        *,
        max_clarification_rounds: int = 2,
        extensions: Iterable[str] = (),
    ) -> None:
        self.rules = rules or load_rules()
        self.max_rounds = max_clarification_rounds
        self.extensions = frozenset(extensions)

    def check(self, msg: Envelope, state: ConversationState) -> GuardResult:
        v: list[Violation] = []
        s, r, t = msg.sender, msg.recipient, msg.message_type
        hub = self.rules.hub
        if state.closed:
            return GuardResult(
                (
                    Violation(
                        "INCIDENT_CLOSED",
                        f"Rejected: incident {state.incident_id or msg.incident_id} is closed "
                        f"({state.incident_state}); no further messages are accepted.",
                    ),
                )
            )
        if msg.message_id in state.seen_message_ids:
            v.append(
                Violation(
                    "DUPLICATE_MESSAGE",
                    f"Rejected: message id {msg.message_id} was already accepted in this incident.",
                )
            )
        if hub not in (s, r):
            v.append(
                Violation(
                    "DIRECT_AGENT_MESSAGE_FORBIDDEN",
                    f"Rejected: {s} tried to message {r} directly; agents talk only through "
                    f"the {hub}.",
                )
            )
            return GuardResult(tuple(v))
        if s == r:
            v.append(Violation("RECIPIENT_NOT_ALLOWED", f"Rejected: {s} cannot message itself."))
            return GuardResult(tuple(v))

        rows = self.rules.rows_for(t)
        by_sender = [row for row in rows if s in row.senders]
        if not by_sender:
            senders = {x for row in rows for x in row.senders}
            v.append(
                Violation(
                    "SENDER_NOT_AUTHORIZED",
                    f"Rejected: only {_either(senders)} may send a {t}; {s} tried.",
                )
            )
            return GuardResult(tuple(v))
        matching = [row for row in by_sender if r in row.recipients]
        if not matching:
            allowed = {x for row in by_sender for x in row.recipients}
            v.append(
                Violation(
                    "RECIPIENT_NOT_ALLOWED",
                    f"Rejected: a {t} from {s} may go only to {_either(allowed)}; it was "
                    f"addressed to {r}.",
                )
            )
            return GuardResult(tuple(v))
        row = matching[0]
        v += self._row_checks(row, msg, state)
        return GuardResult(tuple(v))

    def _row_checks(
        self, row: AuthorityRow, msg: Envelope, state: ConversationState
    ) -> list[Violation]:
        v: list[Violation] = []
        s, r, t = msg.sender, msg.recipient, msg.message_type
        if t == "task_request":
            kind = msg.payload.get("task_kind")
            if kind is not None and row.task_kind is not None and kind != row.task_kind:
                v.append(
                    Violation(
                        "RECIPIENT_NOT_ALLOWED",
                        f"Rejected: {r} takes {row.task_kind} tasks, not {kind} tasks.",
                    )
                )
        if row.extension is not None and row.extension not in self.extensions:
            v.append(
                Violation(
                    "EXTENSION_DISABLED",
                    f"Rejected: a {t} belongs to the {row.extension} extension, which is "
                    "switched off.",
                )
            )
        if (
            not row.any_state()
            and state.incident_state is not None
            and state.incident_state not in row.states
        ):
            v.append(
                Violation(
                    "MESSAGE_OUT_OF_SEQUENCE",
                    f"Rejected: a {t} from {s} is allowed only while the incident is "
                    f"{_either(row.states)}; it is {state.incident_state}.",
                )
            )
        if row.once and (
            (t == "decision" and state.decision_sent) or (t == "report_ready" and state.report_sent)
        ):
            v.append(
                Violation(
                    "MESSAGE_OUT_OF_SEQUENCE",
                    f"Rejected: only one {t} is allowed per incident and one was already accepted.",
                )
            )
        if row.requires_decision and not state.decision_sent:
            v.append(
                Violation(
                    "MESSAGE_OUT_OF_SEQUENCE", f"Rejected: a {t} needs an accepted decision first."
                )
            )
        v += self._reply_checks(row, msg, state)
        if row.counts_round and state.clarification_rounds >= self.max_rounds:
            v.append(
                Violation(
                    "CLARIFICATION_LIMIT_EXCEEDED",
                    f"Rejected: clarification round {state.clarification_rounds + 1} exceeds the "
                    f"limit of {self.max_rounds} rounds per incident.",
                )
            )
        return v

    def _reply_checks(
        self, row: AuthorityRow, msg: Envelope, state: ConversationState
    ) -> list[Violation]:
        s, r, t, irt = msg.sender, msg.recipient, msg.message_type, msg.in_reply_to

        def bad(text: str) -> list[Violation]:
            return [Violation("REPLY_MISMATCH", f"Rejected: {text}")]

        if row.reply == "none":
            return bad(f"a {t} starts a conversation and cannot reply to {irt}.") if irt else []
        if row.reply == "optional":
            if irt is not None and irt not in state.seen_message_ids:
                return bad(f"{t} refers to {irt}, which is not a message of this incident.")
            return []
        if irt is None:
            return bad(f"a {t} must reply to the message it answers; in_reply_to is missing.")
        if row.reply == "task_request":
            task = state.open_tasks.get(irt)
            if task is None or task.recipient != s:
                return bad(f"{irt} is not an open task_request addressed to {s}.")
            if row.task_kind and task.kind and task.kind != row.task_kind:
                return bad(f"a {t} answers a {row.task_kind} task; {irt} is a {task.kind} task.")
            return []
        if row.reply == "question":
            if state.pending_questions.get(irt) != r:
                return bad(f"{irt} is not an open question from the correlation agent for {r}.")
            return []
        # relayed_question
        if state.relayed_questions.get(irt) != s:
            return bad(f"{irt} is not a question that was relayed to {s}.")
        return []
