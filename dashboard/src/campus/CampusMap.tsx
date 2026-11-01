import { CRS, divIcon, type CircleMarker as LeafletCircleMarker, type LatLngExpression, type LeafletEvent, type PopupEvent } from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { CircleMarker, ImageOverlay, MapContainer, Marker, Polyline, Popup, Tooltip, useMap } from "react-leaflet";
import type { MapLayers } from "../api";
import { BuildingSummary } from "../complaints/BuildingSummary";
import type { ComplaintCluster } from "../complaints/types";
import { IMAGE_BOUNDS, toLatLng } from "./coords";
import { CAMPUS_FEATURES, type CampusFeature } from "./features";
import type { DeviceState, Highlight } from "./highlight";
import { LABEL_BELOW, PLACEMENT_NOTE, placeDevices, ZONE_TO_BUILDING, type PlacedDevice } from "./placement";

export const ARTWORK_URL = "/campus/iitbbs-campus-map.svg";
export const NETWORK_OFF_NOTICE =
  "Network layer off. Start the backend with NETCOOP_ENABLE=community_signals,geospatial (doc 13).";

// Leaflet writes path colours as SVG attributes, so the palette is repeated here as values.
// Keep in step with the custom properties in styles.css. Unhighlighted links use muted at
// reduced opacity: --line (#1d2630) is invisible on the artwork's dark field.
const P = {
  bg: "#0a0e13",
  text: "#e6edf3",
  muted: "#8592a0",
  accent: "#5b9bff",
  ok: "#46b98a",
  warning: "#e0a43c",
  critical: "#e5605a",
  corroborated: "#a48bf0",
};

const RADIUS: Record<string, number> = { core: 9, distribution: 7, access: 6 };

/** Solid fill = a telemetry finding; hollow ring = a structural consequence; dashed = unconfirmed. */
const DEVICE_STYLE: Record<DeviceState, { color: string; fillColor: string; fillOpacity: number; weight: number; dashArray?: string }> = {
  neutral: { color: P.text, fillColor: P.bg, fillOpacity: 1, weight: 1.5 },
  ok: { color: P.ok, fillColor: P.ok, fillOpacity: 1, weight: 1.5 },
  critical: { color: P.critical, fillColor: P.critical, fillOpacity: 1, weight: 2 },
  warning: { color: P.warning, fillColor: P.bg, fillOpacity: 1, weight: 2 },
  isolated: { color: P.critical, fillColor: P.bg, fillOpacity: 1, weight: 2 },
  suspect: { color: P.warning, fillColor: P.bg, fillOpacity: 1, weight: 2, dashArray: "3 3" },
};

export const DEVICE_STATE_LABEL: Record<DeviceState, string> = {
  neutral: "No finding",
  ok: "Healthy (no fault found)",
  critical: "Detected fault (telemetry)",
  warning: "Would lose redundancy",
  isolated: "Would be isolated",
  suspect: "Suspected, needs more evidence",
};

export interface CampusMapProps {
  layers: MapLayers | null;
  highlight: Highlight | null;
  reportedZones?: { zone: string; corroborated: boolean }[];
  complaints?: ComplaintCluster[] | null;
  /** The complaint layer is illustrative demo data: every badge and popover says SAMPLE. */
  complaintsAreSample?: boolean;
  pulse?: string[];
  deviceInfo?: (id: string) => ReactNode;
  onDeviceClick?: (id: string) => void;
  variant: "hero" | "full";
  /** Open a switch's or building's popover from outside the map (the legend lists). */
  openRequest?: { kind: "device" | "building"; id: string; seq: number } | null;
}

// Sample badges sit on a side that holds neither the building label nor a switch: below when
// the label is above (switches go sideways there), beside the building when the label is below
// (switches go up there). BHR's badge goes right because MHR sits to its left.
const BADGE_W = 76;
const BADGE_H = 20;
const BADGE_GAP = 26;
type BadgeSide = "below" | "left" | "right";
const BADGE_ANCHOR: Record<BadgeSide, [number, number]> = {
  below: [BADGE_W / 2, -14],
  left: [BADGE_W + BADGE_GAP, BADGE_H / 2],
  right: [-BADGE_GAP, BADGE_H / 2],
};
function badgeSide(buildingId: string): BadgeSide {
  if (!LABEL_BELOW.has(buildingId)) return "below";
  return buildingId === "bhr" ? "right" : "left";
}

