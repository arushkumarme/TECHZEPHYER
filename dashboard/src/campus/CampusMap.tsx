import {
  CRS,
  divIcon,
  latLngBounds,
  type CircleMarker as LeafletCircleMarker,
  type LatLngExpression,
  type LeafletEvent,
  type Map as LeafletMap,
  type PopupEvent,
} from "leaflet";
import "leaflet/dist/leaflet.css";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CircleMarker, ImageOverlay, MapContainer, Marker, Polyline, Popup, Tooltip, useMap } from "react-leaflet";
import type { MapLayers } from "../api";
import { BuildingSummary } from "../complaints/BuildingSummary";
import type { ComplaintCluster } from "../complaints/types";
import { IMAGE_BOUNDS, toLatLng } from "./coords";
import { CAMPUS_FEATURES, type CampusFeature } from "./features";
import type { DeviceState, Highlight } from "./highlight";
import { LABEL_BELOW, PLACEMENT_NOTE, placeDevices, ZONE_TO_BUILDING, type PlacedDevice } from "./placement";

export const ARTWORK_URL = `${import.meta.env.BASE_URL}campus/iitbbs-campus-map.svg`;
export const NETWORK_OFF_NOTICE =
  "Network layer off. Start the backend with NETCOOP_ENABLE=community_signals,geospatial (doc 13).";

// Leaflet writes path colours as SVG attributes, so the network palette is repeated here as
// values. Keep in step with the --map-* custom properties in styles.css.
const P = {
  node: "#0F1B2E", // deep navy: hollow marker fill
  core: "#38BDF8", // sky: core switch, no finding
  distribution: "#818CF8", // indigo: distribution switch, no finding
  access: "#7DD3FC", // light sky: access switch, no finding
  link: "#38BDF8", // links without a finding
  accent: "#D5B893", // tan: selection and focus (brand)
  ok: "#34D399", // healthy
  warning: "#FBBF24", // degraded
  critical: "#FF6B6B", // fault ring / casing
  criticalFill: "#E11D48", // fault fill and fault-path core
  corroborated: "#D5B893", // tan: user reports confirmed by telemetry
};

const RADIUS: Record<string, number> = { core: 9, distribution: 7, access: 6 };
const ROLE_COLOUR: Record<string, string> = { core: P.core, distribution: P.distribution, access: P.access };

interface MarkerStyle { color: string; fillColor: string; fillOpacity: number; weight: number; dashArray?: string }

/** Solid fill = a telemetry finding; hollow ring = a structural consequence; dashed = unconfirmed.
 *  With no finding, the ring takes the switch's role colour (blue family: never a status hue). */
function deviceStyle(state: DeviceState, role: string): MarkerStyle {
  switch (state) {
    case "neutral":
      return { color: ROLE_COLOUR[role] ?? P.core, fillColor: P.node, fillOpacity: 1, weight: 2 };
    case "ok":
      return { color: P.ok, fillColor: P.ok, fillOpacity: 1, weight: 1.5 };
    case "critical":
      return { color: P.critical, fillColor: P.criticalFill, fillOpacity: 1, weight: 2.5 };
    case "warning":
      return { color: P.warning, fillColor: P.node, fillOpacity: 1, weight: 2 };
    case "isolated":
      return { color: P.critical, fillColor: P.node, fillOpacity: 1, weight: 2 };
    case "suspect":
      return { color: P.warning, fillColor: P.node, fillOpacity: 1, weight: 2, dashArray: "3 3" };
  }
}

/** Status filter groups. "No finding" is not "healthy": missing data is never healthy. */
export type StatusFilter = "healthy" | "degraded" | "faulty" | "nofinding";
export const STATUS_FILTER_OF: Record<DeviceState, StatusFilter> = {
  ok: "healthy",
  warning: "degraded",
  suspect: "degraded",
  critical: "faulty",
  isolated: "faulty",
  neutral: "nofinding",
};
export const STATUS_FILTER_LABEL: Record<StatusFilter, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  faulty: "Faulty",
  nofinding: "No finding / unavailable",
};
const STATUS_FILTERS: StatusFilter[] = ["healthy", "degraded", "faulty", "nofinding"];

export type MapLayerToggle = "switches" | "links" | "flow" | "labels" | "buildings";
export const LAYER_LABEL: Record<MapLayerToggle, string> = {
  switches: "Switches",
  links: "Network links",
  flow: "Link animation",
  labels: "All switch labels",
  buildings: "Buildings",
};
const LAYERS: MapLayerToggle[] = ["switches", "links", "flow", "labels", "buildings"];
export const FLOW_NOTE = "Link animation is illustrative: it shows simulated topology links, not measured traffic.";

