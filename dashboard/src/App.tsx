import { useCallback, useEffect, useState } from "react";
import { api, type Health, type IncidentSummary, type MapLayers, type ScenarioInfo } from "./api";
import { CommunityView } from "./components/CommunityView";
import { IncidentView, StatusTag } from "./components/IncidentView";
import { MapView } from "./components/MapView";

type Tab = "incidents" | "map" | "community";
const FAULTS = ["", "timeout", "error", "invalid"] as const;
const AGENTS = ["performance_agent", "infrastructure_agent", "connectivity_agent"];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("incidents");
  const [scenario, setScenario] = useState("S-02");
  const [faultAgent, setFaultAgent] = useState(AGENTS[0]);
  const [fault, setFault] = useState<(typeof FAULTS)[number]>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => api.incidents().then(setIncidents), []);
  const geospatial = !!health?.features.geospatial;

  useEffect(() => {
    Promise.all([api.health(), api.scenarios(), api.incidents()])
      .then(([h, s, i]) => { setHealth(h); setScenarios(s); setIncidents(i); })
      .catch((e: Error) => setError(`Cannot reach the NetCoop AI backend (${e.message}). Start it with: uv run fastapi dev`));
  }, []);

  // The map layers are static for a session: fetch once, only when the API serves them.
  useEffect(() => {
    if (!geospatial) return;
    api.layers().then(setLayers).catch(() => setLayers(null));
  }, [geospatial]);

  const run = async () => {
    setRunning(true);
    try {
      const inc = await api.runScenario(scenario, fault ? { [faultAgent]: fault } : {});
      await refresh();
      setSelected(inc.incident_id);
      setTab("incidents");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const tabs: [Tab, string, boolean][] = [
    ["incidents", "Incidents", true],
    ["map", "Campus map", geospatial],
    ["community", "User reports", !!health?.features.community_signals],
  ];
  const chosen = scenarios.find((s) => s.id === scenario);

  return (
    <div className="shell">
      <header className="masthead">
        <div className="topbar">
          <h1 className="brand">NetCoop AI</h1>
          <nav className="tabs" role="tablist" aria-label="Views">
            {tabs.filter(([, , on]) => on).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
            ))}
          </nav>
          <span className="pill">Simulated data · scenario playback</span>
          <div className="run-controls" aria-label="Run a scenario" role="group">
            <label htmlFor="scenario">Scenario</label>
            <select
              id="scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              title={chosen ? `Data: ${chosen.provenance}` : undefined}
            >
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.id} — {s.title}</option>)}
            </select>
            <details className={fault ? "fault-menu armed" : "fault-menu"}>
              <summary>Simulate an agent failure</summary>
              <div className="fault-pop panel">
                <label htmlFor="fault-agent">Agent</label>
                <select id="fault-agent" value={faultAgent} onChange={(e) => setFaultAgent(e.target.value)}>
                  {AGENTS.map((a) => <option key={a}>{a}</option>)}
                </select>
                <label htmlFor="fault">Failure</label>
                <select id="fault" value={fault} onChange={(e) => setFault(e.target.value as (typeof FAULTS)[number])}>
                  <option value="">None</option>
                  <option value="timeout">Answers too late</option>
                  <option value="error">Reports an error</option>
                  <option value="invalid">Sends a malformed message</option>
                </select>
              </div>
            </details>
            <button className="primary" onClick={run} disabled={running || !scenarios.length}>
              {running ? "Diagnosing…" : "Run diagnosis"}
            </button>
          </div>
        </div>
        <div className="banner" role="note">
          <strong>Simulated data — scenario playback.</strong>
          Synthetic telemetry and a simulated topology. NetCoop AI has no access to any real campus network, and every corrective action is simulated.
        </div>
      </header>
      <div className="layout">
        <aside className="rail" aria-label="Incidents">
          <h2 className="label">Incidents</h2>
          {chosen && <p className="rail-meta">Data: <span className="mono">{chosen.provenance}</span></p>}
          {incidents.length === 0 ? (
            <p className="rail-empty">No incidents yet. Run a scenario to start one.</p>
          ) : (
            <ul className="incident-list">
              {incidents.map((i) => (
                <li key={i.incident_id}>
                  <button
                    aria-current={selected === i.incident_id}
                    title={`${i.incident_id}${i.label ? ` · ${i.label}` : ""}`}
                    onClick={() => { setSelected(i.incident_id); setTab("incidents"); }}
                  >
                    <span className="inc-head">
                      <span className="id">{i.incident_id}</span>
                      {i.label && <span className="inc-scenario">{i.label}</span>}
                    </span>
                    <StatusTag status={i.status} />
                    <span className="inc-cause">{i.top_cause?.replace(/_/g, " ") ?? i.state}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <main className="main">
          {error && <div className="error-box" role="alert">{error}</div>}
          {tab === "incidents" && (selected ? (
            <IncidentView key={selected} id={selected} onChanged={() => void refresh()} />
          ) : (
            <div className="empty-state panel">
              <h2>Choose an incident</h2>
              <p className="muted">
                Pick a scenario in the top bar and press Run diagnosis. Three specialist agents examine the telemetry in parallel, a correlation agent weighs their findings, and a reporting agent writes one report. You can follow every message between them.
              </p>
            </div>
          ))}
          {tab === "map" && <MapView incidents={incidents} layers={layers} />}
          {tab === "community" && (
            <CommunityView scenarios={scenarios} onInvestigated={async (id) => { await refresh(); setSelected(id); setTab("incidents"); }} />
          )}
        </main>
      </div>
    </div>
  );
}
