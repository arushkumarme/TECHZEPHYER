"""Protocol conformance kit: run messages and conversations through the REAL parser and
conversation guard and compare with the manifest's expectations (doc 05 §17)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from netcoop.core.guard import AuthorityRules, ConversationGuard, ConversationState
from netcoop.core.messages import Envelope, ParsedMessage
from netcoop.core.parse import DEFAULT_MAX_MESSAGE_BYTES, try_parse
from netcoop.core.versioning import PROTOCOL_VERSION
from netcoop.scenarios.generator import REPO_ROOT

KIT_DIR = REPO_ROOT / "conformance"
MANIFEST_PATH = KIT_DIR / "manifest.json"


@dataclass(frozen=True)
class Outcome:
    verdict: str  # accepted | rejected
    codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    failing_index: int | None = None  # conversations: index of the first rejected message
    warnings: list[str] = field(default_factory=list)
    messages_checked: int = 1

    @property
    def code(self) -> str | None:
        return self.codes[0] if self.codes else None


def check_message(raw: Any, *, max_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Outcome:
    r = try_parse(raw, max_bytes=max_bytes)
    warnings = [f"{w.code} {w.path}".strip() for w in r.warnings]
    if r.message is None:
        return Outcome(
            "rejected",
            [e.code for e in r.errors],
            [f"{e.path or '<message>'}: {e.reason}" for e in r.errors],
            warnings=warnings,
        )
    return Outcome("accepted", warnings=warnings)


def check_conversation(doc: dict[str, Any], *, rules: AuthorityRules | None = None) -> Outcome:
    """Each step: ``{"incident_state": ..., "message": {...}}``. Messages are parsed and
    checked by the guard in order; the first rejection ends the conversation."""
    guard = ConversationGuard(
        rules,
        max_clarification_rounds=int(doc.get("max_clarification_rounds", 2)),
        extensions=doc.get("extensions", []),
    )
    state = ConversationState()
    steps = doc["steps"]
    for i, step in enumerate(steps):
        state = state.with_incident_state(step.get("incident_state"), guard.rules)
        r = try_parse(step["message"])
        if r.message is None:
            return Outcome(
                "rejected",
                [e.code for e in r.errors],
                [f"message #{i}: {e.path or '<message>'}: {e.reason}" for e in r.errors],
                i,
                messages_checked=i + 1,
            )
        verdict = guard.check(r.message.envelope, state)
        if not verdict.allowed:
            return Outcome(
                "rejected",
                [v.code for v in verdict.violations],
                [f"message #{i}: {v.reason}" for v in verdict.violations],
                i,
                messages_checked=i + 1,
            )
        state = state.apply(r.message.envelope, guard.rules)
    return Outcome("accepted", messages_checked=len(steps))


def check_file(path: Path, *, max_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> Outcome:
    text = path.read_text(encoding="utf-8")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return check_message(text, max_bytes=max_bytes)
    if isinstance(doc, dict) and "steps" in doc:
        return check_conversation(doc)
    return check_message(text, max_bytes=max_bytes)


@dataclass(frozen=True)
class Result:
    entry: dict[str, Any]
    outcome: Outcome

    @property
    def ok(self) -> bool:
        e, o = self.entry, self.outcome
        if o.verdict != e["expected_verdict"]:
            return False
        if e["expected_verdict"] == "rejected" and o.code != e["expected_code"]:
            return False
        return e.get("failing_index") is None or o.failing_index == e["failing_index"]


def run_manifest(
    manifest_path: Path = MANIFEST_PATH, *, rules: AuthorityRules | None = None
) -> list[Result]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    out = []
    for entry in manifest["examples"]:
        path = base / entry["path"]
        if entry["kind"] == "conversation":
            outcome = check_conversation(json.loads(path.read_text("utf-8")), rules=rules)
        else:
            outcome = check_message(
                path.read_text("utf-8"), max_bytes=entry.get("max_bytes", DEFAULT_MAX_MESSAGE_BYTES)
            )
        out.append(Result(entry, outcome))
    return out


def render_summary(results: list[Result]) -> str:
    def count(kind: str, verdict: str) -> tuple[int, int]:
        rs = [
            r for r in results if r.entry["kind"] == kind and r.entry["expected_verdict"] == verdict
        ]
        return sum(r.ok for r in rs), len(rs)

    va, vt = count("message", "accepted")
    ia, it = count("message", "rejected")
    ca, ct = (
        sum(r.ok for r in results if r.entry["kind"] == "conversation"),
        sum(1 for r in results if r.entry["kind"] == "conversation"),
    )
    passed = all(r.ok for r in results)
    lines = [
        f"NetCoop protocol conformance (protocol {PROTOCOL_VERSION}) - SIMULATED DATA, "
        "illustrative examples",
        "",
        f"  Valid messages accepted                     {va:>3}/{vt}",
        f"  Invalid messages rejected with the expected {ia:>3}/{it}  (right error code)",
        f"  Conversations behaving as expected          {ca:>3}/{ct}",
        "",
        f"  Result: {'PASS' if passed else 'FAIL'}",
        "",
        "Rejections (expected code: plain-English reason)",
    ]
    for r in results:
        if r.outcome.verdict == "rejected":
            mark = "ok " if r.ok else "XX "
            lines.append(f"  {mark}{r.entry['path']}")
            lines.append(f"       {r.outcome.code}: {r.outcome.reasons[0]}")
    bad = [r for r in results if not r.ok]
    if bad:
        lines += ["", "Mismatches"]
        for r in bad:
            e, o = r.entry, r.outcome
            lines.append(
                f"  {e['path']}: expected {e['expected_verdict']} {e.get('expected_code') or ''}"
                f"{' at #' + str(e['failing_index']) if e.get('failing_index') is not None else ''}"
                f", got {o.verdict} {o.code or ''}"
                f"{' at #' + str(o.failing_index) if o.failing_index is not None else ''}"
            )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ third-party agents

Agent = Callable[[ParsedMessage], "Envelope | str | dict[str, Any]"]


def assert_agent_conforms(
    agent: Agent,
    recorded_task_request: str | dict[str, Any],
    *,
    task_state: str = "READY",
    reply_state: str = "COLLECTING",
) -> ParsedMessage:
    """Feed a recorded task_request to ``agent`` and check that its reply is a valid
    message that the conversation guard accepts. Returns the parsed reply; raises
    ``AssertionError`` with plain-English reasons otherwise."""
    guard = ConversationGuard()
    task = try_parse(recorded_task_request)
    assert task.message is not None, [e.reason for e in task.errors]
    state = ConversationState().with_incident_state(task_state)
    accepted = guard.check(task.message.envelope, state)
    assert accepted.allowed, [v.reason for v in accepted.violations]
    state = state.apply(task.message.envelope).with_incident_state(reply_state)

    reply = agent(task.message)
    raw = reply.to_json() if isinstance(reply, Envelope) else reply
    parsed = try_parse(raw)
    assert parsed.message is not None, [f"{e.code} {e.path}: {e.reason}" for e in parsed.errors]
    verdict = guard.check(parsed.message.envelope, state)
    assert verdict.allowed, [f"{v.code}: {v.reason}" for v in verdict.violations]
    return parsed.message
