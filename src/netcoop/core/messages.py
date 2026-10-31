"""Message envelope, typed payloads, and validated (de)serialization (doc 05 §2-§5).

Every message crossing the bus is serialized to JSON and re-parsed with
:func:`parse_message`, so in-process delivery exercises the same contract an external
transport would.

Version policy (doc 05 §5): versions are ``"MAJOR.MINOR"``. A reader accepts any minor
version of a major it supports (additive change) and rejects other majors.
"""

from __future__ import annotations

import json
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, Field, ValidationError, model_validator

from netcoop.core.blocks import (
    ClarificationRecord,
    ConflictRecord,
    Limitation,
    NotAssessableItem,
    Observation,
    ProtocolModel,
    ScoredHypothesis,
    SelfAssessment,
    TimeWindow,
    ToolCallRecord,
)
from netcoop.core.blocks import Hypothesis as Hypothesis
from netcoop.core.vocab import (
    RESPONSE_TYPES,
    AgentId,
    ClarificationReason,
    ConfidenceCategory,
    DecisionKind,
    MessageStatus,
    MessageType,
    QuestionType,
    TrustLabel,
)

PROTOCOL_VERSION = "1.0"
PAYLOAD_SCHEMA_VERSION = "1.0"
SUPPORTED_PROTOCOL_MAJORS = frozenset({1})
SUPPORTED_PAYLOAD_MAJORS = frozenset({1})
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


