"""Render the authority matrix and conversation rules for docs/05 (generated block)."""

from __future__ import annotations

from netcoop.core.guard.rules import AuthorityRules, load_rules

AUTHORITY_BEGIN = "<!-- BEGIN GENERATED: authority -->"
AUTHORITY_END = "<!-- END GENERATED: authority -->"

_REPLY_TEXT = {
    "none": "starts a conversation (no `in_reply_to`)",
    "task_request": "answers an open `task_request` addressed to the sender",
    "question": "relays the correlation agent's open question to the target it names",
    "relayed_question": "answers the question relayed to the sender",
    "optional": "may reply to any earlier message of the incident",
}


def _names(items: tuple[str, ...], specialists: tuple[str, ...]) -> str:
    if set(specialists) <= set(items) and len(items) == len(specialists):
        return "specialists"
    return ", ".join(f"`{i}`" for i in items)


def render_authority(rules: AuthorityRules | None = None) -> str:
    rules = rules or load_rules()
    spec = rules.groups.get("specialists", ())
    lines = [
        AUTHORITY_BEGIN,
        "",
        "### Authority matrix",
        "",
        "Specialists = `performance_agent`, `infrastructure_agent`, `connectivity_agent`. "
        f"Source: `config/protocol/authority.toml` (version {rules.version}).",
        "",
        "| Message type | Sender | Recipient | Incident states | Reply rule | Other |",
        "|---|---|---|---|---|---|",
    ]
    for r in rules.rows:
        other = [
            *([f"task kind `{r.task_kind}`"] if r.task_kind else []),
            *(["once per incident"] if r.once else []),
            *(["after a decision"] if r.requires_decision else []),
            *(["counts toward the round limit"] if r.counts_round else []),
            *([f"extension `{r.extension}` must be on"] if r.extension else []),
        ]
        states = "any open state" if r.any_state() else ", ".join(f"`{s}`" for s in r.states)
        lines.append(
            f"| `{r.message_type}` | {_names(r.senders, spec)} | {_names(r.recipients, spec)} "
            f"| {states} | {_REPLY_TEXT[r.reply]} | {'; '.join(other) or '-'} |"
        )
    closed = ", ".join(f"`{s}`" for s in rules.closed_states)
    lines += [
        "",
        "### Conversation rules",
        "",
        "Checked in this order; every rejection is logged with its code and a plain-English "
        "reason.",
        "",
        f"1. **Closed incident** — nothing is accepted once the incident is {closed} "
        "(`INCIDENT_CLOSED`).",
        "2. **No duplicates** — a message id is accepted once per incident (`DUPLICATE_MESSAGE`).",
        f"3. **Hub and spoke** — every message is to or from the `{rules.hub}`; agents never "
        "message each other (`DIRECT_AGENT_MESSAGE_FORBIDDEN`), and nobody messages itself "
        "(`RECIPIENT_NOT_ALLOWED`).",
        "4. **Authority** — only the senders in the matrix may send a type "
        "(`SENDER_NOT_AUTHORIZED`), and only to its recipients (`RECIPIENT_NOT_ALLOWED`).",
        "5. **Extensions** — extension messages need their feature flag (`EXTENSION_DISABLED`).",
        "6. **Sequence** — a type is legal only in its incident states, `decision` and "
        "`report_ready` at most once, `report_ready` only after a decision "
        "(`MESSAGE_OUT_OF_SEQUENCE`).",
        "7. **Replies** — a reply must answer an open request addressed to its sender; a "
        "relayed question must name the target of the correlation agent's question "
        "(`REPLY_MISMATCH`).",
        "8. **Round limit** — the correlation agent's questions count toward "
        "`max_clarification_rounds` (default 2) per incident "
        "(`CLARIFICATION_LIMIT_EXCEEDED`).",
        "",
        AUTHORITY_END,
    ]
    return "\n".join(lines)
