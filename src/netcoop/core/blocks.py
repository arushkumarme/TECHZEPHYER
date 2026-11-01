"""Payload building blocks (doc 05 §4).

Facts, interpretations and unknowns are kept in separate types:
:class:`Observation` (measured or derived fact), :class:`Hypothesis` (interpretation),
:class:`NotAssessableItem` (explicit unknown).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

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
from netcoop.core.vocabulary import VocabTerm, get_vocabulary, is_valid
from netcoop.core.vocabulary.units import unit_fits_metric


def rule_error(code: str, text: str) -> PydanticCustomError:
    """A semantic-rule violation whose error *type* is a registered error code, so the
    parser reports the code itself (not a generic MESSAGE_INVALID) with the field path."""
    return PydanticCustomError(code, "{text}", {"text": text})


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
    # ---- protocol 1.1 (optional) ----
    aggregation: Annotated[str, VocabTerm("aggregation")] | None = None
    sample_count: int | None = Field(default=None, ge=0)
    baseline_ref: str | None = Field(
        default=None, description="Id of the threshold in config/diagnosis.toml it was judged by"
    )
    not_assessable_reason: NotAssessableReason | None = None

    @model_validator(mode="after")
    def _semantic_rules(self) -> Self:
        # Rule 1: missing data is never healthy data, and never carries a value.
        if self.assessability == "not_assessable":
            if (
                self.value is not None
                or self.severity != "unknown"
                or self.not_assessable_reason is None
            ):
                raise rule_error(
                    "ASSESSABILITY_VALUE_MISMATCH",
                    "rule 1: a not_assessable observation must have no value, severity "
                    "'unknown' and a not_assessable_reason",
                )
        elif self.value is None:
            raise rule_error(
                "ASSESSABILITY_VALUE_MISMATCH", "rule 1: an assessed observation must carry a value"
            )
        # Rule 2: a declared unit must exist and fit the metric's dimension.
        if (
            self.unit
            and is_valid("metric", self.metric)
            and not unit_fits_metric(self.metric, self.unit)
        ):
            raise rule_error(
                "UNIT_INCOMPATIBLE",
                f"rule 2: unit {self.unit!r} is unknown or does not fit metric {self.metric!r}",
            )
        return self


class EntityRef(ProtocolModel):
    entity_type: Annotated[str, VocabTerm("entity_type")]
    entity_id: str = Field(min_length=1)


class EvidenceRef(ProtocolModel):
    """A typed pointer to evidence (never a copy of it)."""

    evidence_type: Annotated[str, VocabTerm("evidence_type")]
    evidence_id: str = Field(min_length=1)
    stance: Annotated[str, VocabTerm("evidence_stance")]
    strength: float | None = Field(default=None, ge=0.0, le=1.0)
    note: str = ""

    @model_validator(mode="after")
    def _prefix_matches_type(self) -> Self:
        # Rule 5: the id prefix must match the evidence type (registry attribute id_prefix).
        term = get_vocabulary("evidence_type").term(self.evidence_type)
        prefix = str(term.attributes.get("id_prefix", ""))
        if prefix and not self.evidence_id.startswith(prefix):
            raise rule_error(
                "EVIDENCE_PREFIX_MISMATCH",
                f"rule 5: {self.evidence_type} evidence ids start with {prefix!r}, "
                f"got {self.evidence_id!r}",
            )
        return self


class HypothesisRelation(ProtocolModel):
    hypothesis_id: str = Field(pattern=r"^HYP-")
    relation: Annotated[str, VocabTerm("hypothesis_relation")]


#: Relations that make two hypotheses a real conflict (the others never do).
CONFLICTING_RELATIONS = frozenset({"competes", "contradicts"})


def _refs(ids: list[str], stance: str) -> list[dict[str, Any]]:
    return [{"evidence_type": "observation", "evidence_id": i, "stance": stance} for i in ids]


def _ref_field(r: Any, name: str) -> Any:
    return getattr(r, name) if isinstance(r, EvidenceRef) else r.get(name)


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
    # ---- protocol 1.1 ----
    supporting: list[EvidenceRef] = Field(default_factory=list)
    contradicting: list[EvidenceRef] = Field(default_factory=list)
    score_method: Annotated[str, VocabTerm("score_method")] = "agent_local_heuristic"
    # ---- protocol 1.2 ----
    relations: list[HypothesisRelation] = Field(
        default_factory=list,
        description="How this hypothesis relates to others; only competes/contradicts can "
        "raise a conflict",
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_refs(cls, data: Any) -> Any:
        """1.0 senders give only the observation-id lists (and 1.1 senders may give only
        refs): fill whichever side is absent so both always describe the same evidence."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for ids_key, refs_key, stance in (
            ("supporting_observation_ids", "supporting", "supports"),
            ("contradicting_observation_ids", "contradicting", "contradicts"),
        ):
            ids, refs = data.get(ids_key) or [], data.get(refs_key) or []
            if ids and not refs:
                data[refs_key] = _refs(list(ids), stance)
            elif refs and not ids:
                data[ids_key] = [
                    _ref_field(r, "evidence_id")
                    for r in refs
                    if _ref_field(r, "evidence_type") == "observation"
                ]
        return data

    @model_validator(mode="after")
    def _semantic_rules(self) -> Self:
        # Rule 3: an interpretation must cite evidence or name what is missing.
        if not self.supporting and not self.missing_expected_evidence:
            raise rule_error(
                "HYPOTHESIS_WITHOUT_EVIDENCE",
                "rule 3: a hypothesis needs a supporting evidence ref or missing_expected_evidence",
            )
        for refs, stance in ((self.supporting, "supports"), (self.contradicting, "contradicts")):
            if any(r.stance != stance for r in refs):
                raise rule_error(
                    "EVIDENCE_STANCE_MISMATCH",
                    f"rule 3: refs in this list must have stance {stance!r}",
                )
        for refs, ids in (
            (self.supporting, self.supporting_observation_ids),
            (self.contradicting, self.contradicting_observation_ids),
        ):
            if [r.evidence_id for r in refs if r.evidence_type == "observation"] != list(ids):
                raise rule_error(
                    "EVIDENCE_REFS_DISAGREE",
                    "evidence refs and the observation-id list name different observations",
                )
        return self


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
    score_method: Annotated[str, VocabTerm("score_method")] = "heuristic"


