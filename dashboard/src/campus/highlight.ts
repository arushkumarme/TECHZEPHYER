import type { MapLayers, Overlay, Report } from "../api";
import { shortestPath } from "./paths";

export type DeviceState = "neutral" | "ok" | "critical" | "warning" | "isolated" | "suspect";

export interface Highlight {
  status: string | null;
  devices: Record<string, DeviceState>;
  links: string[];
  focus: string[];
}

export function deriveHighlight(
  report: Report | null,
  layers: MapLayers,
  overlay: Overlay | null,
): Highlight {
  const status = report?.status ?? null;
  const fill = (s: DeviceState) => Object.fromEntries(layers.devices.map((d) => [d.id, s])) as Record<string, DeviceState>;
  const out: Highlight = { status, devices: fill("neutral"), links: [], focus: [] };
  if (!report || status === "failed") return out;

  if (status === "no_fault_detected") {
    out.devices = fill("ok");
  } else if (status === "diagnosed") {
    const critical = report.affected_devices;
    const blast = overlay ? Object.values(overlay.blast_radius)[0] : undefined;
    for (const id of blast?.degraded ?? []) out.devices[id] = "warning";
    for (const id of blast?.isolated ?? []) out.devices[id] = "isolated";
    for (const id of critical) out.devices[id] = "critical";
    const core = layers.devices.find((d) => d.core)?.id;
    const links = new Set<string>();
    if (core) for (const id of critical) for (const l of shortestPath(layers.links, id, core)) links.add(l);
    out.links = [...links];
    out.focus = [...critical];
  } else if (status === "insufficient_evidence") {
    const ids = report.affected_devices.length
      ? report.affected_devices
      : (report.netcoop_extensions?.hypotheses?.[0]?.entities ?? []);
    for (const id of ids) out.devices[id] = "suspect";
    out.focus = [...ids];
  }
  return out;
}
