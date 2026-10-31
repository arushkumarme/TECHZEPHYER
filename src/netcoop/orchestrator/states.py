"""Incident states and allowed transitions (doc 04 §2). Anything else is a bug."""

from __future__ import annotations

from typing import Literal

State = Literal[
    "RECEIVED",
    "VALIDATING",
    "REJECTED",
    "READY",
    "READY_WITH_WARNINGS",
    "DISPATCHED",
    "COLLECTING",
    "CORRELATING",
    "CLARIFYING",
    "DECIDED",
    "REPORTING",
    "AWAITING_REVIEW",
    "COMPLETE",
    "FAILED",
]

TERMINAL: frozenset[str] = frozenset({"REJECTED", "COMPLETE", "FAILED"})

ALLOWED: dict[str | None, frozenset[str]] = {
    None: frozenset({"RECEIVED"}),
    "RECEIVED": frozenset({"VALIDATING", "FAILED"}),
    "VALIDATING": frozenset({"READY", "READY_WITH_WARNINGS", "REJECTED", "FAILED"}),
    "READY": frozenset({"DISPATCHED", "FAILED"}),
    "READY_WITH_WARNINGS": frozenset({"DISPATCHED", "FAILED"}),
    "DISPATCHED": frozenset({"COLLECTING", "FAILED"}),
    # COLLECTING -> COLLECTING records an agent failure/retry without changing phase.
    "COLLECTING": frozenset({"COLLECTING", "CORRELATING", "FAILED"}),
    "CORRELATING": frozenset({"CLARIFYING", "DECIDED", "FAILED"}),
    "CLARIFYING": frozenset({"CORRELATING", "FAILED"}),
    "DECIDED": frozenset({"REPORTING", "FAILED"}),
    "REPORTING": frozenset({"AWAITING_REVIEW", "COMPLETE", "FAILED"}),
    "AWAITING_REVIEW": frozenset({"COMPLETE"}),
    "REJECTED": frozenset(),
    "COMPLETE": frozenset(),
    "FAILED": frozenset(),
}


class IllegalTransition(RuntimeError):
    pass


#: States a stored incident can be resumed from (not finished, not waiting for a human).
RESUMABLE: frozenset[str] = frozenset(
    s for s in ALLOWED if s is not None and s not in TERMINAL and s != "AWAITING_REVIEW"
)


def check_transition(current: str | None, new: str, *, resume: bool = False) -> None:
    """``resume=True`` additionally allows a self-transition that records a restart."""
    if resume and current == new and current in RESUMABLE:
        return
    if new not in ALLOWED.get(current, frozenset()):
        raise IllegalTransition(f"{current} -> {new} is not an allowed transition")
