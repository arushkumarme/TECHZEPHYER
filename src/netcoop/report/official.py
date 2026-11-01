"""The official incident report (doc 07 §1) as a strict model: exactly the ten keys of the
problem statement's example, in its order, with its types. Nothing added, renamed or dropped."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SupportingEvidence(_Strict):
    metric: str
    value: float | int | str
    interpretation: str


class OfficialReport(_Strict):
    incident_id: str = Field(min_length=1)
    status: Literal["diagnosed", "insufficient_evidence", "no_fault_detected", "failed"]
    suspected_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    affected_devices: list[str]
    supporting_evidence: list[SupportingEvidence]
    alternative_causes: list[str]
    recommended_actions: list[str]
    evidence_sources: list[str]
    limitations: list[str]


OFFICIAL_REPORT_KEYS: tuple[str, ...] = tuple(OfficialReport.model_fields)
