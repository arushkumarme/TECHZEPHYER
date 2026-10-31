"""Message envelope, typed payloads, and validated (de)serialization (doc 05 §2-§5).

Every message crossing the bus is serialized to JSON and re-parsed with
:func:`parse_message`, so in-process delivery exercises the same contract an external
transport would.

Version policy (doc 05 §5): versions are ``"MAJOR.MINOR"``. A reader accepts any minor
version of a major it supports (additive change) and rejects other majors.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

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
from netcoop.core.versioning import PAYLOAD_SCHEMA_VERSION as PAYLOAD_SCHEMA_VERSION
from netcoop.core.versioning import PROTOCOL_VERSION as PROTOCOL_VERSION
from netcoop.core.versioning import SUPPORTED_PAYLOAD_MAJORS as SUPPORTED_PAYLOAD_MAJORS
from netcoop.core.versioning import SUPPORTED_PROTOCOL_MAJORS as SUPPORTED_PROTOCOL_MAJORS
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
from netcoop.core.vocabulary import VocabTerm

# Version constants live in versioning.py (re-exported above for existing importers).


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
    # ---- protocol 1.1 (optional; stamped by the bus so 1.0 messages still parse) ----
    snapshot_id: str | None = Field(
        default=None,
        pattern=r"^SNAP-[0-9a-f]{12}$",
        description="Fingerprint of the data every agent of the incident analyses",
    )
    mode: Literal["simulation"] | None = Field(
        default=None, description="Only simulation is allowed (MODE_NOT_ALLOWED otherwise)"
    )
    data_provenance: Annotated[str, VocabTerm("data_provenance")] | None = None
    seq: int | None = Field(
        default=None, ge=1, description="Per-incident sequence number assigned by the bus"
    )

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
    #: Non-fatal notices, e.g. PROTOCOL_MINOR_NEWER (codes from the error_code vocabulary).
    warnings: list[str] = field(default_factory=list)


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
    snapshot_id: str | None = None,
    mode: str | None = None,
    data_provenance: str | None = None,
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
        snapshot_id=snapshot_id,
        mode=mode,
        data_provenance=data_provenance,
    )


# --------------------------------------------------------------------------- parsing


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


def parse_message(
    raw: str | bytes | dict[str, Any], *, max_bytes: int | None = None
) -> ParsedMessage:
    """Validate a raw message. Raises :class:`MessageValidationError` (code of the first
    problem; all problems in the detail) on any violation. Use
    :func:`netcoop.core.parse.try_parse` for a version that never raises."""
    from netcoop.core.parse import DEFAULT_MAX_MESSAGE_BYTES, try_parse

    result = try_parse(raw, max_bytes=max_bytes or DEFAULT_MAX_MESSAGE_BYTES)
    if result.message is None:
        first = result.errors[0]
        detail = "; ".join(f"{e.path or '<message>'}: {e.reason}" for e in result.errors)
        raise MessageValidationError(first.code, detail)
    return result.message


def payload_as[P: ProtocolModel](parsed: ParsedMessage, cls: type[P]) -> P:
    """Typed access to a parsed payload; raises if the type does not match."""
    if not isinstance(parsed.payload, cls):
        raise MessageValidationError(
            "MESSAGE_INVALID", f"expected {cls.__name__}, got {type(parsed.payload).__name__}"
        )
    return parsed.payload
