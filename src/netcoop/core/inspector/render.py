"""Rendering for the protocol inspector. Every function is pure (log rows in, text out)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from netcoop.core.log_store import LoggedMessage, LogStore
from netcoop.core.vocabulary import get_vocabulary, is_valid

BANNER_TEXT = "SIMULATED DATA - scenario playback"

#: Lanes of the sequence view, in order, with short column titles.
LANES: tuple[tuple[str, str], ...] = (
    ("orchestrator", "orchestrator"),
    ("performance_agent", "performance"),
    ("infrastructure_agent", "infrastructure"),
    ("connectivity_agent", "connectivity"),
    ("correlation_agent", "correlation"),
    ("reporting_agent", "reporting"),
    ("community_module", "community"),
)
_LANE_W = 15
_RED, _GREEN, _DIM, _RESET = "\033[31m", "\033[32m", "\033[2m", "\033[0m"


@dataclass(frozen=True)
class TraceView:
    incident_id: str
    rows: list[LoggedMessage]
    snapshot_id: str | None
    mode: str | None
    data_provenance: str | None
    transitions: int = 0
    filters: dict[str, Any] = field(default_factory=dict)


def load_view(store: LogStore, incident_id: str) -> TraceView:
    rows = store.messages(incident_id)
    accepted = [r for r in rows if r.valid]

    def first(attr: str) -> str | None:
        return next((getattr(r, attr) for r in accepted if getattr(r, attr)), None)

    return TraceView(
        incident_id=incident_id,
        rows=rows,
        snapshot_id=first("snapshot_id"),
        mode=first("mode"),
        data_provenance=first("data_provenance"),
        transitions=len(store.transitions(incident_id)),
    )


def _payload(row: LoggedMessage) -> dict[str, Any]:
    try:
        data = json.loads(row.payload_json or "null")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def summarize(message_type: str | None, payload: dict[str, Any]) -> str:
    """One line describing a message's content (never the raw telemetry)."""
    p = payload
    if message_type == "task_request":
        return (
            f"{p.get('task_kind') or p.get('goal')} task {p.get('task_id') or ''}".rstrip()
            + f", scope {len(p.get('scope_entities', []))} entities, budget {p.get('tool_budget')}"
            + (f", refs {len(p['input_message_ids'])}" if p.get("input_message_ids") else "")
        )
    if message_type == "finding":
        return (
            f"{_n(len(p.get('observations', [])), 'observation')}, "
            f"{_n(len(p.get('hypotheses', [])), 'hypothesis', 'hypotheses')}, "
            f"{len(p.get('not_assessable', []))} not_assessable"
        )
    if message_type == "clarification_request":
        cid = f" {p['clarification_id']}" if p.get("clarification_id") else ""
        return (
            f"{p.get('question_type')} -> {p.get('target')}, round {p.get('round')}"
            f" ({p.get('reason')}){cid}"
        )
    if message_type == "clarification_response":
        answerable = p.get("answerable") or ("yes" if p.get("answered") else "no")
        return f"answerable {answerable}, {_n(len(p.get('observations', [])), 'observation')}"
    if message_type == "decision":
        top: dict[str, Any] = next(
            (h for h in p.get("ranked", []) if h.get("diagnosable", True)), {}
        )
        text = f"{p.get('decision')}"
        if top:
            text += f", top {top.get('cause_type')} score {top.get('score')}"
        text += f" ({p.get('score_method', 'heuristic')})"
        if p.get("abstention"):
            text += f", abstains: {', '.join(p['abstention'].get('reasons', []))}"
        return text
    if message_type == "report_ready":
        rep = p.get("report", {})
        n = len(p.get("recommendations", []))
        return f"report {rep.get('status')}, {_n(n, 'recommendation')}"
    if message_type == "agent_error":
        return f"{p.get('code')}: {p.get('message')}"
    if message_type == "community_candidate":
        return (
            f"{p.get('candidate_id')} in {p.get('zone')}, {p.get('distinct_reporters')} "
            f"reporters ({p.get('trust_label')})"
        )
    return ""


def _clock_time(stamp: str | None) -> str:
    """HH:MM:SS.mmm (ISO strings drop a zero fraction, so never slice them)."""
    if not stamp:
        return ""
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%H:%M:%S.%f")[:-3]
    except ValueError:
        return stamp[:12]


