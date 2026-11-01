import { describe, expect, it } from "vitest";
import { CAMPUS_FEATURES } from "../campus/features";
import { clusterByBuilding } from "./source";
import { sampleComplaintSource } from "./sample";
import type { ComplaintMarker } from "./types";

const m = (id: string, buildingId: string, category: ComplaintMarker["category"], reportedAt: string): ComplaintMarker => ({
  id, buildingId, category, text: `SAMPLE ${id} (demo)`, reportedAt,
});

describe("sampleComplaintSource", () => {
  it("is labelled sample data", async () => {
    expect(sampleComplaintSource.isSample).toBe(true);
    expect(sampleComplaintSource.label).toBe("Sample reports (demo data)");
    const list = await sampleComplaintSource.list();
    expect(list).toHaveLength(15);
    const ids = new Set(CAMPUS_FEATURES.map((f) => f.id));
    for (const x of list) {
      expect(x.id.startsWith("SAMPLE-")).toBe(true);
      expect(ids.has(x.buildingId)).toBe(true);
      expect(x.text).toContain("SAMPLE");
    }
    expect(new Set(list.map((x) => x.buildingId)).size).toBe(5);
  });
});

describe("clusterByBuilding", () => {
  it("groups, counts and sorts", () => {
    const out = clusterByBuilding([
      m("a", "lhc", "other", "2026-01-01T00:00:00Z"),
      m("b", "mhr", "wifi", "2026-01-02T00:00:00Z"),
      m("c", "mhr", "slow", "2026-01-03T00:00:00Z"),
    ]);
    expect(out.map((c) => c.buildingId)).toEqual(["mhr", "lhc"]);
    expect(out[0].count).toBe(2);
    expect(out[0].byCategory).toEqual({ wifi: 1, slow: 1 });
    expect(out[0].latest.map((x) => x.id)).toEqual(["c", "b"]);
  });
  it("keeps only the 3 newest, ties by building id", () => {
    const many = ["1", "2", "3", "4"].map((d) => m(d, "sbs", "wifi", `2026-01-0${d}T00:00:00Z`));
    const out = clusterByBuilding([...many, m("x", "bhr", "wifi", "2026-01-01T00:00:00Z")]);
    expect(out[0].latest.map((x) => x.id)).toEqual(["4", "3", "2"]);
    expect(clusterByBuilding([m("p", "sac", "wifi", "2026-01-01T00:00:00Z"), m("q", "bhr", "wifi", "2026-01-01T00:00:00Z")]).map((c) => c.buildingId)).toEqual(["bhr", "sac"]);
  });
});