/** A link's look: on the fault path, touching a degraded switch, or plain. */
type LinkKind = "fault" | "degraded" | "plain";
const DEGRADED_STATES = new Set<DeviceState>(["warning", "suspect", "isolated"]);
const ORDER: Record<LinkKind, number> = { plain: 0, degraded: 1, fault: 2 };

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

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

function MapToolbar({
  onFitCampus,
  onFocusIncident,
  canFocus,
  layers,
  setLayer,
  filters,
  setFilter,
  counts,
}: {
  onFitCampus: () => void;
  onFocusIncident: () => void;
  canFocus: boolean;
  layers: Record<MapLayerToggle, boolean>;
  setLayer: (k: MapLayerToggle, on: boolean) => void;
  filters: Record<StatusFilter, boolean>;
  setFilter: (k: StatusFilter, on: boolean) => void;
  counts: Record<StatusFilter, number>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="map-toolbar" ref={ref} role="toolbar" aria-label="Map view">
      {open && (
        <div className="map-layers-pop" role="group" aria-label="Map layers and filters">
          <p className="map-layers-h">Show devices</p>
          {STATUS_FILTERS.map((f) => (
            <label key={f} className={`chip-toggle st-${f}`}>
              <input type="checkbox" checked={filters[f]} onChange={(e) => setFilter(f, e.target.checked)} />
              <span className="chip-dot" aria-hidden="true" />
              <span className="chip-label">{STATUS_FILTER_LABEL[f]}</span>
              <span className="chip-n mono">{counts[f]}</span>
            </label>
          ))}
          <p className="map-layers-h">Layers</p>
          {LAYERS.map((k) => (
            <label key={k} className="layer-toggle">
              <input type="checkbox" checked={layers[k]} onChange={(e) => setLayer(k, e.target.checked)} />
              {LAYER_LABEL[k]}
            </label>
          ))}
          <p className="map-layers-note">{FLOW_NOTE}</p>
        </div>
      )}
      <div className="map-tool-row">
        <button type="button" className="map-tool" onClick={onFitCampus} title="Fit the whole campus on screen">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4" /></svg>
          <span>Fit campus</span>
        </button>
        <button type="button" className="map-tool" onClick={onFocusIncident} disabled={!canFocus} title="Fly to the incident's devices">
          <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5" /><circle cx="8" cy="8" r="1.5" /></svg>
          <span>Focus incident</span>
        </button>
        <button type="button" className={open ? "map-tool on" : "map-tool"} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2 14 5 8 8 2 5Z M2 8l6 3 6-3 M2 11l6 3 6-3" /></svg>
          <span>Layers</span>
        </button>
      </div>
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

  // ---- View state: layer toggles, status filters, the selected switch, the Leaflet map.
  const [map, setMap] = useState<LeafletMap | null>(null);
  const [shown, setShown] = useState<Record<MapLayerToggle, boolean>>({
    switches: true,
    links: true,
    flow: true,
    labels: false,
    buildings: true,
  });
  const [filters, setFilters] = useState<Record<StatusFilter, boolean>>({ healthy: true, degraded: true, faulty: true, nofinding: true });
  const [selected, setSelected] = useState<string | null>(null);
  const stateOf = useCallback((id: string): DeviceState => highlight?.devices[id] ?? "neutral", [highlight]);
  const visible = useCallback((id: string) => shown.switches && filters[STATUS_FILTER_OF[stateOf(id)]], [shown.switches, filters, stateOf]);
  const counts = useMemo(() => {
    const c: Record<StatusFilter, number> = { healthy: 0, degraded: 0, faulty: 0, nofinding: 0 };
    for (const d of placed) c[STATUS_FILTER_OF[stateOf(d.id)]] += 1;
    return c;
  }, [placed, stateOf]);
  const neighbours = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const l of links) {
      m.set(l.a, [...(m.get(l.a) ?? []), l.b]);
      m.set(l.b, [...(m.get(l.b) ?? []), l.a]);
    }
    return m;
  }, [links]);
  const linkKind = useCallback(
    (l: { id: string; a: string; b: string }): LinkKind =>
      hlLinks.has(l.id) ? "fault" : DEGRADED_STATES.has(stateOf(l.a)) || DEGRADED_STATES.has(stateOf(l.b)) ? "degraded" : "plain",
    [hlLinks, stateOf],
  );

  // ---- Camera: smooth fly-to, with padding that keeps clear of the hero's key column.
  const fly = useCallback(
    (bounds: Parameters<LeafletMap["flyToBounds"]>[0], maxZoom?: number) => {
      if (!map) return;
      const size = map.getSize();
      if (!size.x || !size.y) return; // not laid out yet (and in tests)
      const right = variant === "hero" ? HERO_ASIDE_CLEARANCE : 40;
      map.flyToBounds(bounds, {
        paddingTopLeft: [56, 40],
        paddingBottomRight: [right, 56],
        maxZoom,
        duration: 0.8,
        animate: !prefersReducedMotion(),
      });
    },
    [map, variant],
  );
  const fitCampus = useCallback(() => {
    map?.closePopup();
    fly(IMAGE_BOUNDS);
  }, [map, fly]);
  // The incident's own devices: findings only, so clicking a switch (blast radius) never re-flies.
  const incidentFocus = useMemo(
    () => placed.filter((d) => ["critical", "suspect"].includes(stateOf(d.id))).map((d) => d.id),
    [placed, stateOf],
  );
  const focusIncident = useCallback(() => {
    // Frame the suspect switches and their whole fault path to the core, with some context.
    const ids = new Set(incidentFocus);
    for (const l of links) if (hlLinks.has(l.id)) ids.add(l.a).add(l.b);
    const pts = [...ids].flatMap((id) => {
      const d = placedById.get(id);
      return d ? [toLatLng(d.x, d.y)] : [];
    });
    if (pts.length) fly(latLngBounds(pts).pad(0.35), 0);
  }, [incidentFocus, links, hlLinks, placedById, fly]);
  const focusKey = incidentFocus.join(",");
  const lastFocus = useRef<string | null>(null);
  useEffect(() => {
    if (!map) return;
    const prev = lastFocus.current;
    lastFocus.current = focusKey;
    if (prev === focusKey) return;
    // A map that opens on an incident flies to it; one that opens without keeps the campus view.
    if (focusKey) focusIncident();
    else if (prev !== null) fly(IMAGE_BOUNDS);
  }, [map, focusKey, focusIncident, fly]);

  useEffect(() => {
    const root = map?.getContainer();
    if (!root) return;
    root.querySelectorAll(".is-sel, .net-link.sel").forEach((el) => el.classList.remove("is-sel", "sel"));
    if (!selected) return;
    root.querySelectorAll(`path.dv-${selected}`).forEach((el) => el.classList.add("is-sel"));
    root.querySelectorAll(`path.net-link.ends-${selected}`).forEach((el) => el.classList.add("sel"));
  });

  const selectDevice = useCallback((id: string) => {
    setSelected(id);
    onDeviceClickRef.current?.(id);
  }, []);
  const openDevice = useCallback(
    (id: string) => {
      const layer = markers.current.get(id);
      if (!layer) return;
      selectDevice(id);
      openWithFocus(layer);
    },
    [selectDevice],
  );
  const linkedSwitches = (id: string) => {
    const n = neighbours.get(id) ?? [];
    if (!n.length) return null;
    return (
      <div className="pop-block pop-links">
        <p className="pop-sub">Linked in the simulated topology</p>
        <div className="pop-chips">
          {n.map((other) => (
            <button key={other} type="button" className={`pop-chip st-${STATUS_FILTER_OF[stateOf(other)]}`} onClick={() => openDevice(other)} disabled={!visible(other)}>
              <span className="chip-dot" aria-hidden="true" />
              <span className="mono">{other}</span>
            </button>
          ))}
        </div>
      </div>
    );
  };

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
        ref={setMap}
      >
        <MapUpkeep />
        <ImageOverlay url={ARTWORK_URL} bounds={IMAGE_BOUNDS} className="campus-artwork" opacity={shown.buildings ? 1 : 0.35} />

        {shown.buildings && CAMPUS_FEATURES.map((f) => (
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

        {drawNetwork && shown.links && links
          .map((l) => ({ ...l, kind: linkKind(l) }))
          .sort((x, y) => ORDER[x.kind] - ORDER[y.kind])
          .map((l) => {
            const kind = l.kind;
            const on = kind === "fault";
            const dim = !(visible(l.a) && visible(l.b));
            const cls = `k-${kind}${dim ? " dim" : ""}`;
            const colour = on ? P.criticalFill : kind === "degraded" ? P.warning : P.link;
            // Keys carry the look: Leaflet sets a path's class only when it is created.
            return (
              <Fragment key={`${l.id}:${cls}`}>
                {/* A fault path is a deep red core inside a bright, pulsing casing. */}
                {on && (
                  <Polyline
                    positions={l.points}
                    interactive={false}
                    pathOptions={{ color: P.critical, weight: 8, opacity: 0.85, lineCap: "round" }}
                    className={`net-link-casing ${cls}`}
                  />
                )}
                <Polyline
                  positions={l.points}
                  pathOptions={{
                    color: colour,
                    weight: on ? 3.5 : kind === "degraded" ? 2.5 : 1.75,
                    opacity: on ? 1 : kind === "degraded" ? 0.95 : 0.55,
                    lineCap: "round",
                  }}
                  className={`net-link ${cls} ends-${l.a} ends-${l.b}`}
                >
                  <Tooltip sticky className="map-tip">{l.a} ⇄ {l.b}</Tooltip>
                  <Popup className="map-popup" maxWidth={300} minWidth={220} {...popPan}>
                    <div className="map-pop">
                      <h3 className="pop-title">
                        <span className="mono">{l.a}</span> ⇄ <span className="mono">{l.b}</span>
                      </h3>
                      <p className="label">
                        {on ? "On the fault path to the core" : kind === "degraded" ? "Touches a degraded switch" : "Simulated topology link"}
                      </p>
                      <div className="pop-chips">
                        {[l.a, l.b].map((id) => (
                          <button key={id} type="button" className={`pop-chip st-${STATUS_FILTER_OF[stateOf(id)]}`} onClick={() => openDevice(id)} disabled={!visible(id)}>
                            <span className="chip-dot" aria-hidden="true" />
                            <span className="mono">{id}</span>
                            <span className="muted">{DEVICE_STATE_LABEL[stateOf(id)]}</span>
                          </button>
                        ))}
                      </div>
                      <p className="small muted">Team-authored simulated link, not a real cable.</p>
                    </div>
                  </Popup>
                </Polyline>
                {/* Illustrative flow: dashes travelling along the link (CSS), never measured traffic. */}
                {shown.flow && !dim && (
                  <Polyline
                    positions={l.points}
                    interactive={false}
                    pathOptions={{
                      color: on ? "#FFE4E6" : kind === "degraded" ? "#FDE68A" : "#BAE6FD",
                      weight: on ? 2.5 : 2,
                      opacity: on ? 0.95 : kind === "degraded" ? 0.85 : 0.6,
                      dashArray: on ? "2 12" : kind === "degraded" ? "6 10" : "1.5 16",
                      lineCap: "round",
                    }}
                    className={`net-flow k-${kind}`}
                  />
                )}
              </Fragment>
            );
          })}

        {drawNetwork && selected && visible(selected) && placedById.has(selected) && (
          <CircleMarker
            key={`sel-${selected}`}
            center={at(placedById.get(selected)!)}
            radius={(RADIUS[placedById.get(selected)!.role] ?? 6) + 7}
            interactive={false}
            pathOptions={{ color: P.accent, weight: 2, fill: false, dashArray: "4 5", opacity: 1 }}
            className="sel-ring"
          />
        )}

        {drawNetwork && placed.filter((d) => visible(d.id)).map((d) => {
          const state = stateOf(d.id);
          const s = deviceStyle(state, d.role);
          const building = featureById.get(d.buildingId)!;
          const labelled = focus.has(d.id) || shown.labels;
          const cls = `device st-${state} role-${d.role} dv-${d.id}`;
          return (
            <CircleMarker
              key={`${d.id}:${cls}`}
              ref={(m) => {
                if (m) markers.current.set(d.id, m);
                else markers.current.delete(d.id);
              }}
              center={at(d)}
              radius={RADIUS[d.role] ?? (d.core ? 9 : 6)}
              className={cls}
              pathOptions={{ ...s, dashArray: s.dashArray ?? "", opacity: 1 }}
              eventHandlers={{
                add: focusable(`${d.id}, ${d.role} switch at ${building.name}`),
                click: () => selectDevice(d.id),
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
              <Popup className="map-popup" maxWidth={300} minWidth={220} {...popPan}>
                <div className="map-pop">
                  {deviceInfo ? (
                    deviceInfo(d.id)
                  ) : (
                    <>
                      <h3 className="pop-title mono">{d.id}</h3>
                      <p className="label">{d.role} switch · {building.name}</p>
                      <p className="small">{DEVICE_STATE_LABEL[state]}</p>
                    </>
                  )}
                  {linkedSwitches(d.id)}
                </div>
              </Popup>
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

      {drawNetwork && (
        <MapToolbar
          onFitCampus={fitCampus}
          onFocusIncident={focusIncident}
          canFocus={incidentFocus.length > 0}
          layers={shown}
          setLayer={(k, on) => setShown((v) => ({ ...v, [k]: on }))}
          filters={filters}
          setFilter={(k, on) => setFilters((f) => ({ ...f, [k]: on }))}
          counts={counts}
        />
      )}
      {!drawNetwork && <p className="map-notice" role="status">{NETWORK_OFF_NOTICE}</p>}
      {drawNetwork && placed.length > 0 && <p className="placement-note">{PLACEMENT_NOTE}</p>}
    </div>
  );
}