def _n(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


def _reason(row: LoggedMessage) -> str:
    if row.violations:
        return str(row.violations[0].get("reason", ""))
    return row.error_detail or ""


def _visible(
    view: TraceView, *, show_rejected: bool, types: set[str] | None, sender: str | None
) -> list[LoggedMessage]:
    return [
        r
        for r in view.rows
        if (show_rejected or r.valid)
        and (types is None or r.message_type in types)
        and (sender is None or r.sender == sender)
    ]


def banner(view: TraceView) -> str:
    return (
        f"=== incident {view.incident_id} | snapshot {view.snapshot_id or 'none'} | "
        f"mode {view.mode or 'simulation'} | data provenance "
        f"{view.data_provenance or 'unspecified'} | {BANNER_TEXT} ==="
    )


def footer(view: TraceView) -> str:
    accepted = [r for r in view.rows if r.valid]
    by_type = Counter(r.message_type for r in accepted)
    rounds = sum(
        1
        for r in accepted
        if r.message_type == "clarification_request" and r.sender == "correlation_agent"
    )
    types = ", ".join(f"{t} {n}" for t, n in sorted(by_type.items(), key=lambda x: str(x[0])))
    return (
        f"--- {len(view.rows)} messages: {len(accepted)} accepted, "
        f"{len(view.rows) - len(accepted)} rejected | by type: {types or 'none'} | "
        f"clarification rounds used: {rounds} | snapshot {view.snapshot_id or 'none'} ---"
    )


def _paint(text: str, color: str, on: bool) -> str:
    return f"{color}{text}{_RESET}" if on else text


def render_table(
    view: TraceView,
    *,
    show_rejected: bool = False,
    types: set[str] | None = None,
    sender: str | None = None,
    color: bool = False,
) -> str:
    lines = [banner(view), ""]
    lines.append(
        f"{'seq':>4}  {'time':<12}  {'from -> to':<44}  {'type':<23}  "
        f"{'message_id':<24}  {'in_reply_to':<24}  verdict   summary"
    )
    for r in _visible(view, show_rejected=show_rejected, types=types, sender=sender):
        when = _clock_time(r.received_at or r.sent_at)
        route = f"{r.sender or '?'} -> {r.recipient or '?'}"
        verdict = "accepted" if r.valid else "REJECTED"
        summary = (
            summarize(r.message_type, _payload(r)) if r.valid else (f"{r.error_code}: {_reason(r)}")
        )
        line = (
            f"{r.attempt_seq:>4}  {when:<12}  {route:<44}  {r.message_type or '?':<23}  "
            f"{r.message_id or '?':<24}  {r.in_reply_to or '-':<24}  {verdict:<8}  {summary}"
        )
        lines.append(_paint(line, _RED, color) if not r.valid else line)
    lines += ["", footer(view)]
    return "\n".join(lines) + "\n"


def render_sequence(
    view: TraceView,
    *,
    show_rejected: bool = False,
    types: set[str] | None = None,
    sender: str | None = None,
    color: bool = False,
) -> str:
    """Plain-text lanes: one column per participant, one arrow per message, in order."""
    idx = {name: i for i, (name, _) in enumerate(LANES)}
    width = _LANE_W * len(LANES)
    head = "".join(title.center(_LANE_W) for _, title in LANES)
    lines = [
        banner(view),
        "",
        f"{'seq':>4}  {head}",
        f"{'':>4}  " + "".join("|".center(_LANE_W) for _ in LANES),
    ]
    for r in _visible(view, show_rejected=show_rejected, types=types, sender=sender):
        cells = [" "] * width
        for i in range(len(LANES)):
            cells[i * _LANE_W + _LANE_W // 2] = "|"
        a, b = idx.get(r.sender or "", 0), idx.get(r.recipient or "", 0)
        xa, xb = a * _LANE_W + _LANE_W // 2, b * _LANE_W + _LANE_W // 2
        lo, hi = sorted((xa, xb))
        fill = "-" if r.valid else "x"
        for x in range(lo + 1, hi):
            cells[x] = fill
        cells[xb] = (">" if xb > xa else "<") if r.valid else "X"
        cells[xa] = "o"
        label = r.message_type or "?"
        label += "" if r.valid else f"  REJECTED {r.error_code}: {_reason(r)}"
        line = f"{r.attempt_seq:>4}  {''.join(cells)}  {label}"
        lines.append(_paint(line, _RED, color) if not r.valid else line)
    lines += ["", footer(view)]
    return "\n".join(lines) + "\n"


def to_data(
    view: TraceView,
    *,
    show_rejected: bool = True,
    types: set[str] | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    """Structured form of the trace (for the dashboard and API)."""
    rows = _visible(view, show_rejected=show_rejected, types=types, sender=sender)
    accepted = [r for r in view.rows if r.valid]
    return {
        "banner": {
            "incident_id": view.incident_id,
            "snapshot_id": view.snapshot_id,
            "mode": view.mode or "simulation",
            "data_provenance": view.data_provenance or "unspecified",
            "label": BANNER_TEXT,
        },
        "messages": [
            {
                "seq": r.attempt_seq,
                "protocol_seq": r.protocol_seq,
                "received_at": r.received_at,
                "sender": r.sender,
                "recipient": r.recipient,
                "message_type": r.message_type,
                "message_id": r.message_id,
                "in_reply_to": r.in_reply_to,
                "verdict": r.verdict,
                "summary": summarize(r.message_type, _payload(r)) if r.valid else None,
                "violations": r.violations,
                "warnings": r.warnings,
            }
            for r in rows
        ],
        "footer": {
            "messages": len(view.rows),
            "accepted": len(accepted),
            "rejected": len(view.rows) - len(accepted),
            "by_type": dict(sorted(Counter(str(r.message_type) for r in accepted).items())),
            "clarification_rounds": sum(
                1
                for r in accepted
                if r.message_type == "clarification_request" and r.sender == "correlation_agent"
            ),
            "snapshot_id": view.snapshot_id,
        },
    }


def render_json(view: TraceView, **filters: Any) -> str:
    return json.dumps(to_data(view, **filters), indent=2, sort_keys=True) + "\n"


# ------------------------------------------------------------------ evidence chain


def _observations(view: TraceView) -> dict[str, tuple[dict[str, Any], LoggedMessage]]:
    out: dict[str, tuple[dict[str, Any], LoggedMessage]] = {}
    for r in view.rows:
        if r.valid:
            for o in _payload(r).get("observations", []):
                out.setdefault(str(o.get("observation_id")), (o, r))
    return out


def evidence_chain(view: TraceView, hypothesis_id: str) -> str:
    """hypothesis -> evidence refs -> observations -> source records -> data snapshot.
    A reference that does not resolve is stated explicitly."""
    lines = [banner(view), ""]
    found = None
    for r in view.rows:
        if r.valid:
            for h in _payload(r).get("hypotheses", []):
                if h.get("hypothesis_id") == hypothesis_id:
                    found = (h, r)
    if found is None:
        lines += [
            f"UNRESOLVED: hypothesis {hypothesis_id} is not in any accepted message of "
            f"incident {view.incident_id}.",
            "",
            footer(view),
        ]
        return "\n".join(lines) + "\n"
    h, msg = found
    obs = _observations(view)
    lines.append(
        f"hypothesis {hypothesis_id}: {h.get('cause_type')} on {', '.join(h.get('entities', []))}"
        f" (local score {h.get('local_score')}, {h.get('score_method', 'agent_local_heuristic')})"
        f" from {msg.sender} in {msg.message_id}"
    )
    refs = [("supports", e) for e in h.get("supporting", [])] + [
        ("contradicts", e) for e in h.get("contradicting", [])
    ]
    if not refs:
        refs = [
            ("supports", {"evidence_type": "observation", "evidence_id": i})
            for i in h.get("supporting_observation_ids", [])
        ]
    for stance, ref in refs:
        eid = str(ref.get("evidence_id"))
        lines.append(f"  {stance}: {ref.get('evidence_type')} {eid}")
        if ref.get("evidence_type") != "observation":
            lines.append("    (not an observation: shown as referenced)")
            continue
        hit = obs.get(eid)
        if hit is None:
            lines.append(f"    UNRESOLVED: observation {eid} is not in this incident's messages")
            continue
        o, carrier = hit
        lines.append(
            f"    observation {eid}: {o.get('entity')} {o.get('metric')} = {o.get('value')} "
            f"{o.get('unit') or ''} ({o.get('severity')}, {o.get('assessability')}) "
            f"in {carrier.message_id}"
        )
        sources = o.get("source_ref") or []
        lines.append(f"      source records: {', '.join(sources) if sources else 'none listed'}")
        lines.append(f"      data snapshot: {carrier.snapshot_id or 'UNRESOLVED (no snapshot id)'}")
    if h.get("missing_expected_evidence"):
        lines.append(f"  missing expected evidence: {', '.join(h['missing_expected_evidence'])}")
    lines += ["", footer(view)]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ explain

#: Field name -> vocabularies it may belong to (first one holding the value wins).
FIELD_VOCABULARIES: dict[str, tuple[str, ...]] = {
    "sender": ("agent",),
    "recipient": ("agent",),
    "target": ("agent",),
    "agent": ("agent",),
    "source": ("agent",),
    "message_type": ("message_type",),
    "status": ("message_status", "report_status"),
    "mode": ("mode",),
    "data_provenance": ("data_provenance",),
    "cause_type": ("cause_type",),
    "severity": ("severity",),
    "assessability": ("assessability",),
    "not_assessable_reason": ("not_assessable_reason",),
    "reason": ("not_assessable_reason", "clarification_reason"),
    "metric": ("metric",),
    "unit": ("unit",),
    "evidence_type": ("evidence_type",),
    "stance": ("evidence_stance",),
    "question_type": ("question_type",),
    "decision": ("decision_kind",),
    "score_method": ("score_method",),
    "confidence_category": ("confidence_category",),
    "task_kind": ("task_kind",),
    "aggregation": ("aggregation",),
    "kind": ("recommendation_mode",),
    "priority": ("recommendation_priority",),
    "trust_label": ("trust_label",),
    "rationale_code": ("rationale_code",),
    "code": ("error_code",),
    "reasons": ("abstention_reason",),
    "entity_type": ("entity_type",),
}


def _walk(node: Any, path: str, out: list[tuple[str, str, str]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            sub = f"{path}.{k}" if path else k
            vocabs = FIELD_VOCABULARIES.get(k)
            values = v if isinstance(v, list) and all(isinstance(x, str) for x in v) else [v]
            if vocabs:
                for value in values:
                    if isinstance(value, str):
                        voc = next((n for n in vocabs if is_valid(n, value)), None)
                        if voc:
                            out.append((sub, value, voc))
            if isinstance(v, dict | list):
                _walk(v, sub, out)
    elif isinstance(node, list):
        for i, x in enumerate(node):
            _walk(x, f"{path}[{i}]", out)


def explain_message(view: TraceView, message_id: str) -> str:
    """The full message, then every vocabulary-controlled field with its definition (and,
    for metrics, its unit and problem-statement category): field meanings and units."""
    lines = [banner(view), ""]
    rows = [r for r in view.rows if r.message_id == message_id]
    if not rows:
        lines += [
            f"UNRESOLVED: message {message_id} is not in incident {view.incident_id}.",
            "",
            footer(view),
        ]
        return "\n".join(lines) + "\n"
    row = next((r for r in rows if r.valid), rows[-1])
    lines.append(f"message {message_id} ({row.message_type}, {row.verdict}, seq {row.attempt_seq})")
    if not row.valid:
        for v in row.violations:
            lines.append(f"  REJECTED {v.get('code')}: {v.get('reason')}")
    try:
        doc: Any = json.loads(row.raw_json)
        lines.append(json.dumps(doc, indent=2, sort_keys=True))
    except json.JSONDecodeError:
        doc = None
        lines.append(row.raw_json)
    lines += ["", "Field meanings (from the controlled vocabularies):"]
    found: list[tuple[str, str, str]] = []
    _walk(doc, "", found)
    seen: set[tuple[str, str]] = set()
    for path, value, voc in found:
        if (voc, value) in seen:
            continue
        seen.add((voc, value))
        term = get_vocabulary(voc).term(value)
        extra = ""
        if voc == "metric":
            a = term.attributes
            extra = f" [unit {a.get('unit')}, category {a.get('category')}]"
        lines.append(f"  {path} = {value}  ({voc}): {term.definition}{extra}")
    if len(found) == 0:
        lines.append("  (no vocabulary-controlled fields)")
    lines += ["", footer(view)]
    return "\n".join(lines) + "\n"
