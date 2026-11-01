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
    CONFLICTING_RELATIONS,
    Abstention,
    ClarificationRecord,
    ConflictRecord,
    ConflictTrailEntry,
    EvidenceRef,
    IncidentContext,
    Limitation,
    NotAssessableItem,
    Observation,
    ProtocolModel,
    Recommendation,
    ScoredHypothesis,
    SelfAssessment,
    TimeWindow,
    ToolCallRecord,
    rule_error,
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
    ConflictRule,
    DecisionKind,
    MessageStatus,
    MessageType,
    QuestionType,
    TrustLabel,
)
from netcoop.core.vocabulary import VocabTerm, get_vocabulary

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
    # ---- protocol 1.1 (optional) ----
    task_id: str | None = Field(default=None, pattern=r"^TASK-\d{4,}$")
    task_kind: Annotated[str, VocabTerm("task_kind")] | None = None
    input_message_ids: list[str] = Field(
        default_factory=list,
        description="Earlier messages (findings, decision) this task works from: references",
    )
    incident_context: IncidentContext | None = None


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
    task_id: str | None = Field(default=None, pattern=r"^TASK-\d{4,}$")


#: Parameters each question type needs (any one key of a tuple is enough).
QUESTION_PARAMETERS: dict[str, list[tuple[str, ...]]] = {
    "recheck_metric": [("entity",), ("metric",)],
    "what_if_cause": [("entity",)],
    "assess_additional_entities": [("entities", "entity")],
    "widen_time_window": [("entities", "entity")],
}


class ClarificationRequest(ProtocolModel):
    question_type: QuestionType
    target: AgentId
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: ClarificationReason
    round: int = Field(ge=1)
    clarification_id: str | None = Field(default=None, pattern=r"^CLR-\d{4,}$")

    @model_validator(mode="after")
    def _parameters_fit_question(self) -> Self:
        for keys in QUESTION_PARAMETERS[self.question_type]:
            if not any(self.parameters.get(k) for k in keys):
                raise rule_error(
                    "CLARIFICATION_PARAMETERS_INVALID",
                    f"{self.question_type} needs parameter {' or '.join(keys)}",
                )
        return self


class ClarificationResponse(ProtocolModel):
    answered: bool
    observations: list[Observation] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    reason: str | None = None
    # ---- protocol 1.1 ----
    clarification_id: str | None = Field(default=None, pattern=r"^CLR-\d{4,}$")
    answerable: Literal["yes", "no", "partial"] | None = None
    source: AgentId | None = None

    @model_validator(mode="before")
    @classmethod
    def _derive_answerable(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("answerable") is None and "answered" in data:
            data = {**data, "answerable": "yes" if data["answered"] else "no"}
        return data

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.answerable in ("yes", "partial")) is not self.answered:
            raise rule_error(
                "CLARIFICATION_ANSWER_MISMATCH",
                f"answerable={self.answerable!r} contradicts answered={self.answered}",
            )
        return self


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
    # ---- protocol 1.1 ----
    decision_id: str | None = Field(default=None, pattern=r"^DEC-\d{4,}$")
    score_method: Annotated[str, VocabTerm("score_method")] = "heuristic"
    abstention: Abstention | None = None
    # ---- protocol 1.2 ----
    conflict_trail: list[ConflictTrailEntry] = Field(
        default_factory=list,
        description="Every conflict with the rule applied; unresolved ones are preserved",
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_abstention(cls, data: Any) -> Any:
        """A 1.0 sender has no abstention block: derive its reasons from the failed gate
        checks. An explicit null is NOT filled in (and is then rejected below)."""
        if (
            isinstance(data, dict)
            and data.get("decision") == "insufficient_evidence"
            and "abstention" not in data
        ):
            data = {**data, "abstention": abstention_from_gates(data.get("gate_checks") or {})}
        return data

    @model_validator(mode="after")
    def _abstention_rule(self) -> Self:
        if self.decision == "insufficient_evidence" and self.abstention is None:
            raise rule_error(
                "ABSTENTION_MISMATCH", "an insufficient_evidence decision needs an abstention block"
            )
        if self.decision == "diagnosed" and self.abstention is not None:
            raise rule_error(
                "ABSTENTION_MISMATCH", "a diagnosed decision must not carry an abstention block"
            )
        return self


def abstention_from_gates(
    gate_checks: dict[str, Any], would_change: list[str] | None = None
) -> dict[str, Any]:
    """Map failed decision-gate checks onto abstention reasons (registry attribute
    ``gate_check`` of the abstention_reason vocabulary)."""
    by_gate = {
        str(t.attributes.get("gate_check")): t.id for t in get_vocabulary("abstention_reason").terms
    }
    failed = sorted(k for k, v in gate_checks.items() if v is False)
    return {
        "reasons": [by_gate[k] for k in failed if k in by_gate],
        "evidence_that_would_change_decision": list(would_change or []),
    }


class ReportReady(ProtocolModel):
    report: dict[str, Any]
    markdown: str | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)


