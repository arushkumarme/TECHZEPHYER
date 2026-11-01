import type { CampusFeature } from "../campus/features";
import type { ComplaintCluster } from "./types";

const CATEGORY_LABEL: Record<string, string> = {
  wifi: "Wi-Fi",
  slow: "Slow",
  disconnect: "Disconnects",
  other: "Other",
};

/** Sample-report summary for one building. Illustrative demo data only, never diagnosis input. */
export function BuildingSummary({ building, cluster }: { building: CampusFeature; cluster: ComplaintCluster }) {
  const categories = Object.entries(cluster.byCategory).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return (
    <section className="building-summary" aria-label={`Sample reports for ${building.name}`}>
      <h4 className="bs-head">
        <span className="tag neutral sample-tag">SAMPLE</span>
        <span>{building.name}</span>
      </h4>
      <p className="bs-count">
        <span className="mono">{cluster.count === 1 ? "1 report" : `${cluster.count} reports`}</span>
        <span className="muted"> · illustrative demo data</span>
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
