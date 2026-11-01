import { useState } from "react";
import { api, type IncidentDetail, type ReviewItem } from "../api";

const STATUS_TEXT: Record<string, string> = {
  diagnosed: "Fault diagnosed",
  insufficient_evidence: "Needs more evidence",
  no_fault_detected: "No fault",
  failed: "Run failed",
};

/** The report status as a tag: text always, colour and border style from the status class. */
export function StatusTag({ status }: { status: string | null }) {
  if (!status) return <span className="status failed">Not reported yet</span>;
  return <span className={`status ${status}`}>{STATUS_TEXT[status] ?? status}</span>;
}

function ConfidenceMeter({ value, category, method }: { value: number; category: string; method: string }) {
  return (
    <div className="meter">
      <span>Confidence {value.toFixed(2)}</span>
      <div
        className="meter-track"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value}
        aria-label="Heuristic confidence score"
      >
        <div className="meter-fill" style={{ width: `${Math.round(value * 100)}%` }} />
        <div className="meter-mark" style={{ left: "55%" }} />
        <span className="meter-mark-label" style={{ left: "55%" }}>threshold 0.55</span>
      </div>
      <span className="muted small">
        {category}, {method} score — a ranking, not a probability
      </span>
    </div>
  );
}

/**
 * The right-hand panel of the Incidents tab: what the agents concluded, how sure the
 * heuristic is, the evidence, the alternatives, the actions awaiting a person, and what
 * could not be assessed. With no report yet it shows only the header and the state.
 */
export function DiagnosisPanel({
  id,
  detail,
  review,
  onChanged,
  onReload,
}: {
  id: string;
  detail: IncidentDetail;
  review: ReviewItem[];
  onChanged: () => void;
  onReload: () => void;
}) {
  const r = detail.report;
  const ext = r?.netcoop_extensions;

  return (
    <article className="diagnosis panel" aria-labelledby="incident-title">
      <h2 id="incident-title">
        <span className="id">{id}</span> <StatusTag status={detail.status} />
        <span className="dx-state muted small">state {detail.state}{detail.label ? `, ${detail.label}` : ""}</span>
      </h2>
      {detail.resumable && (
        <div className="notice">
          This incident is paused.{" "}
          <button className="secondary" onClick={async () => { await api.resume(id); onChanged(); onReload(); }}>
            Resume diagnosis
          </button>
        </div>
      )}
      {!r && !detail.resumable && (
        <p className="muted small dx-pending">No report for this incident yet.</p>
      )}
      {r && ext && (
        <>
          <p className={r.suspected_root_cause.length > 120 ? "cause long" : "cause"}>{r.suspected_root_cause}</p>
          {/* The template narrative restates the headline; show it only when it adds
              something (e.g. an accepted, grounding-checked rewording). */}
          {ext.narrative && !ext.narrative.startsWith(r.suspected_root_cause) && (
            <p className="narrative">{ext.narrative}</p>
          )}
          <ConfidenceMeter value={r.confidence} category={ext.confidence_category} method={ext.confidence_method} />
          <p className="small muted dx-meta">
            Affected devices: {r.affected_devices.length ? r.affected_devices.map((d) => <code key={d}>{d} </code>) : "none identified"}
            {" — "}data: {ext.data_provenance}; topology: {ext.topology_provenance ?? "unavailable"}
          </p>
        </>
      )}

      {r && (
        <>
          <section className="dx-section" aria-labelledby="evidence">
            <h3 id="evidence" className="label">Supporting evidence</h3>
            {r.supporting_evidence.length ? (
              <table className="dx-evidence">
                <thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">What it shows</th></tr></thead>
                <tbody>
                  {r.supporting_evidence.map((e, i) => (
                    <tr key={i}><td><code>{e.metric}</code></td><td className="mono">{e.value}</td><td>{e.interpretation}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted">No telemetry evidence supports a cause.</p>}
            <p className="small muted">From: {r.evidence_sources.join(", ") || "no agent"}</p>
            {ext?.community_signals && ext.community_signals.length > 0 && (
              <div className="notice">
                User reports (unverified, kept apart from telemetry evidence):{" "}
                {ext.community_signals.map((s) => `${s.zone} — ${s.distinct_reporters} reporters, ${s.trust_label.replace(/_/g, " ")}`).join("; ")}
              </div>
            )}
          </section>

          <section className="dx-section" aria-labelledby="alts">
            <h3 id="alts" className="label">Also considered</h3>
            {r.alternative_causes.length ? (
              <ul className="list">{r.alternative_causes.map((a) => <li key={a}>{a}</li>)}</ul>
            ) : <p className="muted small">None scored above zero.</p>}
          </section>

          <ReviewPanel id={id} items={review} onDone={() => { onChanged(); onReload(); }} />

          <section className="dx-section" aria-labelledby="gaps">
            <h3 id="gaps" className="label">What could not be assessed</h3>
            <NotAssessable items={ext?.not_assessable ?? []} />
            <h4 className="dx-sub">Limitations</h4>
            <ul className="list">{r.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </section>
        </>
      )}
    </article>
  );
}

function NotAssessable({ items }: { items: { entity: string; metric: string; reason: string }[] }) {
  if (!items.length) return <p className="muted small">Everything in scope was assessed.</p>;
  const grouped = new Map<string, string[]>();
  for (const n of items) {
    const key = `${n.metric} (${n.reason.toLowerCase().replace(/_/g, " ")})`;
    grouped.set(key, [...(grouped.get(key) ?? []), n.entity]);
  }
  return (
    <ul className="list">
      {[...grouped].map(([k, v]) => (
        <li key={k}><code>{k.split(" ")[0]}</code> {k.slice(k.indexOf(" "))}: {v.length} device{v.length > 1 ? "s" : ""} — never treated as healthy</li>
      ))}
    </ul>
  );
}

function ReviewPanel({ id, items, onDone }: { id: string; items: ReviewItem[]; onDone: () => void }) {
  const [reviewer, setReviewer] = useState("");
  const [outcomes, setOutcomes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  if (!items.length) return null;

  const decide = async (index: number, decision: "approve" | "reject") => {
    try {
      const r = await api.decide(id, index, decision, reviewer);
      setOutcomes((o) => ({ ...o, [index]: r.simulated_outcome ?? "Rejected. Nothing will be simulated." }));
      setError(null);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="dx-section" aria-labelledby="review">
      <h3 id="review" className="label">Recommended actions</h3>
      <p className="muted small">
        Each action needs a person's decision. Approving runs a simulation only — no device is changed.
      </p>
      <label htmlFor="reviewer">Your name (recorded with each decision)</label>
      <input id="reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
      {error && <div className="error-box">{error}</div>}
      {items.map((it) => (
        <div className="review-item" key={it.index}>
          <span>{it.action}</span>
          {it.approval_state === "pending" ? (
            <span className="row" style={{ marginTop: 0 }}>
              <button className="primary" disabled={!reviewer.trim()} onClick={() => decide(it.index, "approve")}>Approve</button>
              <button className="secondary" disabled={!reviewer.trim()} onClick={() => decide(it.index, "reject")}>Reject</button>
            </span>
          ) : (
            <span className="small">{it.approval_state === "approved" ? "Approved" : "Rejected"} by {it.reviewer}</span>
          )}
          {outcomes[it.index] && <p className="outcome">{outcomes[it.index]}</p>}
        </div>
      ))}
    </section>
  );
}