class AgentError(ProtocolModel):
    code: str
    message: str
    recoverable: bool
    related_message_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CommunityCandidate(ProtocolModel):
    candidate_id: str
    zone: str
    symptom_categories: list[str]
    window: TimeWindow
    complaint_count: int = Field(ge=1)
    distinct_reporters: int = Field(ge=1)
    trust_label: TrustLabel = "reported_unverified"
    complaint_ids: list[str] = Field(default_factory=list)


class ConflictParty(ProtocolModel):
    agent: AgentId
    hypothesis_ids: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)


class ConflictSide(ProtocolModel):
    agent: AgentId
    claim: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)


class ConflictReport(ProtocolModel):
    """The correlation agent states a REAL conflict and asks one party to respond
    (protocol 1.2, doc 05 §19). Agents merely describing the same problem differently
    (relation compatible/refines) never make a conflict."""

    conflict_id: str = Field(pattern=r"^CONF-\d{3,}$")
    conflict_type: Annotated[str, VocabTerm("conflict_type")]
    parties: list[ConflictParty] = Field(min_length=1)
    sides: list[ConflictSide] = Field(min_length=2)
    relation: Annotated[str, VocabTerm("hypothesis_relation")] | None = None
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    reason_text: str
    proposed_rule: ConflictRule
    status: Annotated[str, VocabTerm("conflict_status")] = "open"
    effect_on_confidence: str
    target: AgentId = Field(description="The party asked to respond")
    recheck: dict[str, Any] = Field(
        default_factory=dict, description="What the target should re-check (entity, metric)"
    )
    round: int = Field(ge=1, description="Counts toward the clarification round limit")
    clarification_id: str | None = Field(default=None, pattern=r"^CLR-\d{4,}$")

    @model_validator(mode="after")
    def _a_real_conflict(self) -> Self:
        if self.relation is not None and self.relation not in CONFLICTING_RELATIONS:
            raise rule_error(
                "CONFLICT_RELATION_NOT_CONFLICTING",
                f"relation {self.relation!r} is not a conflict; only competes or contradicts "
                "can raise one",
            )
        if self.conflict_type == "hypothesis_competition" and self.relation is None:
            raise rule_error(
                "CONFLICT_RELATION_NOT_CONFLICTING",
                "a hypothesis_competition conflict must state relation competes or contradicts",
            )
        if self.target not in {p.agent for p in self.parties}:
            raise rule_error(
                "CONFLICT_TARGET_NOT_PARTY",
                f"{self.target} is asked to respond but is not a party to {self.conflict_id}",
            )
        return self


class ConflictResponse(ProtocolModel):
    conflict_id: str = Field(pattern=r"^CONF-\d{3,}$")
    stance: Annotated[str, VocabTerm("conflict_stance")]
    evidence: list[EvidenceRef] = Field(default_factory=list, description="New evidence refs")
    observations: list[Observation] = Field(default_factory=list)
    note: str = ""
    source: AgentId | None = None
    clarification_id: str | None = Field(default=None, pattern=r"^CLR-\d{4,}$")


PAYLOAD_TYPES: dict[str, type[ProtocolModel]] = {
    "task_request": TaskRequest,
    "finding": Finding,
    "clarification_request": ClarificationRequest,
    "clarification_response": ClarificationResponse,
    "decision": Decision,
    "report_ready": ReportReady,
    "agent_error": AgentError,
    "community_candidate": CommunityCandidate,
    "conflict_report": ConflictReport,
    "conflict_response": ConflictResponse,
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
