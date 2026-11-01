import { describe, expect, it } from "vitest";
import { IMAGE_BOUNDS, MAP_CROP, toLatLng } from "./coords";
import { CAMPUS_FEATURES } from "./features";
import { placeDevices, ZONE_TO_BUILDING } from "./placement";

const zones = [
  "ZONE_DATA_CENTRE", "ZONE_DATA_CENTRE", "ZONE_DATA_CENTRE", "ZONE_HOSTEL_A", "ZONE_HOSTEL_B",
  "ZONE_ACADEMIC_BLOCK", "ZONE_LIBRARY", "ZONE_LECTURE_HALLS", "ZONE_DEPT_LAB", "ZONE_ADMIN",
];
const roles = ["core", "distribution", "distribution", ...Array(7).fill("access")];
const dev = (i: number, zone = zones[i], role = roles[i]) => ({
  id: `SW_CAMPUS_${i + 1}`, role, zone, position: [0, 0] as [number, number],
  core: i === 0, provenance: "SIMULATED",
});
const fixture = zones.map((_, i) => dev(i));

describe("geometry", () => {
  it("converts coordinates", () => {
    expect(toLatLng(650, 620)).toEqual([620, 650]);
    expect(IMAGE_BOUNDS).toEqual([[75, 48], [1085, 1303]]);
  });
  it("maps zones to known buildings", () => {
    const ids = new Set(CAMPUS_FEATURES.map((f) => f.id));
    expect(CAMPUS_FEATURES).toHaveLength(19);
    for (const b of Object.values(ZONE_TO_BUILDING)) expect(ids.has(b)).toBe(true);
  });
});

describe("placeDevices", () => {
  it("places the campus_v1 fixture", () => {
    const { placed, notPlaced } = placeDevices(fixture);
    expect(placed).toHaveLength(10);
    expect(notPlaced).toEqual([]);
    expect(placed.find((p) => p.id === "SW_CAMPUS_4")!.buildingId).toBe("mhr");
    const dc = placed.filter((p) => p.zone === "ZONE_DATA_CENTRE");
    expect(dc).toHaveLength(3);
    expect(dc.every((p) => p.buildingId === "admin")).toBe(true);
    expect(new Set(dc.map((p) => `${p.x},${p.y}`)).size).toBe(3);
  });
  it("lists unknown zones as not placed", () => {
    const { placed, notPlaced } = placeDevices([...fixture, dev(10, "ZONE_UNKNOWN", "access")]);
    expect(placed).toHaveLength(10);
    expect(notPlaced).toEqual(["SW_CAMPUS_11"]);
  });
  it("keeps every device inside the crop, even when a building is crowded", () => {
    const many = Array.from({ length: 14 }, (_, i) => dev(i + 20, "ZONE_DATA_CENTRE", "access"));
    for (const p of placeDevices([...fixture, ...many]).placed) {
      expect(p.x).toBeGreaterThanOrEqual(MAP_CROP.x);
      expect(p.x).toBeLessThanOrEqual(MAP_CROP.x + MAP_CROP.w);
      expect(p.y).toBeGreaterThanOrEqual(MAP_CROP.y);
      expect(p.y).toBeLessThanOrEqual(MAP_CROP.y + MAP_CROP.h);
    }
  });
});
