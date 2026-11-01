import { describe, expect, it } from "vitest";
import type { MapLayers, Overlay, Report } from "../api";
import { deriveHighlight } from "./highlight";
import { shortestPath } from "./paths";

const links = [
  ["L-1-2", 1, 2], ["L-1-3", 1, 3], ["L-2-3", 2, 3], ["L-2-4", 2, 4], ["L-2-5", 2, 5],
  ["L-2-10", 2, 10], ["L-3-6", 3, 6], ["L-3-7", 3, 7], ["L-3-9", 3, 9], ["L-2-8", 2, 8], ["L-3-8", 3, 8],
].map(([id, a, b]) => ({ id: id as string, a: `SW_CAMPUS_${a}`, b: `SW_CAMPUS_${b}` }));

const pt: [number, number] = [0, 0];
const layers = {
  crs: "x", bounds: [], banner: "", provenance_note: "", zones: [],
  devices: Array.from({ length: 10 }, (_, i) => ({
    id: `SW_CAMPUS_${i + 1}`, role: "access", zone: "Z", position: pt, core: i === 0, provenance: "p",
  })),
  links: links.map((l) => ({ ...l, from: pt, to: pt, provenance: "p" })),
} as unknown as MapLayers;

const report = (p: Partial<Report>): Report =>
  ({ incident_id: "i", status: "diagnosed", affected_devices: [], ...p }) as unknown as Report;
const overlay = (degraded: string[], isolated: string[]): Overlay =>
  ({ blast_radius: { X: { degraded, isolated } } }) as unknown as Overlay;
const states = (h: { devices: Record<string, string> }, s: string) =>
  Object.values(h.devices).every((v) => v === s);

describe("shortestPath", () => {
  it("finds the path", () => expect(shortestPath(links, "SW_CAMPUS_4", "SW_CAMPUS_1")).toEqual(["L-2-4", "L-1-2"]));
  it("core to core is empty", () => expect(shortestPath(links, "SW_CAMPUS_1", "SW_CAMPUS_1")).toEqual([]));
  it("unreachable is empty", () => expect(shortestPath(links, "SW_CAMPUS_4", "SW_X")).toEqual([]));
});

describe("deriveHighlight", () => {
  it("diagnosed S-02", () => {
    const h = deriveHighlight(report({ affected_devices: ["SW_CAMPUS_4"] }), layers, overlay(["SW_CAMPUS_5"], []));
    expect(h.devices.SW_CAMPUS_4).toBe("critical");
    expect(h.devices.SW_CAMPUS_5).toBe("warning");
    expect(h.devices.SW_CAMPUS_2).toBe("neutral");
    expect(h.links).toEqual(["L-2-4", "L-1-2"]);
    expect(h.focus).toEqual(["SW_CAMPUS_4"]);
    expect(h.status).toBe("diagnosed");
  });
  it("blast radius never overrides critical; isolated marked", () => {
    const h = deriveHighlight(
      report({ affected_devices: ["SW_CAMPUS_4"] }), layers, overlay(["SW_CAMPUS_4"], ["SW_CAMPUS_5"]));
    expect(h.devices.SW_CAMPUS_4).toBe("critical");
    expect(h.devices.SW_CAMPUS_5).toBe("isolated");
  });
  it("core affected: no path, no throw", () => {
    const h = deriveHighlight(report({ affected_devices: ["SW_CAMPUS_1"] }), layers, null);
    expect(h.devices.SW_CAMPUS_1).toBe("critical");
    expect(h.links).toEqual([]);
  });
  it("insufficient evidence uses hypotheses when no affected", () => {
    const r = report({
      status: "insufficient_evidence",
      netcoop_extensions: { hypotheses: [{ cause_type: "c", entities: ["SW_CAMPUS_7"], score: 0.2 }] },
    } as unknown as Partial<Report>);
    const h = deriveHighlight(r, layers, null);
    expect(h.devices.SW_CAMPUS_7).toBe("suspect");
    expect(h.links).toEqual([]);
    expect(h.focus).toEqual(["SW_CAMPUS_7"]);
  });
  it("insufficient evidence with nothing is neutral", () => {
    expect(states(deriveHighlight(report({ status: "insufficient_evidence" }), layers, null), "neutral")).toBe(true);
  });
  it("no_fault_detected is all ok", () => {
    expect(states(deriveHighlight(report({ status: "no_fault_detected" }), layers, null), "ok")).toBe(true);
  });
  it("null and failed are neutral", () => {
    const n = deriveHighlight(null, layers, null);
    expect(n.status).toBeNull();
    expect(states(n, "neutral")).toBe(true);
    const f = deriveHighlight(report({ status: "failed", affected_devices: ["SW_CAMPUS_4"] }), layers, null);
    expect(states(f, "neutral")).toBe(true);
    expect(f.links).toEqual([]);
  });
});
