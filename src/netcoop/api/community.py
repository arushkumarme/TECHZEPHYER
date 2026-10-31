"""Extension A API (doc 10 §2: the web form is the primary complaint channel).

Registered only when ``features.community_signals`` is on (doc 02 §6). Complaints are
synthetic test submissions in hackathon mode; responses never echo reporter identities.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from netcoop.api.app import EXTENSIONS, Backend, BackendDep
from netcoop.api.models import IncidentSummary
from netcoop.community.pipeline import CommunityPipeline
from netcoop.scenarios.runner import list_scenarios, load_scenario


class ComplaintIn(BaseModel):
    text: str = Field(max_length=2000, description="What the user experienced")
    reporter: str = Field(min_length=1, max_length=120, description="Pseudonymized at intake")
    channel: str = Field(default="web_form", pattern=r"^(web_form|telegram_test)$")


class ComplaintAck(BaseModel):
    accepted: bool
    duplicate: bool
    complaint_id: str | None
    reason: str | None
    zone: str | None
    symptoms: list[str]
    notice: str = "Thank you. Reports are unverified until network telemetry agrees."


class InvestigateIn(BaseModel):
    scenario_id: str = Field(description="Synthetic telemetry to investigate against")


def get_pipeline(request: Request) -> CommunityPipeline:
    pipeline: CommunityPipeline = request.app.state.community
    return pipeline


PipelineDep = Annotated[CommunityPipeline, Depends(get_pipeline)]
router = APIRouter(prefix="/api/community", tags=["community (extension A)"])


@router.post("/complaints", status_code=status.HTTP_201_CREATED)
def submit_complaint(body: ComplaintIn, pipeline: PipelineDep) -> ComplaintAck:
    r = pipeline.submit(
        body.text, channel=body.channel, reporter=body.reporter, received_at=datetime.now(UTC)
    )
    return ComplaintAck(
        accepted=r.accepted,
        duplicate=r.duplicate,
        complaint_id=r.complaint_id,
        reason=r.reason,
        zone=r.zone,
        symptoms=list(r.symptoms),
    )


@router.get("/candidates")
def list_candidates(pipeline: PipelineDep) -> list[dict[str, Any]]:
    return [c.model_dump(mode="json") for c in pipeline.candidates()]


@router.get("/stats")
def complaint_stats(pipeline: PipelineDep) -> dict[str, int]:
    """Aggregate counts only - individual messages are not exposed (doc 12 §5)."""
    return pipeline.stats()


@router.post("/candidates/{candidate_id}/investigate", status_code=status.HTTP_201_CREATED)
def investigate(
    candidate_id: str, body: InvestigateIn, pipeline: PipelineDep, backend: BackendDep
) -> IncidentSummary:
    if body.scenario_id not in list_scenarios():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown scenario {body.scenario_id}")
    try:
        result = pipeline.investigate(
            candidate_id, backend.orchestrator(), load_scenario(body.scenario_id).input_bytes
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return backend.summary(result.incident_id)


def register(app: FastAPI, backend: Backend) -> None:
    if not backend.settings.features.community_signals:
        return
    app.state.community = CommunityPipeline(backend.store, llm=backend.orchestrator().llm)
    app.include_router(router)


EXTENSIONS.append(register)