// Generous pan limits: room for a popover to auto-pan into view, but the artwork can't be lost.
const PAN_PAD = 600;
const PAN_BOUNDS: [[number, number], [number, number]] = [
  [IMAGE_BOUNDS[0][0] - PAN_PAD, IMAGE_BOUNDS[0][1] - PAN_PAD],
  [IMAGE_BOUNDS[1][0] + PAN_PAD, IMAGE_BOUNDS[1][1] + PAN_PAD],
];

// The hero's key column is 240 px wide, 12 px in from the right edge (styles.css .hero-aside).
const HERO_ASIDE_CLEARANCE = 240 + 12 + 16;
const HERO_POPUP_PAN = {
  autoPanPaddingTopLeft: [16, 16] as [number, number],
  autoPanPaddingBottomRight: [HERO_ASIDE_CLEARANCE, 16] as [number, number],
};

const featureById = new Map(CAMPUS_FEATURES.map((f) => [f.id, f]));
const at = (p: { x: number; y: number }) => toLatLng(p.x, p.y) as LatLngExpression;

/** A gently curved link: quadratic Bezier bowing to the left of a→b, sampled in SVG space. */
function curve(a: { x: number; y: number }, b: { x: number; y: number }): LatLngExpression[] {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const bow = 0.12;
  const cx = mx - dy * bow;
  const cy = my + dx * bow;
  const pts: LatLngExpression[] = [];
  const n = 16;
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    pts.push(toLatLng(u * u * a.x + 2 * u * t * cx + t * t * b.x, u * u * a.y + 2 * u * t * cy + t * t * b.y));
  }
  return pts;
}

/**
 * Keep Leaflet's idea of the container size in step with CSS layout changes, and re-measure
 * popups once React has rendered their content (Leaflet sizes and pans before that).
 */
function MapUpkeep() {
  const map = useMap();
  useEffect(() => {
    const onOpen = (e: PopupEvent) => {
      requestAnimationFrame(() => {
        if (!e.popup.isOpen()) return;
        // Leaflet skips a pan while it thinks its own first (too small) pan is running.
        (e.popup as unknown as { _autopanning: boolean })._autopanning = false;
        e.popup.update();
        // Opened from the keyboard (Enter on a marker, or a legend list): move focus inside.
        // One more frame: React fills the popup's portal after Leaflet opens it.
        if (FOCUS_ON_OPEN.delete(e.popup)) {
          requestAnimationFrame(() => {
            const root = e.popup.getElement();
            const target =
              root?.querySelector<HTMLElement>(".pop-title") ?? root?.querySelector<HTMLElement>(".leaflet-popup-close-button");
            if (target) {
              if (!target.hasAttribute("tabindex") && target.tagName !== "A") target.setAttribute("tabindex", "-1");
              target.focus();
            }
          });
        }
      });
    };
    map.on("popupopen", onOpen);
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => map.invalidateSize());
      ro.observe(map.getContainer());
    }
    return () => {
      map.off("popupopen", onOpen);
      ro?.disconnect();
    };
  }, [map]);
  return null;
}

const FOCUS_ON_OPEN = new WeakSet<object>();

/** Open a layer's popup and, once it has rendered, move keyboard focus into it. */
function openWithFocus(layer: LeafletCircleMarker) {
  const popup = layer.getPopup();
  if (popup) FOCUS_ON_OPEN.add(popup);
  layer.openPopup();
}

/** Make an SVG path reachable and operable from the keyboard (Leaflet only does this for icons). */
function focusable(label: string) {
  return (e: LeafletEvent) => {
    const layer = e.target as LeafletCircleMarker;
    const el = layer.getElement();
    if (!el) return;
    el.setAttribute("tabindex", "0");
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", label);
    el.addEventListener("keydown", (ev) => {
      const k = (ev as KeyboardEvent).key;
      if (k === "Enter" || k === " ") {
        ev.preventDefault();
        layer.fire("click");
        openWithFocus(layer);
      }
    });
  };
}

function BuildingPopover({
  building,
  devices,
  cluster,
  isSample,
}: {
  building: CampusFeature;
  devices: PlacedDevice[];
  cluster?: ComplaintCluster;
  isSample: boolean;
}) {
  return (
    <div className="map-pop">
      <h3 className="pop-title">{building.name}</h3>
      <p className="label">{building.category.replace(/-/g, " ")}</p>
      {devices.length > 0 && (
        <div className="pop-block">
          <p className="pop-sub">Simulated switches placed here</p>
          <ul className="pop-list">
            {devices.map((d) => (
              <li key={d.id}><span className="mono">{d.id}</span> <span className="muted">{d.role}</span></li>
            ))}
          </ul>
        </div>
      )}
      {cluster && <BuildingSummary building={building} cluster={cluster} isSample={isSample} />}
    </div>
  );
}

