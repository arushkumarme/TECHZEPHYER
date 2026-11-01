"""Safe parsing of external messages (doc 05 §2, §5, §7).

:func:`try_parse` NEVER raises on bad input: it returns a :class:`ParseResult` with the
message (or ``None``), a list of errors and a list of warnings, each carrying a code from
the ``error_code`` vocabulary, a short human-readable reason and the field path. The
raising :func:`netcoop.core.messages.parse_message` is a thin wrapper around it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from netcoop.core.messages import PAYLOAD_TYPES, Envelope, ParsedMessage, _unknown_keys
from netcoop.core.versioning import (
    PAYLOAD_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    SUPPORTED_PAYLOAD_MAJORS,
    SUPPORTED_PROTOCOL_MAJORS,
    VERSION_ADDITIONS,
    check_version,
    parse_version,
)

#: PROVISIONAL (D-23): ~20x the largest message of the scenario suite (about 47 KB).
DEFAULT_MAX_MESSAGE_BYTES = 1_048_576
ALLOWED_MODE = "simulation"


@dataclass(frozen=True)
class ParseIssue:
    code: str
    reason: str
    path: str = ""


@dataclass(frozen=True)
class ParseResult:
    message: ParsedMessage | None
    errors: list[ParseIssue] = field(default_factory=list)
    warnings: list[ParseIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.message is not None


def _size(raw: object) -> int:
    if isinstance(raw, bytes):
        return len(raw)
    if isinstance(raw, str):
        return len(raw.encode("utf-8"))
    try:
        return len(json.dumps(raw, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _issues(exc: ValidationError, prefix: str = "") -> list[ParseIssue]:
    out = []
    for err in exc.errors():
        path = (prefix + ".".join(str(x) for x in err["loc"])).rstrip(".")
        msg = str(err["msg"])
        vocabulary_problem = err["type"] == "literal_error" or (
            err["type"] == "value_error"
            and ("is not a term of vocabulary" in msg or "is blocked" in msg)
        )
        if err["type"].isupper():  # a semantic rule: its type IS a registered error code
            code = err["type"]
        else:
            code = "UNKNOWN_TERM" if vocabulary_problem else "MESSAGE_INVALID"
        given = err.get("input")
        # Quote short scalar inputs only; whole objects would bury the reason.
        reason = (
            f"{msg} (got {given!r})"
            if isinstance(given, str | int | float | bool) and len(repr(given)) <= 60
            else msg
        )
        out.append(ParseIssue(code, reason, path))
    return out


def _fail(code: str, reason: str, path: str = "") -> ParseResult:
    return ParseResult(None, [ParseIssue(code, reason, path)])


def _newer_than(reader: str) -> list[dict[str, tuple[str, ...]]]:
    mine = parse_version(reader)
    assert mine is not None
    return [
        added
        for version, added in VERSION_ADDITIONS.items()
        if (parse_version(version) or (0, 0)) > mine
    ]


def _as_reader(
    data: dict[str, Any], reader: str
) -> tuple[dict[str, Any], list[ParseIssue], ParseIssue | None]:
    """Emulate a reader pinned to an older minor: drop the fields it does not know (reported
    as FIELD_IGNORED) and refuse message types it does not know."""
    data = json.loads(json.dumps(data))
    ignored: list[ParseIssue] = []
    for added in _newer_than(reader):
        if data.get("message_type") in added["message_types"]:
            return (
                data,
                ignored,
                ParseIssue(
                    "UNKNOWN_TERM",
                    f"message_type {data['message_type']!r} is not known to a {reader} reader",
                    "message_type",
                ),
            )
        for key in added["envelope"]:
            if key in data:
                data.pop(key)
                ignored.append(ParseIssue("FIELD_IGNORED", f"not known to a {reader} reader", key))
        payload = data.get("payload")
        for path in added["payload"]:
            mtype, _, rest = path.partition(".")
            if data.get("message_type") != mtype or not isinstance(payload, dict):
                continue
            if "[]." in rest:
                lst, _, key = rest.partition("[].")
                for i, item in enumerate(payload.get(lst) or []):
                    if isinstance(item, dict) and key in item:
                        item.pop(key)
                        ignored.append(
                            ParseIssue(
                                "FIELD_IGNORED",
                                f"not known to a {reader} reader",
                                f"payload.{lst}.{i}.{key}",
                            )
                        )
            elif rest in payload:
                payload.pop(rest)
                ignored.append(
                    ParseIssue(
                        "FIELD_IGNORED", f"not known to a {reader} reader", f"payload.{rest}"
                    )
                )
    return data, ignored, None


def try_parse(
    raw: object,
    *,
    max_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
    reader_version: str = PROTOCOL_VERSION,
) -> ParseResult:
    if not isinstance(raw, str | bytes | dict):
        return _fail(
            "MESSAGE_INVALID", f"a message must be JSON text or an object, got {type(raw).__name__}"
        )
    size = _size(raw)
    if size > max_bytes:
        return _fail("MESSAGE_TOO_LARGE", f"message is {size} bytes; the limit is {max_bytes}")
    data: Any = raw
    if isinstance(raw, str | bytes):
        try:
            data = json.loads(raw)
        except ValueError as exc:  # JSON or UTF-8 decoding
            return _fail("MESSAGE_INVALID", f"not valid JSON: {exc}")
    if not isinstance(data, dict):
        return _fail("MESSAGE_INVALID", "a message must be a JSON object")

    warnings: list[ParseIssue] = []
    if reader_version != PROTOCOL_VERSION:
        data, pinned_ignored, refused = _as_reader(data, reader_version)
        if refused is not None:
            return ParseResult(None, [refused])
        warnings += pinned_ignored
    for value, ours, majors, what, code in (
        (
            data.get("protocol_version"),
            reader_version,
            SUPPORTED_PROTOCOL_MAJORS,
            "protocol_version",
            "PROTOCOL_VERSION_UNSUPPORTED",
        ),
        (
            data.get("payload_schema_version"),
            PAYLOAD_SCHEMA_VERSION,
            SUPPORTED_PAYLOAD_MAJORS,
            "payload_schema_version",
            "PAYLOAD_SCHEMA_VERSION_UNSUPPORTED",
        ),
    ):
        verdict = check_version(
            value, ours=ours, supported_majors=majors, what=what, unsupported_code=code
        )
        if not verdict.accepted:
            assert verdict.code is not None
            return _fail(verdict.code, verdict.reason, what)
        if verdict.code:
            warnings.append(ParseIssue(verdict.code, verdict.reason, what))

    mode = data.get("mode")
    if mode is not None and mode != ALLOWED_MODE:
        return _fail(
            "MODE_NOT_ALLOWED",
            f"mode {mode!r} is not allowed; only "
            f"{ALLOWED_MODE!r} exists in this build (never defaulted to live)",
            "mode",
        )

    try:
        envelope = Envelope.model_validate(data)
    except ValidationError as exc:
        return ParseResult(None, _issues(exc), warnings)
    payload_cls = PAYLOAD_TYPES[envelope.message_type]
    try:
        payload = payload_cls.model_validate(envelope.payload)
    except ValidationError as exc:
        return ParseResult(None, _issues(exc, "payload."), warnings)

    ignored = _unknown_keys(Envelope, {k: v for k, v in data.items() if k != "payload"}, "")
    ignored += _unknown_keys(payload_cls, envelope.payload, "payload.")
    ignored = sorted(ignored)
    warnings += [ParseIssue("FIELD_IGNORED", "unknown field ignored", p) for p in ignored]
    message = ParsedMessage(
        envelope=envelope,
        payload=payload,
        ignored_fields=ignored,
        warnings=[w.code for w in warnings if w.code != "FIELD_IGNORED"],
    )
    return ParseResult(message, [], warnings)