class Abstention(ProtocolModel):
    """Why the system declined to name a single cause, and what would change that."""

    reasons: list[Annotated[str, VocabTerm("abstention_reason")]] = Field(default_factory=list)
    evidence_that_would_change_decision: list[str] = Field(default_factory=list)


class IncidentContext(ProtocolModel):
    description: str = ""
    zone: str | None = None
    trigger: Literal["telemetry_bundle", "community_candidate"] = "telemetry_bundle"
    incident_time: AwareDatetime | None = None


class Recommendation(ProtocolModel):
    """A suggested action. Always simulated and always needs human approval (doc 12 §3):
    neither flag can be set to False."""

    recommendation_id: str = Field(pattern=r"^RCM-\d{4,}$")
    action_text: str = Field(min_length=1)
    kind: Annotated[str, VocabTerm("recommendation_mode")]
    target_entities: list[str] = Field(default_factory=list)
    reason: str
    priority: Annotated[str, VocabTerm("recommendation_priority")]
    precautions: list[str] = Field(default_factory=list)
    requires_human_approval: bool = True
    simulated: bool = True
    verification_step: str
    linked_hypothesis_id: str | None = None

    @field_validator("requires_human_approval", "simulated")
    @classmethod
    def _always_true(cls, v: bool) -> bool:
        # Rule 6.
        if v is not True:
            raise rule_error(
                "RECOMMENDATION_SAFETY_VIOLATION",
                "rule 6: recommendations are always simulated and always need human approval",
            )
        return v


class ConflictTrailEntry(ProtocolModel):
    """One conflict in a decision's trail (protocol 1.2)."""

    conflict_id: str
    rule: ConflictRule
    status: Annotated[str, VocabTerm("conflict_status")]
    raised: bool = Field(default=False, description="A conflict_report was exchanged for it")
    preserved_observation_ids: list[str] = Field(
        default_factory=list, description="Kept on both sides when unresolved"
    )


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
    "Abstention",
    "ClarificationRecord",
    "ConfidenceCategory",
    "ConflictRecord",
    "EntityRef",
    "EvidenceRef",
    "Hypothesis",
    "IncidentContext",
    "Limitation",
    "NotAssessableItem",
    "Observation",
    "ProtocolModel",
    "Recommendation",
    "ScoredHypothesis",
    "SelfAssessment",
    "TimeWindow",
    "ToolCallRecord",
]
