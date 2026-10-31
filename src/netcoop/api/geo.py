"""Extension B API (doc 11 §7): read-only map layers, blast radius, incident overlay.
Registered only when ``features.geospatial`` is on (doc 02 §6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, status

from netcoop.api.app import EXTENSIONS, Backend, BackendDep
from netcoop.geo.layers import blast_radius, campus_layers, incident_overlay
from netcoop.tools.topology import TopologyError

router = APIRouter(prefix="/api/geo", tags=["geo (extension B)"])


@router.get("/layers")
def layers(topology: str = "campus_v1") -> dict[str, Any]:
    try:
        return campus_layers(topology)
    except TopologyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/blast-radius/{entity}")
def entity_blast_radius(entity: str, topology: str = "campus_v1") -> dict[str, Any]:
    try:
        return blast_radius(topology, entity)
    except TopologyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/incidents/{incident_id}")
def overlay(incident_id: str, backend: BackendDep) -> dict[str, Any]:
    backend.require(incident_id)
    try:
        return incident_overlay(backend.store, incident_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def register(app: FastAPI, backend: Backend) -> None:
    if backend.settings.features.geospatial:
        app.include_router(router)


EXTENSIONS.append(register)
