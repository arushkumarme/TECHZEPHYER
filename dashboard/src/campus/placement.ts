import type { MapLayers } from "../api";
import { CAMPUS_FEATURES } from "./features";

export const PLACEMENT_NOTE = "Simulated network, illustrative placement, not real switch locations.";

export const ZONE_TO_BUILDING: Record<string, string> = {
  ZONE_DATA_CENTRE: "admin",
  ZONE_HOSTEL_A: "mhr",
  ZONE_HOSTEL_B: "bhr",
  ZONE_ADMIN: "sac",
  ZONE_LECTURE_HALLS: "lhc",
  ZONE_ACADEMIC_BLOCK: "sbs",
  ZONE_LIBRARY: "secs",
  ZONE_DEPT_LAB: "sif",
};

export interface PlacedDevice {
  id: string;
  role: string;
  zone: string;
  core: boolean;
  buildingId: string;
  x: number;
  y: number;
}

// Fan-out angles (degrees, SVG space, 0 = right, -90 = up). The upper arc comes first so
// markers stay clear of the building label, which sits below its anchor point.
const ANGLES = [-90, -30, -150, 30, 150, 90];
const RING_BASE = 34;
const RING_STEP = 24;

export function placeDevices(devices: MapLayers["devices"]): {
  placed: PlacedDevice[];
  notPlaced: string[];
} {
  const byBuilding = new Map<string, MapLayers["devices"]>();
  const notPlaced: string[] = [];
  for (const d of [...devices].sort((a, b) => a.id.localeCompare(b.id))) {
    const b = ZONE_TO_BUILDING[d.zone];
    const feature = b ? CAMPUS_FEATURES.find((f) => f.id === b) : undefined;
    if (!feature) {
      notPlaced.push(d.id);
      continue;
    }
    byBuilding.set(b, [...(byBuilding.get(b) ?? []), d]);
  }
  const placed: PlacedDevice[] = [];
  for (const [buildingId, list] of byBuilding) {
    const f = CAMPUS_FEATURES.find((c) => c.id === buildingId)!;
    list.forEach((d, i) => {
      const ring = Math.floor(i / ANGLES.length);
      const a = (ANGLES[i % ANGLES.length] * Math.PI) / 180;
      const r = RING_BASE + RING_STEP * ring;
      placed.push({
        id: d.id,
        role: d.role,
        zone: d.zone,
        core: d.core,
        buildingId,
        x: Math.round((f.x + r * Math.cos(a)) * 10) / 10,
        y: Math.round((f.y + r * Math.sin(a)) * 10) / 10,
      });
    });
  }
  placed.sort((a, b) => a.id.localeCompare(b.id));
  return { placed, notPlaced };
}