class MessageValidationError(ValueError):
    """A message failed validation. ``code`` is from the error taxonomy (doc 05 §7)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- payloads


class TaskRequest(ProtocolModel):
    goal: str
    scope_entities: list[str]
    window: TimeWindow
    tool_budget: int = Field(ge=0)
    deadline_s: float = Field(gt=0)
    context: dict[str, Any] = Field(default_factory=dict)


class Finding(ProtocolModel):
    observations: list[Observation]
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    not_assessable: list[NotAssessableItem] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    self_assessment: SelfAssessment
    facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured non-metric facts, e.g. topology scope from connectivity_agent",
    )


class ClarificationRequest(ProtocolModel):
    question_type: QuestionType
    target: AgentId
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: ClarificationReason
    round: int = Field(ge=1)


class ClarificationResponse(ProtocolModel):
    answered: bool
    observations: list[Observation] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    reason: str | None = None


class Decision(ProtocolModel):
    decision: DecisionKind
    ranked: list[ScoredHypothesis]
    margin: float | None
    gate_checks: dict[str, bool] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_category: ConfidenceCategory = "insufficient"
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    clarifications: list[ClarificationRecord] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    affected_entities: list[str] = Field(default_factory=list)


class ReportReady(ProtocolModel):
    report: dict[str, Any]
    markdown: str | None = None


class AgentError(ProtocolModel):
    code: str
    message: str
    recoverable: bool


class CommunityCandidate(ProtocolModel):
    candidate_id: str
    zone: str
    symptom_categories: list[str]
    window: TimeWindow
    complaint_count: int = Field(ge=1)
    distinct_reporters: int = Field(ge=1)
    trust_label: TrustLabel = "reported_unverified"


PAYLOAD_TYPES: dict[str, type[ProtocolModel]] = {
    "task_request": TaskRequest,
    "finding": Finding,
    "clarification_request": ClarificationRequest,
    "clarification_response": ClarificationResponse,
    "decision": Decision,
    "report_ready": ReportReady,
    "agent_error": AgentError,
    "community_candidate": CommunityCandidate,
}

# --------------------------------------------------------------------------- envelope


class Envelope(ProtocolModel):
    protocol_version: str
    message_id: str = Field(min_length=1)
    incident_id: str | None = None
    in_reply_to: str | None = None
    sender: AgentId
    recipient: AgentId
    message_type: MessageType
    sent_at: AwareDatetime
    payload_schema_version: str
    status: MessageStatus = "ok"
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _responses_reference_requests(self) -> Self:
        if self.message_type in RESPONSE_TYPES and not self.in_reply_to:
            raise ValueError(f"{self.message_type} requires in_reply_to")
        return self

    def to_json(self) -> str:
        return self.model_dump_json()


@dataclass(frozen=True)
class ParsedMessage:
    envelope: Envelope
    payload: ProtocolModel
    ignored_fields: list[str] = field(default_factory=list)


def make_message(
    *,
    message_id: str,
    sender: AgentId,
    recipient: AgentId,
    message_type: MessageType,
    payload: ProtocolModel,
    sent_at: Any,
    incident_id: str | None = None,
    in_reply_to: str | None = None,
    status: MessageStatus = "ok",
) -> Envelope:
    """Build an envelope around a typed payload (payload stored in JSON form)."""
    expected = PAYLOAD_TYPES[message_type]
    if not isinstance(payload, expected):
        raise MessageValidationError(
            "MESSAGE_INVALID",
            f"{message_type} needs {expected.__name__}, got {type(payload).__name__}",
        )
    return Envelope(
        protocol_version=PROTOCOL_VERSION,
        message_id=message_id,
        incident_id=incident_id,
        in_reply_to=in_reply_to,
        sender=sender,
        recipient=recipient,
        message_type=message_type,
        sent_at=sent_at,
        payload_schema_version=PAYLOAD_SCHEMA_VERSION,
        status=status,
        payload=payload.model_dump(mode="json"),
    )


# --------------------------------------------------------------------------- parsing


def _check_version(value: Any, supported: frozenset[int], code: str, what: str) -> None:
    match = _VERSION_RE.match(value) if isinstance(value, str) else None
    if match is None:
        raise MessageValidationError("MESSAGE_INVALID", f"{what} {value!r} is not MAJOR.MINOR")
    if int(match.group(1)) not in supported:
        raise MessageValidationError(code, f"{what} {value} not supported")


def _model_types(annotation: Any) -> list[type[BaseModel]]:
    """BaseModel classes reachable directly from an annotation (through Optional/list)."""
    origin = typing.get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]
        return []
    if origin in (list, typing.Union, types.UnionType):
        found: list[type[BaseModel]] = []
        for arg in typing.get_args(annotation):
            found.extend(_model_types(arg))
        return found
    return []


def _unknown_keys(model: type[BaseModel], data: Any, prefix: str) -> list[str]:
    if not isinstance(data, dict):
        return []
    unknown: list[str] = []
    fields = model.model_fields
    for key, value in data.items():
        path = f"{prefix}{key}"
        if key not in fields:
            unknown.append(path)
            continue
        for sub in _model_types(fields[key].annotation):
            if isinstance(value, list):
                for i, item in enumerate(value):
                    unknown.extend(_unknown_keys(sub, item, f"{path}[{i}]."))
            else:
                unknown.extend(_unknown_keys(sub, value, f"{path}."))
    return unknown


def parse_message(raw: str | bytes | dict[str, Any]) -> ParsedMessage:
    """Validate a raw message. Raises :class:`MessageValidationError` on any violation."""
    if isinstance(raw, str | bytes):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MessageValidationError("MESSAGE_INVALID", f"not JSON: {exc}") from exc
    else:
        data = raw
    if not isinstance(data, dict):
        raise MessageValidationError("MESSAGE_INVALID", "message must be a JSON object")

    _check_version(
        data.get("protocol_version"),
        SUPPORTED_PROTOCOL_MAJORS,
        "PROTOCOL_VERSION_UNSUPPORTED",
        "protocol_version",
    )
    _check_version(
        data.get("payload_schema_version"),
        SUPPORTED_PAYLOAD_MAJORS,
        "PAYLOAD_SCHEMA_VERSION_UNSUPPORTED",
        "payload_schema_version",
    )
    try:
        envelope = Envelope.model_validate(data)
        payload_cls = PAYLOAD_TYPES[envelope.message_type]
        payload = payload_cls.model_validate(envelope.payload)
    except ValidationError as exc:
        raise MessageValidationError("MESSAGE_INVALID", str(exc)) from exc

    ignored = _unknown_keys(Envelope, {k: v for k, v in data.items() if k != "payload"}, "")
    ignored += _unknown_keys(payload_cls, envelope.payload, "payload.")
    return ParsedMessage(envelope=envelope, payload=payload, ignored_fields=sorted(ignored))


def payload_as[P: ProtocolModel](parsed: ParsedMessage, cls: type[P]) -> P:
    """Typed access to a parsed payload; raises if the type does not match."""
    if not isinstance(parsed.payload, cls):
        raise MessageValidationError(
            "MESSAGE_INVALID", f"expected {cls.__name__}, got {type(parsed.payload).__name__}"
        )
    return parsed.payload
