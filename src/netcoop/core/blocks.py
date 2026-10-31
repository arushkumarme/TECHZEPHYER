"""Payload building blocks (doc 05 §4).

Facts, interpretations and unknowns are kept in separate types:
:class:`Observation` (measured or derived fact), :class:`Hypothesis` (interpretation),
:class:`NotAssessableItem` (explicit unknown).
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from netcoop.core.vocab import (
    AgentId,
    Assessability,
    CauseType,
    ConfidenceCategory,
    ConflictRule,
    EvidenceClass,
    NotAssessableReason,
    Severity,
)


class ProtocolModel(BaseModel):
    """Base for every protocol model: immutable; unknown keys ignored (and reported by
    :func:`netcoop.core.messages.parse_message`)."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class TimeWindow(ProtocolModel):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("window end is before start")
        return self


class Observation(ProtocolModel):
    """A measured or derived fact about one entity and one metric."""

    observation_id: str
    entity: str
    metric: str = Field(description="Canonical metric name (doc 06), e.g. 'latency_ms'")
    metric_category: str
    value: float | int | str | None
    unit: str
    window: TimeWindow
    severity: Severity
    assessability: Assessability
    quality_flags: list[str] = Field(default_factory=list)
    source_ref: list[str] = Field(default_factory=list, description="Normalized record IDs")
    agent: AgentId
    evidence_class: EvidenceClass = "direct_measurement"


class Hypothesis(ProtocolModel):
    """An agent-local interpretation; never a fact and never the final confidence."""

    hypothesis_id: str
    cause_type: CauseType
    entities: list[str]
    supporting_observation_ids: list[str] = Field(default_factory=list)
    contradicting_observation_ids: list[str] = Field(default_factory=list)
    missing_expected_evidence: list[str] = Field(default_factory=list)
    local_score: float = Field(ge=0.0, le=1.0)
    rationale_code: str


class NotAssessableItem(ProtocolModel):
    entity: str
    metric: str
    reason: NotAssessableReason
    detail: str = ""


class Limitation(ProtocolModel):
    code: str
    text: str


class ToolCallRecord(ProtocolModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str
    at: AwareDatetime


class SelfAssessment(ProtocolModel):
    assessed_fraction: float = Field(ge=0.0, le=1.0)
    budget_exhausted: bool


class ScoredHypothesis(ProtocolModel):
    """A hypothesis after scoring by the correlation agent (doc 08 §4)."""

    cause_type: CauseType
    entities: list[str]
    score: float = Field(ge=0.0, le=1.0)
    support: float = Field(ge=0.0, le=1.0)
    contradiction: float = Field(ge=0.0, le=1.0)
    corroboration: float = Field(ge=0.0)
    community_bonus: float = Field(default=0.0, ge=0.0)
    unexplained: float = Field(default=0.0, ge=0.0, le=1.0)
    base: float = Field(default=0.0, ge=0.0, le=1.0, description="Score before the ceiling")
    ceiling: float = Field(ge=0.0, le=1.0)
    supporting_observation_ids: list[str] = Field(default_factory=list)
    contradicting_observation_ids: list[str] = Field(default_factory=list)
    missing_expected_evidence: list[str] = Field(default_factory=list)
    supporting_sources: list[AgentId] = Field(default_factory=list)
    matched_signature_items: list[str] = Field(default_factory=list)
    diagnosable: bool = True


class ConflictRecord(ProtocolModel):
    conflict_id: str
    description: str
    observation_ids: list[str]
    rule: ConflictRule
    resolution: str
    disregarded: dict[str, str] = Field(
        default_factory=dict, description="observation_id -> reason it was given less weight"
    )


class ClarificationRecord(ProtocolModel):
    round: int = Field(ge=1)
    question_type: str
    target: AgentId
    reason: str
    answered: bool
    summary: str


__all__ = [
    "ClarificationRecord",
    "ConfidenceCategory",
    "ConflictRecord",
    "Hypothesis",
    "Limitation",
    "NotAssessableItem",
    "Observation",
    "ProtocolModel",
    "ScoredHypothesis",
    "SelfAssessment",
    "TimeWindow",
    "ToolCallRecord",
]
