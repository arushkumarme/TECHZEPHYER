import type { CampusFeature } from "../campus/features";
import type { ComplaintCluster } from "./types";

const CATEGORY_LABEL: Record<string, string> = {
  wifi: "Wi-Fi",
  slow: "Slow",
  disconnect: "Disconnects",
  other: "Other",
};

/**
 * Report summary for one building. Never diagnosis input. With `isSample` (the default, and
 * today's only source) it is marked SAMPLE and illustrative demo data.
 */
export function BuildingSummary({
  building,
  cluster,
  isSample = true,
}: {
  building: CampusFeature;
  cluster: ComplaintCluster;
  isSample?: boolean;
}) {
  const categories = Object.entries(cluster.byCategory).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return (
    <section className="building-summary" aria-label={`${isSample ? "Sample reports" : "Reports"} for ${building.name}`}>
      <h4 className="bs-head">
        {isSample && <span className="tag neutral sample-tag">SAMPLE</span>}
        <span>{building.name}</span>
      </h4>
      <p className="bs-count">
        <span className="mono">{cluster.count === 1 ? "1 report" : `${cluster.count} reports`}</span>
        <span className="muted">{isSample ? " · illustrative demo data" : " · unverified user reports"}</span>
      </p>
      <ul className="bs-cats">
        {categories.map(([cat, n]) => (
          <li key={cat}>
            <span>{CATEGORY_LABEL[cat] ?? cat}</span>
            <span className="mono">{n}</span>
          </li>
        ))}
      </ul>
      <ol className="bs-latest">
        {cluster.latest.slice(0, 3).map((m) => (
          <li key={m.id}>
            <span>{m.text}</span>
            <time className="mono muted" dateTime={m.reportedAt}>{m.reportedAt.slice(0, 10)}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}
