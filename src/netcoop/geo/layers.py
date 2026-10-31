"""Geospatial Network Intelligence backend (Extension B, doc 11). Read-only.

The map is a **schematic, non-geographic** layout (decision ID-17): no verified campus
coordinates exist (D-08), so positions are illustrative x/y units rendered with Leaflet's
``CRS.Simple``. This also satisfies the offline requirement (doc 11 §8): no map tiles.
Every layer carries a provenance label; reported areas (complaints) and detected faults
(telemetry) are separate layers with distinct styles; blast radius is computed here from
the SIMULATED topology - structural reach, never measured impact.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from netcoop.core.log_store import LogStore
from netcoop.tools.topology import TOPOLOGY_DIR, TopologyError, load_topology

BANNER = "SIMULATED DATA - schematic scenario playback; not a map of the real campus"


class ZoneShape(BaseModel):
    model_config = ConfigDict(frozen=True)
    zone: str
    label: str
    polygon: list[tuple[float, float]]


class DevicePosition(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    position: tuple[float, float]


class Layout(BaseModel):
    model_config = ConfigDict(frozen=True)
    layout_id: str
    topology_id: str
    provenance: str
    provenance_note: str
    crs: str
    bounds: list[tuple[float, float]]
    zones: list[ZoneShape]
    devices: list[DevicePosition]


def load_layout(topology_id: str) -> Layout:
    path = TOPOLOGY_DIR / f"{topology_id}_layout.json"
    if not path.is_file():
        raise TopologyError(f"no layout for topology {topology_id}")
    layout = Layout.model_validate(json.loads(path.read_text(encoding="utf-8")))
    topo = load_topology(topology_id)
    missing = {n.id for n in topo.nodes} - {d.id for d in layout.devices}
    if missing:
        raise TopologyError(f"layout lacks positions for {sorted(missing)}")
    return layout


def campus_layers(topology_id: str) -> dict[str, Any]:
    topo = load_topology(topology_id)
    layout = load_layout(topology_id)
    pos = {d.id: d.position for d in layout.devices}
    prov = layout.provenance
    return {
        "layout_id": layout.layout_id,
        "topology_id": topology_id,
        "crs": layout.crs,
        "bounds": layout.bounds,
        "banner": BANNER,
        "provenance_note": layout.provenance_note,
        "zones": [{**z.model_dump(), "provenance": prov} for z in layout.zones],
        "devices": [
            {
                "id": n.id,
                "role": n.role,
                "zone": n.zone,
                "position": pos[n.id],
                "core": n.id in topo.core_nodes,
                "provenance": prov,
            }
            for n in topo.nodes
        ],
        "links": [
            {
                "id": link.id,
                "a": link.a,
                "b": link.b,
                "from": pos[link.a],
                "to": pos[link.b],
                "provenance": prov,
            }
            for link in topo.links
        ],
    }


def blast_radius(topology_id: str | None, entity: str) -> dict[str, Any]:
    """Isolated / degraded / unaffected / unknown if ``entity`` failed (doc 11 §4)."""
    basis = "structural reach in the SIMULATED topology, not measured impact"
    if topology_id is None:
        return {
            "failed": entity,
            "isolated": [],
            "degraded": [],
            "unaffected": [],
            "unknown": [entity],
            "zones_isolated": [],
            "zones_degraded": [],
            "basis": basis,
        }
    topo = load_topology(topology_id)
    r = topo.what_if_failure(entity)

    def zones(ids: list[str]) -> list[str]:
        return sorted({z for e in ids if (z := topo.zone_of(e)) is not None})

    return {
        **r.model_dump(),
        "zones_isolated": zones(r.isolated),
        "zones_degraded": zones(r.degraded),
        "basis": basis,
    }


def _topology_ref(store: LogStore, incident: str) -> str | None:
    for cp in store.checkpoints(incident):
        if cp["kind"] == "input":
            try:
                raw = json.loads(base64.b64decode(cp["data"]["raw_b64"]))
            except (ValueError, KeyError):
                return None
            ref = raw.get("topology_ref") if isinstance(raw, dict) else None
            return ref if isinstance(ref, str) else None
    return None


def incident_overlay(store: LogStore, incident: str) -> dict[str, Any]:
    stored = store.latest_report(incident)
    if stored is None:
        raise KeyError(f"{incident} has no report")
    report = stored[0]
    ext = report.get("netcoop_extensions", {})
    topology_id = _topology_ref(store, incident)
    try:
        topo = load_topology(topology_id) if topology_id else None
    except TopologyError:
        topo, topology_id = None, None
    signals = ext.get("community_signals", [])
    trust = ext.get("community_trust", {})
    diagnosed = report["status"] == "diagnosed"
    detected = [
        {
            "entity": e,
            "zone": topo.zone_of(e) if topo else None,
            "cause": ext.get("top_cause_type"),
            "confidence": report["confidence"],
            "trust_label": trust.get(e, "detected"),
            "style": "detected",
        }
        for e in (report["affected_devices"] if diagnosed else [])
    ]
    reported = [
        {
            "zone": s["zone"],
            "candidate_id": s["candidate_id"],
            "entities": s["entities"],
            "distinct_reporters": s["distinct_reporters"],
            "complaint_count": s["complaint_count"],
            "trust_label": s["trust_label"],
            "style": "reported",
        }
        for s in signals
    ]
    corroborated = [
        {
            "zone": s["zone"],
            "candidate_id": s["candidate_id"],
            "entities": s["entities"],
            "style": "corroborated",
        }
        for s in signals
        if s["trust_label"] == "corroborated"
    ]
    blasts = {
        e: blast_radius(topology_id, e) for e in (report["affected_devices"] if diagnosed else [])
    }
    panel = {
        "incident_id": incident,
        "status": report["status"],
        "suspected_root_cause": report["suspected_root_cause"],
        "confidence": report["confidence"],
        "confidence_method": ext.get("confidence_method", "heuristic"),
        "confidence_category": ext.get("confidence_category"),
        "affected_devices": report["affected_devices"],
        "supporting_evidence": report["supporting_evidence"],
        "alternative_causes": report["alternative_causes"],
        "limitations": report["limitations"],
        "not_assessable": ext.get("not_assessable", []),
        "recommendations": ext.get("recommendation_status", []),
        "blast_radius": blasts,
        "community_summary": signals,
        "trace_url": f"/api/incidents/{incident}/trace",
    }
    return {
        "incident_id": incident,
        "banner": BANNER,
        "topology_id": topology_id,
        "reported_areas": reported,
        "detected_faults": detected,
        "corroborated": corroborated,
        "blast_radius": blasts,
        "panel": panel,
    }
