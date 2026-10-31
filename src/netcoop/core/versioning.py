"""Protocol version rules (doc 05 §5).

Versions are ``"MAJOR.MINOR"``. Same major and same or older minor: accepted. Same major,
NEWER minor than ours: accepted - unknown fields are ignored and reported - with the warning
``PROTOCOL_MINOR_NEWER``. Any other major: rejected (``PROTOCOL_VERSION_UNSUPPORTED``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: 1.1 adds the optional envelope fields snapshot_id, mode, data_provenance, seq.
PROTOCOL_VERSION = "1.1"
PAYLOAD_SCHEMA_VERSION = "1.0"
SUPPORTED_PROTOCOL_MAJORS = frozenset({1})
SUPPORTED_PAYLOAD_MAJORS = frozenset({1})
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


@dataclass(frozen=True)
class VersionVerdict:
    accepted: bool
    code: str | None = None  # error code when rejected, warning code when accepted-with-warning
    reason: str = ""


def parse_version(value: object) -> tuple[int, int] | None:
    m = _VERSION_RE.match(value) if isinstance(value, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_version(
    value: object, *, ours: str, supported_majors: frozenset[int], what: str, unsupported_code: str
) -> VersionVerdict:
    parsed, mine = parse_version(value), parse_version(ours)
    assert mine is not None
    if parsed is None:
        return VersionVerdict(False, "MESSAGE_INVALID", f"{what} {value!r} is not MAJOR.MINOR")
    if parsed[0] not in supported_majors:
        return VersionVerdict(
            False, unsupported_code, f"{what} {value} not supported (ours {ours})"
        )
    if parsed[0] == mine[0] and parsed[1] > mine[1]:
        return VersionVerdict(
            True,
            "PROTOCOL_MINOR_NEWER",
            f"{what} {value} is newer than ours ({ours}); unknown fields are ignored",
        )
    return VersionVerdict(True)
