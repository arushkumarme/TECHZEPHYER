import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type IncidentDetail, type MapLayers, type Overlay, type ReviewItem, type TraceEvent } from "../api";
import { CampusMap, DEVICE_STATE_LABEL } from "../campus/CampusMap";
import { CAMPUS_FEATURES } from "../campus/features";
import { deriveHighlight, type DeviceState } from "../campus/highlight";
import { MapLists } from "../campus/MapLists";
import { placeDevices } from "../campus/placement";
import { agentActivity, devicesIn, useReplay } from "../lib/replay";
import { AgentStrip } from "./AgentStrip";
import { DiagnosisPanel } from "./DiagnosisPanel";
import { Swatch } from "./MapView";
import { Swimlane } from "./Swimlane";

export { StatusTag } from "./DiagnosisPanel";

const featureName = new Map(CAMPUS_FEATURES.map((f) => [f.id, f.name]));

/** Map key entries, shown only for the states the current incident actually draws. */
const KEY: { state: DeviceState; swatch: Parameters<typeof Swatch>[0]["kind"] }[] = [
  { state: "critical", swatch: "critical" },
  { state: "suspect", swatch: "suspect" },
  { state: "isolated", swatch: "isolated" },
  { state: "warning", swatch: "warning" },
  { state: "ok", swatch: "ok" },
];

/**
 * The Incidents tab (Layout A): the campus map as the hero, the diagnosis panel on the right,
 * and below them the five-agent strip with the replayable message exchange.
 */
