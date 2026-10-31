"""NetCoop AI backend API (FastAPI; decision CD-3: separate from the React dashboard).

Read-only resources for incidents, scenarios, reports, traces and topology, plus four
write paths that act only inside the simulation: run a scenario, submit a telemetry
bundle, resume an incident, and record a human review decision (whose outcome is
simulated). No endpoint can change a network device.

Run: ``uv run fastapi dev`` (entrypoint in pyproject) or ``uv run fastapi run``.
The database path comes from ``NETCOOP_DB`` (default ``var/netcoop.sqlite3``).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

import netcoop
from netcoop.api.models import (
    ApprovalOut,
    Health,
    IncidentDetail,
    IncidentSummary,
    ReviewDecision,
    ReviewItem,
    RunRequest,
    ScenarioInfo,
    Trace,
    TraceEvent,
    TransitionOut,
)
from netcoop.config.fields import load_field_dictionary
from netcoop.config.settings import Settings, load_settings
from netcoop.core.log_store import LogStore
from netcoop.orchestrator.review import ReviewError, ReviewService
from netcoop.orchestrator.states import RESUMABLE
from netcoop.orchestrator.trace import summarize_message
from netcoop.orchestrator.workflow import IncidentResult, Orchestrator
from netcoop.report.builder import strict_official
from netcoop.scenarios.generator import REPO_ROOT
from netcoop.scenarios.runner import list_scenarios, load_scenario
from netcoop.tools.topology import TopologyError, load_topology

BANNER = "SIMULATED DATA - scenario playback; NetCoop AI has no access to any real network"
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class Backend:
    """Everything the endpoints need, created once per app."""

    def __init__(self, store: LogStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    def orchestrator(self, faults: dict[str, str] | None = None) -> Orchestrator:
        return Orchestrator(self.store, settings=self.settings, fault_injection=faults)

    def state(self, incident: str) -> str | None:
        t = self.store.transitions(incident)
        return t[-1].to_state if t else None

    def require(self, incident: str) -> None:
        if incident not in self.store.list_incidents():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown incident {incident}")

    def summary(self, incident: str) -> IncidentSummary:
        meta = self.store.incident_meta(incident) or {}
        stored = self.store.latest_report(incident)
        report = stored[0] if stored else {}
        state = self.state(incident)
        return IncidentSummary(
            incident_id=incident,
            state=state,
            label=meta.get("label"),
            source=meta.get("source"),
            created_at=meta.get("created_at"),
            status=report.get("status"),
            top_cause=report.get("netcoop_extensions", {}).get("top_cause_type"),
            confidence=report.get("confidence"),
            affected_devices=report.get("affected_devices", []),
            resumable=state in RESUMABLE,
        )


def get_backend(request: Request) -> Backend:
    backend: Backend = request.app.state.backend
    return backend


BackendDep = Annotated[Backend, Depends(get_backend)]


# ------------------------------------------------------------------------- system
system = APIRouter(prefix="/api", tags=["system"])


@system.get("/health")
def health() -> Health:
    return Health(banner=BANNER, version=netcoop.__version__)


@system.get("/field-dictionary")
def field_dictionary() -> dict[str, Any]:
    data: dict[str, Any] = load_field_dictionary().model_dump(by_alias=True)
    return data


@system.get("/topology/{topology_id}")
def topology(topology_id: str) -> dict[str, Any]:
    try:
        data: dict[str, Any] = load_topology(topology_id).model_dump()
    except (TopologyError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return data


# ------------------------------------------------------------------------- scenarios
scenarios = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


@scenarios.get("")
def list_all_scenarios() -> list[ScenarioInfo]:
    out = []
    for sid in list_scenarios():
        meta = load_scenario(sid).meta
        out.append(
            ScenarioInfo(
                id=sid,
                title=meta["title"],
                provenance=meta["provenance"],
                pdf_suggested_scenario=meta.get("pdf_suggested_scenario"),
            )
        )
    return out


def _scenario_or_404(scenario_id: str) -> Any:
    if scenario_id not in list_scenarios():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown scenario {scenario_id}")
    return load_scenario(scenario_id)


@scenarios.get("/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict[str, Any]:
    meta: dict[str, Any] = _scenario_or_404(scenario_id).meta
    return meta


@scenarios.post("/{scenario_id}/run", status_code=status.HTTP_201_CREATED)
def run_scenario(scenario_id: str, options: RunRequest, backend: BackendDep) -> IncidentSummary:
    sc = _scenario_or_404(scenario_id)
    faults = {**sc.meta.get("run", {}).get("fault_injection", {}), **options.fault_injection}
    result = backend.orchestrator(faults).run(
        sc.input_bytes,
        source=f"api:scenario:{scenario_id}",
        label=scenario_id,
        pause_after=options.pause_after,
    )
    return backend.summary(result.incident_id)


# ------------------------------------------------------------------------- incidents
incidents = APIRouter(prefix="/api/incidents", tags=["incidents"])


@incidents.get("")
def list_incidents(backend: BackendDep) -> list[IncidentSummary]:
    return [backend.summary(i) for i in reversed(backend.store.list_incidents())]


@incidents.post("", status_code=status.HTTP_201_CREATED)
def submit_bundle(
    bundle: Annotated[dict[str, Any] | list[Any], Body()], backend: BackendDep
) -> IncidentSummary:
    """Diagnose a telemetry bundle (doc 05 §11 layout). Invalid bundles become REJECTED
    incidents with a failure report - the request itself still succeeds."""
    result: IncidentResult = backend.orchestrator().run(
        json.dumps(bundle), source="api:upload", label="uploaded bundle"
    )
    return backend.summary(result.incident_id)


@incidents.get("/{incident_id}")
def incident_detail(incident_id: str, backend: BackendDep) -> IncidentDetail:
    backend.require(incident_id)
    stored = backend.store.latest_report(incident_id)
    return IncidentDetail(
        **backend.summary(incident_id).model_dump(),
        transitions=[
            TransitionOut(
                seq=t.seq,
                from_state=t.from_state,
                to_state=t.to_state,
                trigger=t.trigger,
                at=t.at,
                message_id=t.message_id,
                detail=t.detail,
            )
            for t in backend.store.transitions(incident_id)
        ],
        report=stored[0] if stored else None,
    )


@incidents.get("/{incident_id}/report")
def incident_report(incident_id: str, backend: BackendDep, strict: bool = False) -> dict[str, Any]:
    backend.require(incident_id)
    stored = backend.store.latest_report(incident_id)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{incident_id} has no report yet")
    return strict_official(stored[0]) if strict else stored[0]


@incidents.get("/{incident_id}/report.md", response_class=PlainTextResponse)
def incident_report_markdown(incident_id: str, backend: BackendDep) -> PlainTextResponse:
    backend.require(incident_id)
    stored = backend.store.latest_report(incident_id)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{incident_id} has no report yet")
    return PlainTextResponse(stored[1], media_type="text/markdown")


@incidents.get("/{incident_id}/trace")
def incident_trace(incident_id: str, backend: BackendDep) -> Trace:
    backend.require(incident_id)
    events = [
        TraceEvent(
            kind="state",
            at=t.at,
            seq=t.seq,
            summary=f"{t.from_state or '-'} -> {t.to_state} ({t.trigger})",
            type=t.to_state,
        )
        for t in backend.store.transitions(incident_id)
    ]
    for m in backend.store.messages(incident_id):
        try:
            payload = json.loads(m.raw_json).get("payload", {})
        except (json.JSONDecodeError, AttributeError):
            payload = {}
        events.append(
            TraceEvent(
                kind="message",
                at=m.sent_at or "",
                seq=m.seq,
                summary=summarize_message(
                    m.message_type, payload if isinstance(payload, dict) else {}
                ),
                message_id=m.message_id,
                sender=m.sender,
                recipient=m.recipient,
                type=m.message_type,
                valid=m.valid,
                error_code=m.error_code,
            )
        )
    from netcoop.ingestion.normalize import parse_timestamp

    def when(e: TraceEvent) -> tuple[Any, int, int]:
        t = parse_timestamp(e.at)
        return (t.timestamp() if t else 0.0, 0 if e.kind == "state" else 1, e.seq)

    return Trace(incident_id=incident_id, events=sorted(events, key=when))


@incidents.get("/{incident_id}/messages/{message_id}")
def incident_message(incident_id: str, message_id: str, backend: BackendDep) -> dict[str, Any]:
    backend.require(incident_id)
    for m in backend.store.messages(incident_id):
        if m.message_id == message_id:
            try:
                data: dict[str, Any] = json.loads(m.raw_json)
            except json.JSONDecodeError:
                data = {"raw": m.raw_json}
            return {**data, "valid": m.valid, "error_code": m.error_code}
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown message {message_id}")


@incidents.post("/{incident_id}/resume")
def resume_incident(incident_id: str, backend: BackendDep) -> IncidentSummary:
    backend.require(incident_id)
    backend.orchestrator().resume(incident_id)
    return backend.summary(incident_id)


@incidents.get("/{incident_id}/review")
def review_items(incident_id: str, backend: BackendDep) -> list[ReviewItem]:
    backend.require(incident_id)
    try:
        pending = ReviewService(backend.store).pending(incident_id)
    except ReviewError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return [
        ReviewItem(
            index=p.index, action=p.action, approval_state=p.approval_state, reviewer=p.reviewer
        )
        for p in pending
    ]


@incidents.post("/{incident_id}/review/{index}")
def review_decide(
    incident_id: str, index: int, body: ReviewDecision, backend: BackendDep
) -> ApprovalOut:
    """Record a human decision on one recommendation. Approval yields a SIMULATED outcome;
    nothing outside the simulation is changed."""
    backend.require(incident_id)
    svc = ReviewService(backend.store)
    try:
        rec = svc.decide(incident_id, index, body.decision, reviewer=body.reviewer, note=body.note)
    except ReviewError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ApprovalOut(
        incident_id=rec.incident_id,
        action_index=rec.action_index,
        action=rec.action,
        decision=rec.decision,
        reviewer=rec.reviewer,
        note=rec.note,
        decided_at=rec.decided_at,
        simulated_outcome=rec.simulated_outcome,
        incident_state=svc.state(incident_id),
    )


# ------------------------------------------------------------------------- factory
Extension = Callable[[FastAPI, Backend], None]
EXTENSIONS: list[Extension] = []  # feature-flagged routers register here (docs 10, 11)


def create_app(*, db_path: Path | str | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    path = Path(db_path or os.environ.get("NETCOOP_DB") or REPO_ROOT / "var" / "netcoop.sqlite3")
    app = FastAPI(
        title="NetCoop AI",
        version=netcoop.__version__,
        description=f"Multi-agent network fault diagnosis. {BANNER}.",
    )
    app.state.backend = Backend(LogStore(path), settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    for router in (system, scenarios, incidents):
        app.include_router(router)
    for extension in EXTENSIONS:
        extension(app, app.state.backend)
    return app


app = create_app()
