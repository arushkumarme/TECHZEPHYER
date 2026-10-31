"""Normalized bundle, data-quality note and ingestion result (doc 05 §6)."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from netcoop.core.blocks import TimeWindow
from netcoop.core.vocab import Assessability, NotAssessableReason
from netcoop.ingestion.issues import IngestIssue

Acceptance = Literal["READY", "READY_WITH_WARNINGS", "REJECTED"]

#: The eight assessable items per entity: seven doc-06 metrics plus device status.
STATUS_ITEM = "status"


class NormalizedRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_id: str
    source_index: int = Field(description="Index of the raw record in the input bundle")
    entity: str
    timestamp: AwareDatetime
    status: Literal["Healthy", "Warning", "Critical"] | None
    metrics: dict[str, float] = Field(description="Canonical name -> value in canonical unit")
    flags: list[str] = Field(default_factory=list)


class MetricState(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessability: Assessability
    reason: NotAssessableReason | None = None
    detail: str = ""


class ProbeResult(BaseModel):
    """Team-authored service check (doc 08 §3.3). Never generator telemetry."""

    model_config = ConfigDict(frozen=True)

    probe_id: str
    from_entity: str
    service: Literal["dns", "dhcp"]
    outcome: Literal["success", "failure", "timeout"]
    response_ms: float | None = None
    timestamp: AwareDatetime
    provenance: Literal["team-authored probe"] = "team-authored probe"


class DataQualityNote(BaseModel):
    model_config = ConfigDict(frozen=True)

    completeness: float = Field(ge=0, le=1)
    freshness: float = Field(ge=0, le=1)
    consistency: float = Field(ge=0, le=1)
    acceptance: Acceptance
    warnings: list[str] = Field(default_factory=list, description="Distinct warning codes")

    @property
    def q(self) -> float:
        """Combined data quality used for the confidence ceiling (doc 08 §4.3)."""
        return min(self.completeness, self.freshness, self.consistency)


class NormalizedBundle(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    schema_version: str | None
    provenance: str
    topology_ref: str | None
    records: list[NormalizedRecord]
    entities: list[str]
    window: TimeWindow
    metric_states: dict[tuple[str, str], MetricState]
    probes: list[ProbeResult] = Field(default_factory=list)
    data_quality: DataQualityNote
    assessable_items: list[str]


class IngestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    acceptance: Acceptance
    bundle: NormalizedBundle | None
    issues: list[IngestIssue]
    rejection_code: str | None = None