export function IncidentView({
  id,
  onChanged,
  layers,
  autoReplay,
}: {
  id: string;
  onChanged: () => void;
  layers: MapLayers | null;
  autoReplay: boolean;
}) {
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [review, setReview] = useState<ReviewItem[]>([]);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messagesOpen, setMessagesOpen] = useState(true);
  const [openRequest, setOpenRequest] = useState<{ kind: "device" | "building"; id: string; seq: number } | null>(null);
  const requestOpen = (kind: "device" | "building", target: string) =>
    setOpenRequest((r) => ({ kind, id: target, seq: (r?.seq ?? 0) + 1 }));

  const load = useCallback(async () => {
    try {
      const [d, t] = await Promise.all([api.incident(id), api.trace(id)]);
      setDetail(d);
      setTrace(t.events);
      setReview(d.report ? await api.review(id) : []);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // The overlay adds the blast radius and user-report areas; without it the map still works.
  useEffect(() => {
    if (!layers) return;
    let current = true;
    api.overlay(id).then((o) => current && setOverlay(o)).catch(() => current && setOverlay(null));
    return () => { current = false; };
  }, [id, layers]);

  const replay = useReplay(trace.length, { auto: autoReplay, resetKey: id });
  const { cursor, playing } = replay;
  const activity = useMemo(() => agentActivity(trace, cursor), [trace, cursor]);
  const row = playing ? trace[cursor] : undefined;
  // One pulse per message that names a switch (decisions, clarifications), only while replaying.
  const pulse = useMemo(() => (row?.kind === "message" ? devicesIn(row.summary) : []), [row]);
  const active = row?.kind === "message" ? [row.sender ?? "", row.recipient ?? ""] : [];

  const report = detail?.report ?? null;
  const placement = useMemo(() => (layers ? placeDevices(layers.devices) : null), [layers]);
  const highlight = useMemo(() => (layers ? deriveHighlight(report, layers, overlay) : null), [layers, report, overlay]);
  const reportedZones = useMemo(() => {
    if (!overlay) return [];
    const corroborated = new Set(overlay.corroborated.map((c) => c.zone));
    const zones = new Set([...overlay.reported_areas.map((a) => a.zone), ...corroborated]);
    return [...zones].map((zone) => ({ zone, corroborated: corroborated.has(zone) }));
  }, [overlay]);

  const deviceInfo = (deviceId: string) => {
    const d = placement?.placed.find((p) => p.id === deviceId);
    const state = highlight?.devices[deviceId] ?? "neutral";
    const evidence = (report?.supporting_evidence ?? []).filter((e) => new RegExp(`\\b${deviceId}\\b`).test(e.interpretation));
    const gaps = (report?.netcoop_extensions?.not_assessable ?? []).filter((n) => n.entity === deviceId);
    return (
      <>
        <h3 className="pop-title mono">{deviceId}</h3>
        <p className="label">{d?.role} switch · simulated</p>
        <dl className="pop-dl">
          <dt>Zone</dt><dd className="mono">{d?.zone}</dd>
          <dt>Drawn at</dt><dd>{d ? featureName.get(d.buildingId) : "not placed"}</dd>
          <dt>State</dt><dd>{DEVICE_STATE_LABEL[state]}</dd>
        </dl>
        {evidence.length > 0 && (
          <div className="pop-block">
            <p className="pop-sub">Evidence in this report</p>
            <ul className="pop-list">
              {evidence.map((e) => (
                <li key={e.metric}><span className="mono">{e.metric}</span> <span className="mono">{e.value}</span></li>
              ))}
            </ul>
          </div>
        )}
        {gaps.length > 0 && (
          <div className="pop-block">
            <p className="pop-sub">Not assessable (never treated as healthy)</p>
            <ul className="pop-list">
              {gaps.map((n) => (
                <li key={n.metric}><span className="mono">{n.metric}</span> <span className="muted">{n.reason.toLowerCase().replace(/_/g, " ")}</span></li>
              ))}
            </ul>
          </div>
        )}
      </>
    );
  };

  if (error) return <div className="error-box">Could not load {id}: {error}</div>;
  if (!detail) return <p className="muted">Loading {id}…</p>;

  const drawn = new Set(Object.values(highlight?.devices ?? {}));
  const key = KEY.filter((k) => drawn.has(k.state));
  const hasPath = (highlight?.links.length ?? 0) > 0;

  return (
    <div className="incident">
      <section className="incident-hero" aria-label="Campus map for this incident">
        <CampusMap
          variant="hero"
          layers={layers}
          highlight={highlight}
          reportedZones={reportedZones}
          pulse={pulse}
          deviceInfo={layers ? deviceInfo : undefined}
          openRequest={openRequest}
        />
        {layers && (
          <div className="hero-aside">
            {(key.length > 0 || hasPath) && (
              <ul className="hero-key" aria-label="Map key">
                {key.map((k) => <li key={k.state}><Swatch kind={k.swatch} />{DEVICE_STATE_LABEL[k.state]}</li>)}
                {hasPath && <li><Swatch kind="path" />Path to the core</li>}
              </ul>
            )}
            <details className="hero-lists">
              <summary>Switches and buildings</summary>
              <MapLists
                devices={placement?.placed ?? []}
                onDevice={(d) => requestOpen("device", d)}
                onBuilding={(b) => requestOpen("building", b)}
              />
            </details>
          </div>
        )}
      </section>

      <DiagnosisPanel id={id} detail={detail} review={review} onChanged={onChanged} onReload={() => void load()} />

      <section className="incident-agents" aria-labelledby="exchange">
        <h2 id="exchange" className="visually-hidden">How the agents reached this</h2>
        <AgentStrip
          activity={activity}
          replay={replay}
          active={active}
          messagesOpen={messagesOpen}
          onToggleMessages={() => setMessagesOpen((o) => !o)}
        />
        <div id="message-panel" className="message-panel" hidden={!messagesOpen}>
          <p className="muted small">
            Solid arrows are requests, dashed arrows are replies, violet is a clarification question, red is a rejected message or agent error.
          </p>
          {/* Mark progress only while a replay is under way; a finished trace shows plainly. */}
          <Swimlane events={trace} cursor={playing || cursor < trace.length - 1 ? cursor : undefined} />
        </div>
      </section>
    </div>
  );
}
