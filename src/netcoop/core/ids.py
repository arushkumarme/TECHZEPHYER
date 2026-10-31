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

    def incident(self) -> str:
        return self.next("INC")

    def message(self) -> str:
        msg = self.next("MSG", width=6)
        return f"{self.namespace}-{msg}" if self.namespace else msg
