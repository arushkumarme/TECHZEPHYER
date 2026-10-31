"""Grade a single value against the configured thresholds (doc 08 §2)."""

from __future__ import annotations

from netcoop.core.vocab import Severity
from netcoop.diagnosis.params import DiagnosisParams

_ORDER: dict[str, int] = {"unknown": -1, "normal": 0, "elevated": 1, "critical": 2}


def grade(item: str, value: float | str | None, params: DiagnosisParams) -> Severity:
    """Severity of one value. Unknown items or unusable values grade as ``unknown``."""
    if value is None:
        return "unknown"
    if item == "status":
        return params.status_severity.get(str(value), "unknown")
    t = params.severity.get(item)
    if t is None or isinstance(value, str):
        return "unknown"
    if value >= t.critical_at:
        return "critical"
    if value > t.elevated_above:
        return "elevated"
    return "normal"


def worst(severities: list[Severity]) -> Severity:
    """Most severe of a list; ``unknown`` only when nothing is known."""
    return max(severities, key=lambda s: _ORDER[s]) if severities else "unknown"


def rank(severity: Severity) -> int:
    return _ORDER[severity]
