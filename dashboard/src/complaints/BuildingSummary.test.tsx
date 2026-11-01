import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CAMPUS_FEATURES } from "../campus/features";
import { BuildingSummary } from "./BuildingSummary";
import type { ComplaintCluster } from "./types";

const mhr = CAMPUS_FEATURES.find((f) => f.id === "mhr")!;

const cluster: ComplaintCluster = {
  buildingId: "mhr",
  count: 2,
  byCategory: { wifi: 1, slow: 1 },
  latest: [
    { id: "S-1", buildingId: "mhr", category: "slow", text: "SAMPLE: pages load slowly (demo)", reportedAt: "2026-10-06T21:30:00Z" },
    { id: "S-2", buildingId: "mhr", category: "wifi", text: "SAMPLE: Wi-Fi drops (demo)", reportedAt: "2026-10-05T18:10:00Z" },
  ],
};

describe("BuildingSummary", () => {
  it("labels the summary as sample data and shows counts and the latest texts", () => {
    render(<BuildingSummary building={mhr} cluster={cluster} />);
    expect(screen.getByText("SAMPLE")).toBeInTheDocument();
    expect(screen.getByText(/Mahanadi/)).toBeInTheDocument();
    expect(screen.getByText(/2 reports/)).toBeInTheDocument();
    expect(screen.getByText("SAMPLE: pages load slowly (demo)")).toBeInTheDocument();
    expect(screen.getByText("SAMPLE: Wi-Fi drops (demo)")).toBeInTheDocument();
  });

  it("uses the singular for a single report", () => {
    render(<BuildingSummary building={mhr} cluster={{ ...cluster, count: 1, byCategory: { wifi: 1 }, latest: [cluster.latest[1]] }} />);
    expect(screen.getByText(/1 report\b/)).toBeInTheDocument();
  });
});
