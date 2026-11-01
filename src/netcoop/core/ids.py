"""Deterministic identifiers and an injectable clock (doc 04 §7: replayable runs)."""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Returns ``start``, then advances by ``step`` on every call (tests and replays)."""

    def __init__(self, start: datetime, step: timedelta = timedelta(0)) -> None:
        if start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        self._t = start
        self._step = step
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            t = self._t
            self._t = t + self._step
            return t


class IdFactory:
    """Sequential ids per prefix: ``INC-0001``, ``MSG-000001``, ``OBS-0001``..."""

    def __init__(self, namespace: str | None = None) -> None:
        self.namespace = namespace
        self._counters: defaultdict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def next(self, prefix: str, width: int = 4) -> str:
        with self._lock:
            self._counters[prefix] += 1
            return f"{prefix}-{self._counters[prefix]:0{width}d}"

    def seed(self, prefix: str, value: int) -> None:
        """Continue numbering after ``value`` (used when resuming a stored incident)."""
        with self._lock:
            self._counters[prefix] = max(self._counters[prefix], value)

    def incident(self) -> str:
        return self.next("INC")

    def message(self) -> str:
        msg = self.next("MSG", width=6)
        return f"{self.namespace}-{msg}" if self.namespace else msg


#: Accepted shapes of every identifier kind. Existing formats are kept (owner ruling); new
#: kinds use PREFIX-NNNN. ``REC-`` is taken by normalized records, so recommendations use
#: ``RCM-``. The incident format is PROVISIONAL (D-22).
ID_PATTERNS: dict[str, str] = {
    "incident": r"[A-Z]{2,8}-\d{4,}",
    "message": r"(?:[A-Z]{2,8}-\d{4,}-)?MSG-\d{6}(?:\.R)?",
    "observation": r"OBS-(?:[A-Z]+-\d{6}-\d{3}|\d{4,})",
    "hypothesis": r"HYP-(?:[A-Z]+-\d{6}-\d{3}|\d{4,})",
    "record": r"REC-\d{4,}",
    "snapshot": r"SNAP-[0-9a-f]{12}",
    "candidate": r"CAND-\d{4,}",
    "complaint": r"CMP-\d{4,}",
    "conflict": r"CONF-\d{3,}",
    "recommendation": r"RCM-\d{4,}",
    "task": r"TASK-\d{4,}",
    "clarification": r"CLR-\d{4,}",
    "decision": r"DEC-\d{4,}",
}


def validate_id(kind: str, value: str) -> bool:
    """True if ``value`` has the shape of an id of ``kind`` (KeyError for an unknown kind)."""
    import re

    return re.fullmatch(ID_PATTERNS[kind], value) is not None
