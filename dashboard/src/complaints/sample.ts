import type { ComplaintMarker, ComplaintSource } from "./types";

// ILLUSTRATIVE DEMO DATA ONLY. These are not real reports and not real people.
const SAMPLE_MARKERS: ComplaintMarker[] = [
  { id: "SAMPLE-001", buildingId: "mhr", category: "wifi", text: "SAMPLE: Wi-Fi drops in the evening (demo)", reportedAt: "2026-10-05T18:10:00Z" },
  { id: "SAMPLE-002", buildingId: "mhr", category: "slow", text: "SAMPLE: pages load slowly at night (demo)", reportedAt: "2026-10-06T21:30:00Z" },
  { id: "SAMPLE-003", buildingId: "mhr", category: "disconnect", text: "SAMPLE: connection resets repeatedly (demo)", reportedAt: "2026-10-07T20:05:00Z" },
  { id: "SAMPLE-004", buildingId: "mhr", category: "wifi", text: "SAMPLE: weak signal in the corridor (demo)", reportedAt: "2026-10-08T19:45:00Z" },
  { id: "SAMPLE-005", buildingId: "bhr", category: "wifi", text: "SAMPLE: no signal on upper floor (demo)", reportedAt: "2026-10-05T19:00:00Z" },
  { id: "SAMPLE-006", buildingId: "bhr", category: "slow", text: "SAMPLE: downloads very slow (demo)", reportedAt: "2026-10-07T22:15:00Z" },
  { id: "SAMPLE-007", buildingId: "bhr", category: "other", text: "SAMPLE: captive login page loops (demo)", reportedAt: "2026-10-09T08:40:00Z" },
  { id: "SAMPLE-008", buildingId: "lhc", category: "disconnect", text: "SAMPLE: drops during lecture hours (demo)", reportedAt: "2026-10-06T10:20:00Z" },
  { id: "SAMPLE-009", buildingId: "lhc", category: "wifi", text: "SAMPLE: signal weak in the back rows (demo)", reportedAt: "2026-10-08T11:00:00Z" },
  { id: "SAMPLE-010", buildingId: "lhc", category: "slow", text: "SAMPLE: slow video streaming (demo)", reportedAt: "2026-10-09T12:30:00Z" },
  { id: "SAMPLE-011", buildingId: "sbs", category: "slow", text: "SAMPLE: slow file uploads (demo)", reportedAt: "2026-10-07T14:10:00Z" },
  { id: "SAMPLE-012", buildingId: "sbs", category: "other", text: "SAMPLE: cannot reach a department page (demo)", reportedAt: "2026-10-08T15:25:00Z" },
  { id: "SAMPLE-013", buildingId: "sac", category: "wifi", text: "SAMPLE: Wi-Fi unreachable near the courts (demo)", reportedAt: "2026-10-06T17:50:00Z" },
  { id: "SAMPLE-014", buildingId: "sac", category: "disconnect", text: "SAMPLE: random disconnects (demo)", reportedAt: "2026-10-09T16:35:00Z" },
  { id: "SAMPLE-015", buildingId: "sac", category: "slow", text: "SAMPLE: slow in the evening (demo)", reportedAt: "2026-10-10T18:20:00Z" },
];

export const sampleComplaintSource: ComplaintSource = {
  label: "Sample reports (demo data)",
  isSample: true,
  list: () => Promise.resolve(SAMPLE_MARKERS.map((m) => ({ ...m }))),
};
