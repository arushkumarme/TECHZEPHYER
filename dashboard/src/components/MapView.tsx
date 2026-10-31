import { CRS, type LatLngBoundsExpression, type LatLngExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, Polygon, Polyline, Tooltip } from "react-leaflet";
import { api, type BlastRadius, type IncidentSummary, type MapLayers, type Overlay } from "../api";

const C = { link: "#1f5fa8", red: "#b42318", amber: "#b7791f", violet: "#6941c6", ink: "#1c2833", grey: "#8a96a3" };

// Schematic, non-geographic map (decision ID-17): Leaflet CRS.Simple with x/y units, so no
// tile server is needed and nothing implies real campus geography.
export function MapView({ incidents }: { incidents: IncidentSummary[] }) {
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [incident, setIncident] = useState<string>("");
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [blast, setBlast] = useState<BlastRadius | null>(null);
  const [showBlast, setShowBlast] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.layers().then(setLayers).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!incident) return setOverlay(null);
    api.overlay(incident).then(setOverlay).catch((e: Error) => setError(e.message));
  }, [incident]);

  if (error) return <div className="error-box">Map unavailable: {error}</div>;
  if (!layers) return <p className="muted">Loading map…</p>;

  const reported = new Set(overlay?.reported_areas.map((a) => a.zone));
  const corroborated = new Set(overlay?.corroborated.map((a) => a.zone));
  const detected = new Set(overlay?.detected_faults.map((d) => d.entity));
  const shown = blast ?? Object.values(overlay?.blast_radius ?? {})[0] ?? null;
  const isolated = new Set(showBlast ? shown?.isolated : []);
  const degraded = new Set(showBlast ? shown?.degraded : []);

  return (
    <div>
      <h2>Campus map</h2>
      <p className="muted small">{layers.provenance_note}</p>
      <div className="row" style={{ marginBottom: "0.75rem" }}>
        <label htmlFor="map-incident" style={{ margin: 0 }}>Show incident</label>
        <select id="map-incident" value={incident} onChange={(e) => { setBlast(null); setIncident(e.target.value); }} style={{ maxWidth: "22rem" }}>
          <option value="">None — topology only</option>
          {incidents.filter((i) => i.status).map((i) => (
            <option key={i.incident_id} value={i.incident_id}>{i.incident_id} — {i.label ?? ""} ({i.status})</option>
          ))}
        </select>
        <label style={{ margin: 0, display: "flex", gap: "0.35rem", alignItems: "center" }}>
          <input type="checkbox" checked={showBlast} onChange={(e) => setShowBlast(e.target.checked)} style={{ width: "auto" }} />
          Blast radius
        </label>
      </div>
      <div className="map-wrap">
        <MapContainer
          className="map"
          crs={CRS.Simple}
          bounds={layers.bounds as LatLngBoundsExpression}
          minZoom={-2}
          maxZoom={2}
          zoomSnap={0.25}
          attributionControl={false}
        >
          {layers.zones.map((z) => {
            const isRep = reported.has(z.zone);
            const isCor = corroborated.has(z.zone);
            return (
              <Polygon
                key={z.zone}
                positions={z.polygon as LatLngExpression[]}
                pathOptions={{
                  color: isCor ? C.violet : isRep ? C.amber : C.grey,
                  weight: isRep || isCor ? 3 : 1,
                  dashArray: isRep && !isCor ? "8 6" : undefined,
                  fillOpacity: isCor ? 0.18 : isRep ? 0.12 : 0.04,
                  fillColor: isCor ? C.violet : isRep ? C.amber : C.grey,
                }}
              >
                <Tooltip permanent direction="center" offset={[0, -24]} className="zone-label">
                  {z.label.replace(" (placeholder)", "")}
                  {isCor ? " · confirmed" : isRep ? " · reported" : ""}
                </Tooltip>
              </Polygon>
            );
          })}
          {layers.links.map((l) => (
            <Polyline key={l.id} positions={[l.from, l.to] as LatLngExpression[]} pathOptions={{ color: C.link, weight: 2, opacity: 0.7 }} />
          ))}
          {layers.devices.map((d) => {
            const isDet = detected.has(d.id);
            const iso = isolated.has(d.id);
            const deg = degraded.has(d.id);
            return (
              <CircleMarker
                key={d.id}
                center={d.position as LatLngExpression}
                radius={d.core ? 11 : isDet ? 10 : 7}
                eventHandlers={{ click: () => api.blast(d.id).then(setBlast) }}
                pathOptions={{
                  color: isDet ? C.red : iso ? C.ink : deg ? C.amber : C.link,
                  weight: isDet ? 4 : iso || deg ? 3 : 2,
                  dashArray: deg ? "3 3" : undefined,
                  fillColor: isDet ? C.red : iso ? C.ink : "#ffffff",
                  fillOpacity: isDet || iso ? 0.85 : 1,
                }}
              >
                <Tooltip>
                  {d.id} ({d.role}){isDet ? " — detected fault" : iso ? " — would be isolated" : deg ? " — would lose redundancy" : ""}
                </Tooltip>
              </CircleMarker>
            );
          })}
        </MapContainer>
        <aside className="legend" aria-label="Map legend">
          <h3>Legend</h3>
          <ul>
            <li><svg className="swatch"><rect x="1" y="1" width="24" height="12" fill="none" stroke={C.amber} strokeWidth="2.5" strokeDasharray="5 3" /></svg>Reported by users (unverified)</li>
            <li><svg className="swatch"><rect x="1" y="1" width="24" height="12" fill={C.violet} fillOpacity=".2" stroke={C.violet} strokeWidth="2.5" /></svg>Reported and confirmed by telemetry</li>
            <li><svg className="swatch"><circle cx="13" cy="7" r="6" fill={C.red} stroke={C.red} strokeWidth="3" /></svg>Detected fault (telemetry)</li>
            <li><svg className="swatch"><circle cx="13" cy="7" r="5" fill={C.ink} /></svg>Would be isolated</li>
            <li><svg className="swatch"><circle cx="13" cy="7" r="5" fill="#fff" stroke={C.amber} strokeWidth="2.5" strokeDasharray="2 2" /></svg>Would lose redundancy</li>
            <li><svg className="swatch"><circle cx="13" cy="7" r="5" fill="#fff" stroke={C.link} strokeWidth="2" /></svg>Device, no finding</li>
          </ul>
          <p className="small muted">
            Click a device to see what would happen if it failed. {shown ? `Showing failure of ${shown.failed}: ${shown.isolated.length} isolated, ${shown.degraded.length} degraded.` : ""} Blast radius is structural reach in the simulated topology, not measured impact.
          </p>
        </aside>
      </div>
    </div>
  );
}
