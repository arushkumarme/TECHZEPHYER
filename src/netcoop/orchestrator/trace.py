"""Render an incident's state transitions and messages as a readable trace (doc 04 §7).

The trace is the visible evidence of agent behaviour (doc 03 §1): task → tool calls →
finding → clarification → decision → report.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from netcoop.core.log_store import LogStore
from netcoop.ingestion.normalize import parse_timestamp


def _summary(mtype: str | None, payload: dict[str, Any]) -> str:
    if mtype == "task_request":
        return (
            f"goal={payload.get('goal')} scope={len(payload.get('scope_entities', []))} "
            f"budget={payload.get('tool_budget')}"
        )
    if mtype == "finding":
        tools = [t["tool"] for t in payload.get("tool_calls", [])]
        hyps = sorted({h["cause_type"] for h in payload.get("hypotheses", [])})
        return (
            f"{len(payload.get('observations', []))} observations, "
            f"{len(payload.get('not_assessable', []))} not assessable, hypotheses={hyps}, "
            f"tool calls={tools}"
        )
    if mtype in ("clarification_request",):
        return (
            f"{payload.get('question_type')} -> {payload.get('target')} "
            f"{payload.get('parameters')} (reason: {payload.get('reason')})"
        )
    if mtype == "clarification_response":
        return f"answered={payload.get('answered')} " + (
            str(payload.get("result"))
            if payload.get("result")
            else f"{len(payload.get('observations', []))} observation(s)"
        )
    if mtype == "decision":
        top: dict[str, Any] = next(
            (h for h in payload.get("ranked", []) if h.get("diagnosable")), {}
        )
        return (
            f"{payload.get('decision')} top={top.get('cause_type')} {top.get('entities')} "
            f"confidence={payload.get('confidence')} margin={payload.get('margin')}"
        )
    if mtype == "report_ready":
        rep = payload.get("report", {})
        return f"status={rep.get('status')} cause={rep.get('suspected_root_cause')!r}"
    if mtype == "agent_error":
        return f"{payload.get('code')}: {payload.get('message')}"
    return ""


def render_trace(store: LogStore, incident_id: str) -> str:
    events: list[tuple[str, int, str]] = []
    for t in store.transitions(incident_id):
        extra = f" {json.dumps(t.detail, sort_keys=True)}" if t.detail else ""
        events.append(
            (t.at, 0, f"[state] {t.from_state or '-'} -> {t.to_state} ({t.trigger}){extra}")
        )
    for m in store.messages(incident_id):
        envelope: dict[str, Any] = {}
        try:
            loaded = json.loads(m.raw_json)
            envelope = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            envelope = {}
        payload = envelope.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        flag = "" if m.valid else f"  ** INVALID: {m.error_code} **"
        seq = envelope.get("seq")
        # Protocol 1.1 stamp: which data snapshot (and provenance) the message refers to.
        stamp = (
            f"  [{envelope['snapshot_id']} {envelope.get('data_provenance', '?')}]"
            if envelope.get("snapshot_id")
            else ""
        )
        events.append(
            (
                m.sent_at or "",
                1,
                f"[msg]   seq={seq if seq is not None else '-'} {m.message_id} {m.sender} -> "
                f"{m.recipient} {m.message_type}: {_summary(m.message_type, payload)}"
                f"{flag}{stamp}",
            )
        )

    # Transitions store "+00:00" and messages "Z": compare as datetimes, not strings.
    def when(at: str) -> datetime:
        return parse_timestamp(at) or datetime.min.replace(tzinfo=UTC)

    events.sort(key=lambda e: (when(e[0]), e[1]))
    lines = [f"{when(at).strftime('%H:%M:%S.%f')[:-3]}  {line}" for at, _, line in events]
    return "\n".join(lines) + "\n"


def summarize_message(message_type: str | None, payload: dict[str, Any]) -> str:
    """One-line human summary of a message payload (used by the trace and the API)."""
    return _summary(message_type, payload)
