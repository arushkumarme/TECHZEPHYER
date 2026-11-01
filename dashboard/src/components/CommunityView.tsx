import { useEffect, useState } from "react";
import { api, type Candidate, type ScenarioInfo } from "../api";

// Web reporting form (doc 10 §2, primary channel) and candidate incidents. In this
// simulation every submission is a synthetic test report.
export function CommunityView({ scenarios, onInvestigated }: {
  scenarios: ScenarioInfo[];
  onInvestigated: (incidentId: string) => void;
}) {
  const [text, setText] = useState("");
  const [reporter, setReporter] = useState("");
  const [ack, setAck] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [scenario, setScenario] = useState("S-02");
  const [busy, setBusy] = useState(false);

  const refresh = () => api.candidates().then(setCandidates).catch((e: Error) => setError(e.message));
  useEffect(() => { void refresh(); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.complain(text, reporter);
      setAck(r.accepted
        ? `Report received${r.zone ? ` for ${r.zone}` : " (location not recognised)"}. ${r.notice}`
        : `Report not accepted: ${r.reason}.`);
      setText("");
      setError(null);
      void refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const investigate = async (cand: string) => {
    setBusy(true);
    try {
      const inc = await api.investigate(cand, scenario);
      onInvestigated(inc.incident_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="community">
      <section className="panel">
      <div className="label">Reporting form</div>
      <h2>Report a network problem</h2>
      <p className="muted small" style={{ maxWidth: "70ch" }}>
        Test submissions only. Reports are unverified: they can start an investigation, but only network telemetry can confirm a fault.
      </p>
      <form onSubmit={submit} style={{ maxWidth: "36rem" }}>
        <label htmlFor="complaint">What is happening, and where?</label>
        <textarea id="complaint" rows={3} value={text} onChange={(e) => setText(e.target.value)}
                  placeholder="Hostel A Wi-Fi is disconnecting." required />
        <label htmlFor="reporter-id">Reporter (test account; stored only as a pseudonym)</label>
        <input id="reporter-id" value={reporter} onChange={(e) => setReporter(e.target.value)} required />
        <div className="row"><button className="primary" type="submit">Send report</button></div>
      </form>
      {ack && <div className="notice" role="status">{ack}</div>}
      {error && <div className="error-box" role="alert">{error}</div>}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
      <div className="label">Unverified reports</div>
      <h2>Candidate incidents</h2>
      {candidates.length === 0 ? (
        <p className="muted">No candidates yet. A candidate needs reports from at least two different people about the same place within an hour.</p>
      ) : (
        <>
          <label htmlFor="inv-scenario">Investigate against telemetry from</label>
          <select id="inv-scenario" value={scenario} onChange={(e) => setScenario(e.target.value)} style={{ maxWidth: "26rem" }}>
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.id} — {s.title}</option>)}
          </select>
          <table style={{ marginTop: "0.75rem" }}>
            <thead><tr><th scope="col">Candidate</th><th scope="col">Zone</th><th scope="col">Devices</th><th scope="col">Reporters</th><th scope="col">Symptoms</th><th scope="col" /></tr></thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.candidate_id}>
                  <td className="id"><span className="tag neutral">{c.candidate_id}</span></td><td>{c.zone}</td><td className="id">{c.entities.join(", ")}</td>
                  <td>{c.distinct_reporters}</td><td>{c.symptom_categories.join(", ")}</td>
                  <td><button className="secondary" disabled={busy} onClick={() => investigate(c.candidate_id)}>Investigate</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      </section>
    </div>
  );
}
