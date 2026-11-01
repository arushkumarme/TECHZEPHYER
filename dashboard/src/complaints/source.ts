import type { ComplaintCluster, ComplaintMarker } from "./types";

export function clusterByBuilding(markers: ComplaintMarker[]): ComplaintCluster[] {
  const groups = new Map<string, ComplaintMarker[]>();
  for (const m of markers) {
    const g = groups.get(m.buildingId);
    if (g) g.push(m);
    else groups.set(m.buildingId, [m]);
  }
  const clusters: ComplaintCluster[] = [];
  for (const [buildingId, items] of groups) {
    const byCategory: Record<string, number> = {};
    for (const m of items) byCategory[m.category] = (byCategory[m.category] ?? 0) + 1;
    const latest = [...items]
      .sort((a, b) => Date.parse(b.reportedAt) - Date.parse(a.reportedAt))
      .slice(0, 3);
    clusters.push({ buildingId, count: items.length, byCategory, latest });
  }
  return clusters.sort((a, b) => b.count - a.count || a.buildingId.localeCompare(b.buildingId));
}