export function CampusMap({
  layers,
  highlight,
  reportedZones,
  complaints,
  complaintsAreSample = true,
  pulse,
  deviceInfo,
  onDeviceClick,
  variant,
  openRequest,
}: CampusMapProps) {
  // In the hero, the map key and lists sit over the top-right corner, above Leaflet's panes:
  // keep every popover clear of that column so none opens underneath it.
  const popPan = variant === "hero" ? HERO_POPUP_PAN : undefined;
  const { placed } = useMemo(() => (layers ? placeDevices(layers.devices) : { placed: [] as PlacedDevice[] }), [layers]);
  const placedById = useMemo(() => new Map(placed.map((d) => [d.id, d])), [placed]);
  const byBuilding = useMemo(() => {
    const m = new Map<string, PlacedDevice[]>();
    for (const d of placed) m.set(d.buildingId, [...(m.get(d.buildingId) ?? []), d]);
    return m;
  }, [placed]);
  const clusters = useMemo(() => new Map((complaints ?? []).map((c) => [c.buildingId, c])), [complaints]);
  const hlLinks = useMemo(() => new Set(highlight?.links ?? []), [highlight]);
  const focus = useMemo(() => new Set(highlight?.focus ?? []), [highlight]);

  const links = useMemo(() => {
    if (!layers) return [];
    return layers.links.flatMap((l) => {
      const a = placedById.get(l.a);
      const b = placedById.get(l.b);
      return a && b ? [{ id: l.id, a: l.a, b: l.b, points: curve(a, b) }] : [];
    });
  }, [layers, placedById]);

  const rings = useMemo(() => {
    const out = new Map<string, boolean>();
    for (const r of reportedZones ?? []) {
      const b = ZONE_TO_BUILDING[r.zone];
      if (b && featureById.has(b)) out.set(b, (out.get(b) ?? false) || r.corroborated);
    }
    return [...out];
  }, [reportedZones]);

  // One 600 ms ring per pulsed id: restart the CSS animation on the marker's own path.
  const markers = useRef(new Map<string, LeafletCircleMarker>());
  const buildings = useRef(new Map<string, LeafletCircleMarker>());
  const onDeviceClickRef = useRef(onDeviceClick);
  onDeviceClickRef.current = onDeviceClick;

  // A list item does what activating the marker does: select it, then open its popover.
  useEffect(() => {
    if (!openRequest) return;
    const layer = (openRequest.kind === "device" ? markers : buildings).current.get(openRequest.id);
    if (!layer) return;
    if (openRequest.kind === "device") onDeviceClickRef.current?.(openRequest.id);
    openWithFocus(layer);
  }, [openRequest]);
  useEffect(() => {
    if (!pulse?.length) return;
    const timers: number[] = [];
    for (const id of pulse) {
      const el = markers.current.get(id)?.getElement();
      if (!el) continue;
      el.classList.remove("pulse");
      void el.getBoundingClientRect();
      el.classList.add("pulse");
      timers.push(window.setTimeout(() => el.classList.remove("pulse"), 600));
    }
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [pulse]);

  const drawNetwork = layers !== null;

  return (
    <div className={`campus-map ${variant}`}>
      <MapContainer
        className="campus-leaflet"
        crs={CRS.Simple}
        bounds={IMAGE_BOUNDS}
        maxBounds={PAN_BOUNDS}
        minZoom={-2}
        maxZoom={1.5}
        zoomSnap={0.25}
        zoomDelta={0.5}
        scrollWheelZoom={variant === "full"}
        attributionControl={false}
      >
        <MapUpkeep />
        <ImageOverlay url={ARTWORK_URL} bounds={IMAGE_BOUNDS} className="campus-artwork" />

        {CAMPUS_FEATURES.map((f) => (
          <CircleMarker
            key={f.id}
            ref={(m) => {
              if (m) buildings.current.set(f.id, m);
              else buildings.current.delete(f.id);
            }}
            center={at(f)}
            radius={15}
            className="building-hit"
            pathOptions={{ color: P.accent, opacity: 0, weight: 1.5, fillColor: P.accent, fillOpacity: 0 }}
            eventHandlers={{ add: focusable(f.name) }}
          >
            <Popup className="map-popup" maxWidth={300} minWidth={220} {...popPan}>
              <BuildingPopover building={f} devices={byBuilding.get(f.id) ?? []} cluster={clusters.get(f.id)} isSample={complaintsAreSample} />
            </Popup>
          </CircleMarker>
        ))}

        {rings.map(([b, corroborated]) => (
          <CircleMarker
            key={`ring-${b}-${corroborated}`}
            center={at(featureById.get(b)!)}
            radius={24}
            interactive={false}
            pathOptions={{
              color: corroborated ? P.corroborated : P.warning,
              weight: 2,
              dashArray: corroborated ? undefined : "6 4",
              fillColor: corroborated ? P.corroborated : P.warning,
              fillOpacity: 0.08,
            }}
          />
        ))}

        {drawNetwork && [...links].sort((x, y) => Number(hlLinks.has(x.id)) - Number(hlLinks.has(y.id))).map((l) => {
          const on = hlLinks.has(l.id);
          return (
            <Polyline
              key={l.id}
              positions={l.points}
              pathOptions={{ color: on ? P.critical : P.muted, weight: on ? 3 : 1.5, opacity: on ? 1 : 0.55, lineCap: "round" }}
              className={on ? "net-link hl" : "net-link"}
            >
              <Tooltip sticky className="map-tip">{l.a} – {l.b}</Tooltip>
            </Polyline>
          );
        })}

        {drawNetwork && placed.map((d) => {
          const state = highlight?.devices[d.id] ?? "neutral";
          const s = DEVICE_STYLE[state];
          const building = featureById.get(d.buildingId)!;
          const labelled = focus.has(d.id);
          return (
            <CircleMarker
              key={d.id}
              ref={(m) => {
                if (m) markers.current.set(d.id, m);
                else markers.current.delete(d.id);
              }}
              center={at(d)}
              radius={RADIUS[d.role] ?? (d.core ? 9 : 6)}
              className="device"
              pathOptions={{ ...s, dashArray: s.dashArray ?? "", opacity: 1 }}
              eventHandlers={{
                add: focusable(`${d.id}, ${d.role} switch at ${building.name}`),
                click: () => onDeviceClick?.(d.id),
              }}
            >
              <Tooltip
                key={labelled ? "on" : "off"}
                permanent={labelled}
                direction={LABEL_BELOW.has(d.buildingId) ? "top" : "bottom"}
                offset={[0, LABEL_BELOW.has(d.buildingId) ? -8 : 8]}
                className={labelled ? "map-tip device-label" : "map-tip"}
              >
                {d.id}{labelled ? "" : ` · ${d.role}`}
              </Tooltip>
              {deviceInfo && (
                <Popup className="map-popup" maxWidth={300} minWidth={220} {...popPan}>
                  <div className="map-pop">{deviceInfo(d.id)}</div>
                </Popup>
              )}
            </CircleMarker>
          );
        })}

        {[...clusters.values()].flatMap((c) => {
          const f = featureById.get(c.buildingId);
          if (!f) return [];
          const side = badgeSide(f.id);
          const tag = complaintsAreSample ? `<span class="cbadge-tag">SAMPLE</span>` : "";
          const icon = divIcon({
            className: "cbadge-icon",
            html: `<span class="cbadge">${tag}<span class="cbadge-n">${c.count}</span></span>`,
            iconSize: [BADGE_W, BADGE_H],
            iconAnchor: BADGE_ANCHOR[side],
          });
          return [
            <Marker key={`c-${c.buildingId}`} position={at(f)} icon={icon} title={`${complaintsAreSample ? "SAMPLE reports" : "Reports"} at ${f.name}: ${c.count}`} alt="">
              <Popup className="map-popup" maxWidth={300} minWidth={220} {...popPan}>
                <BuildingPopover building={f} devices={byBuilding.get(f.id) ?? []} cluster={c} isSample={complaintsAreSample} />
              </Popup>
            </Marker>,
          ];
        })}
      </MapContainer>

      {!drawNetwork && <p className="map-notice" role="status">{NETWORK_OFF_NOTICE}</p>}
      {drawNetwork && placed.length > 0 && <p className="placement-note">{PLACEMENT_NOTE}</p>}
    </div>
  );
}
