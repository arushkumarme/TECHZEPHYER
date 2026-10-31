"""Public API schemas (doc 11 §7). Reports stay plain JSON objects: their contract is the
official report schema (doc 07), validated where they are produced."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from netcoop.orchestrator.faults import FAULTS
from netcoop.orchestrator.states import State


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["simulation"] = "simulation"
    banner: str
    version: str


class ScenarioInfo(BaseModel):
    id: str
    title: str
    provenance: str
    pdf_suggested_scenario: str | None = None


class RunRequest(BaseModel):
    """Options for running a scenario. Fault injection exists only to demonstrate degraded
    operation (S-10); it never touches anything outside the simulation."""

    fault_injection: dict[str, str] = Field(default_factory=dict)
    pause_after: State | None = None

    @field_validator("fault_injection")
    @classmethod
    def _known_faults(cls, value: dict[str, str]) -> dict[str, str]:
        for agent, fault in value.items():
            if fault not in FAULTS:
                raise ValueError(f"{agent}: fault must be one of {FAULTS}, got {fault!r}")
        return value


class IncidentSummary(BaseModel):
    incident_id: str
    state: str | None
    label: str | None = None
    source: str | None = None
    created_at: str | None = None
    status: str | None = None
    top_cause: str | None = None
    confidence: float | None = None
    affected_devices: list[str] = Field(default_factory=list)
    resumable: bool = False


class TransitionOut(BaseModel):
    seq: int
    from_state: str | None
    to_state: str
    trigger: str
    at: str
    message_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class IncidentDetail(IncidentSummary):
    transitions: list[TransitionOut]
    report: dict[str, Any] | None = None


class TraceEvent(BaseModel):
    kind: Literal["state", "message"]
    at: str
    seq: int
    summary: str
    message_id: str | None = None
    sender: str | None = None
    recipient: str | None = None
    type: str | None = None
    valid: bool = True
    error_code: str | None = None


class Trace(BaseModel):
    incident_id: str
    events: list[TraceEvent]


class ReviewItem(BaseModel):
    index: int
    action: str
    approval_state: str
    reviewer: str | None = None


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1, max_length=80, pattern=r"\S")
    note: str = Field(default="", max_length=500)


class ApprovalOut(BaseModel):
    incident_id: str
    action_index: int
    action: str
    decision: str
    reviewer: str
    note: str
    decided_at: str
    simulated_outcome: str | None
    incident_state: str | None
