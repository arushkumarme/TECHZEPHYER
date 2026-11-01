import { useEffect, useMemo, useState } from "react";
import { api, type BlastRadius, type IncidentSummary, type MapLayers, type Overlay, type Report } from "../api";
import { CampusMap, DEVICE_STATE_LABEL } from "../campus/CampusMap";
import { CAMPUS_FEATURES } from "../campus/features";
import { MapLists } from "../campus/MapLists";
import { deriveHighlight, type DeviceState, type Highlight } from "../campus/highlight";
import { PLACEMENT_NOTE, placeDevices } from "../campus/placement";
import { clusterByBuilding } from "../complaints/source";
import { sampleComplaintSource } from "../complaints/sample";
import type { ComplaintCluster } from "../complaints/types";

const featureName = new Map(CAMPUS_FEATURES.map((f) => [f.id, f.name]));

/** Swatches mirror the marker styles in CampusMap (solid = finding, hollow = consequence). */
export function Swatch({ kind }: { kind: "reported" | "corroborated" | "critical" | "isolated" | "warning" | "neutral" | "sample" | "path" | "ok" | "suspect" }) {
  const box = { width: 24, height: 14, viewBox: "0 0 24 14", className: "swatch", "aria-hidden": true } as const;
  switch (kind) {
    case "reported":
      return <svg {...box}><circle cx="12" cy="7" r="5.5" fill="var(--warning)" fillOpacity=".08" stroke="var(--warning)" strokeWidth="1.5" strokeDasharray="3 2" /></svg>;
    case "corroborated":
      return <svg {...box}><circle cx="12" cy="7" r="5.5" fill="#a48bf0" fillOpacity=".08" stroke="#a48bf0" strokeWidth="1.5" /></svg>;
    case "critical":
      return <svg {...box}><circle cx="12" cy="7" r="5" fill="var(--critical)" /></svg>;
    case "isolated":
      return <svg {...box}><circle cx="12" cy="7" r="4.5" fill="var(--bg)" stroke="var(--critical)" strokeWidth="2" /></svg>;
    case "warning":
      return <svg {...box}><circle cx="12" cy="7" r="4.5" fill="var(--bg)" stroke="var(--warning)" strokeWidth="2" /></svg>;
    case "ok":
      return <svg {...box}><circle cx="12" cy="7" r="5" fill="var(--ok)" /></svg>;
    case "suspect":
      return <svg {...box}><circle cx="12" cy="7" r="4.5" fill="var(--bg)" stroke="var(--warning)" strokeWidth="2" strokeDasharray="3 2" /></svg>;
    case "neutral":
      return <svg {...box}><circle cx="12" cy="7" r="4.5" fill="var(--bg)" stroke="var(--text)" strokeWidth="1.5" /></svg>;
    case "path":
      return <svg {...box}><path d="M2 10 Q12 2 22 10" fill="none" stroke="var(--critical)" strokeWidth="2.5" strokeLinecap="round" /></svg>;
    case "sample":
      return <svg {...box}><rect x="1" y="2" width="22" height="10" rx="3" fill="none" stroke="var(--muted)" strokeDasharray="2 2" /></svg>;
  }
}

/** Overlay the structural reach of a clicked device on the incident highlight, or hide it. */
function withBlast(base: Highlight, blast: BlastRadius | null, show: boolean): Highlight {
  const devices: Record<string, DeviceState> = {};
  for (const [id, s] of Object.entries(base.devices)) {
    // A clicked device's reach replaces the incident's; with the toggle off, no reach is drawn.
    const reach = s === "warning" || s === "isolated";
    devices[id] = reach && (!show || blast) ? "neutral" : s;
  }
  if (show && blast) {
    for (const id of blast.degraded) if (devices[id] === "neutral") devices[id] = "warning";
    for (const id of blast.isolated) if (devices[id] === "neutral") devices[id] = "isolated";
  }
  const focus = blast && show && !base.focus.includes(blast.failed) ? [...base.focus, blast.failed] : base.focus;
  return { ...base, devices, focus };
}

// The Campus map tab: the shared CampusMap, full width, with its controls, legend and footer.
export function MapView({ incidents, layers: shared }: { incidents: IncidentSummary[]; layers?: MapLayers | null }) {
  const [fetched, setFetched] = useState<MapLayers | null>(null);
  const [layersMissing, setLayersMissing] = useState(false);
  const [incident, setIncident] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [blast, setBlast] = useState<BlastRadius | null>(null);
  const [showBlast, setShowBlast] = useState(true);
  const [showSample, setShowSample] = useState(false);
  const [complaints, setComplaints] = useState<ComplaintCluster[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openRequest, setOpenRequest] = useState<{ kind: "device" | "building"; id: string; seq: number } | null>(null);
  const requestOpen = (kind: "device" | "building", id: string) =>
    setOpenRequest((r) => ({ kind, id, seq: (r?.seq ?? 0) + 1 }));

  // Prefer the layers App already fetched; fetch here only if they are not there yet.
  useEffect(() => {
    if (shared) return;
    api.layers().then(setFetched).catch(() => setLayersMissing(true));
  }, [shared]);
  const layers = shared ?? fetched;

  useEffect(() => {
    setReport(null);
    setOverlay(null);
    if (!incident) return;
    let current = true;
    api.incident(incident).then((d) => current && setReport(d.report)).catch((e: Error) => current && setError(e.message));
    api.overlay(incident).then((o) => current && setOverlay(o)).catch((e: Error) => current && setError(e.message));
    return () => { current = false; };
  }, [incident]);

  useEffect(() => {
    if (!showSample || complaints) return;
    let current = true;
    sampleComplaintSource.list().then((m) => current && setComplaints(clusterByBuilding(m)));
    return () => { current = false; };
  }, [showSample, complaints]);

  const placement = useMemo(() => (layers ? placeDevices(layers.devices) : null), [layers]);
  const highlight = useMemo(
    () => (layers ? withBlast(deriveHighlight(report, layers, overlay), blast, showBlast) : null),
    [layers, report, overlay, blast, showBlast],
  );
  const reportedZones = useMemo(() => {
    if (!overlay) return [];
    const corroborated = new Set(overlay.corroborated.map((c) => c.zone));
    const zones = new Set([...overlay.reported_areas.map((a) => a.zone), ...corroborated]);
    return [...zones].map((zone) => ({ zone, corroborated: corroborated.has(zone) }));
  }, [overlay]);

  const shown = showBlast ? (blast ?? Object.values(overlay?.blast_radius ?? {})[0] ?? null) : null;

  const deviceInfo = (id: string) => {
    const d = placement?.placed.find((p) => p.id === id);
    const state = highlight?.devices[id] ?? "neutral";
    const b = blast?.failed === id ? blast : null;
    return (
      <>
        <h3 className="pop-title mono">{id}</h3>
        <p className="label">{d?.role} switch · simulated</p>
        <dl className="pop-dl">
          <dt>Zone</dt><dd className="mono">{d?.zone}</dd>
          <dt>Drawn at</dt><dd>{d ? featureName.get(d.buildingId) : "not placed"}</dd>
          <dt>State</dt><dd>{DEVICE_STATE_LABEL[state]}</dd>
        </dl>
        <p className="pop-sub">If this switch failed</p>
        {b ? (
          <p className="small">{b.isolated.length} would be isolated, {b.degraded.length} would lose redundancy. Structural reach in the simulated topology, not measured impact.</p>
        ) : (
          <p className="small muted">Working out the structural reach…</p>
        )}
      </>
    );
  };

  if (!layers && !layersMissing) return <p className="muted">Loading map…</p>;

  return (
    <div className="map-tab">
      <div className="map-head">
        <h2>Campus map</h2>
        <div className="map-controls" role="group" aria-label="Map controls">
          <label htmlFor="map-incident">Show incident</label>
          <select
            id="map-incident"
            value={incident}
            onChange={(e) => { setBlast(null); setError(null); setIncident(e.target.value); }}
          >
            <option value="">None — topology only</option>
            {incidents.filter((i) => i.status).map((i) => (
              <option key={i.incident_id} value={i.incident_id}>{i.incident_id} — {i.label ?? ""} ({i.status})</option>
            ))}
          </select>
          <label className="toggle">
            <input type="checkbox" checked={showBlast} onChange={(e) => setShowBlast(e.target.checked)} />
            Blast radius
          </label>
          <label className="toggle">
            <input type="checkbox" checked={showSample} onChange={(e) => setShowSample(e.target.checked)} />
            Sample reports (demo data)
          </label>
        </div>
      </div>
      {error && <div className="error-box" role="alert">Map data unavailable: {error}</div>}

      <div className="map-wrap">
        <CampusMap
          variant="full"
          layers={layers}
          highlight={highlight}
          reportedZones={reportedZones}
          complaints={showSample ? complaints : null}
          deviceInfo={layers ? deviceInfo : undefined}
          openRequest={openRequest}
          onDeviceClick={(id) => { api.blast(id).then(setBlast).catch((e: Error) => setError(e.message)); }}
        />
        <aside className="legend panel" aria-label="Map legend">
          <h3 className="label">Legend</h3>
          <ul>
            <li><Swatch kind="reported" />Reported by users (unverified)</li>
            <li><Swatch kind="corroborated" />Reported and confirmed by telemetry</li>
            <li><Swatch kind="critical" />Detected fault (telemetry)</li>
            <li><Swatch kind="path" />Path from the fault to the core</li>
            <li><Swatch kind="isolated" />Would be isolated</li>
            <li><Swatch kind="warning" />Would lose redundancy</li>
            <li><Swatch kind="neutral" />Device, no finding</li>
            {showSample && <li><Swatch kind="sample" />Illustrative demo data, not real reports</li>}
          </ul>
          {placement && placement.notPlaced.length > 0 && (
            <p className="legend-note">Not placed: <span className="mono">{placement.notPlaced.join(", ")}</span></p>
          )}
          <p className="legend-note">{PLACEMENT_NOTE}</p>
          <p className="legend-note muted">
            Click a switch to see what would happen if it failed.
            {shown && <> Showing failure of <span className="mono">{shown.failed}</span>: {shown.isolated.length} isolated, {shown.degraded.length} would lose redundancy.</>}
            {" "}Blast radius is structural reach in the simulated topology, not measured impact.
          </p>
          <MapLists
            devices={layers ? (placement?.placed ?? []) : []}
            onDevice={(id) => requestOpen("device", id)}
            onBuilding={(id) => requestOpen("building", id)}
          />
        </aside>
      </div>

      {layers && (
        <footer className="map-about">
          <h3 className="label">About this data</h3>
          <p>{layers.provenance_note}</p>
        </footer>
      )}
    </div>
  );
}
