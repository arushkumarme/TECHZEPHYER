import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Health, type IncidentSummary, type MapLayers, type ScenarioInfo } from "./api";
import { CampusMap } from "./campus/CampusMap";
import { sampleComplaintSource } from "./complaints/sample";
import type { ComplaintSource } from "./complaints/types";
import { CommunityView } from "./components/CommunityView";
import { StatusTag } from "./components/DiagnosisPanel";
import { IncidentView } from "./components/IncidentView";
import { MapView } from "./components/MapView";

type Tab = "incidents" | "map" | "community";
const FAULTS = ["", "timeout", "error", "invalid"] as const;
const AGENTS = ["performance_agent", "infrastructure_agent", "connectivity_agent"];

/** Where the Campus map tab's complaint layer comes from; a backend source replaces this. */
const COMPLAINT_SOURCE: ComplaintSource = sampleComplaintSource;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // The incident just created by Run diagnosis: its exchange replays once on arrival, and
  // `fresh` is cleared as soon as that replay starts (or the user moves to another tab).
  const [fresh, setFresh] = useState<string | null>(null);
  const [tab, setTabState] = useState<Tab>("incidents");
  const [faultOpen, setFaultOpen] = useState(false);
  const faultMenu = useRef<HTMLDetailsElement>(null);
  const [scenario, setScenario] = useState("S-02");
  const [faultAgent, setFaultAgent] = useState(AGENTS[0]);
  const [fault, setFault] = useState<(typeof FAULTS)[number]>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => api.incidents().then(setIncidents), []);
  const setTab = (next: Tab) => {
    if (next !== tab) {
      setFresh(null);
      setFaultOpen(false);
    }
    setTabState(next);
  };

  // The failure menu is a disclosure: it closes on a click elsewhere and on Escape.
  useEffect(() => {
    if (!faultOpen) return;
    const onPointer = (e: PointerEvent) => {
      if (!faultMenu.current?.contains(e.target as Node)) setFaultOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setFaultOpen(false);
      faultMenu.current?.querySelector("summary")?.focus();
    };
    document.addEventListener("pointerdown", onPointer, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [faultOpen]);
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
    setFaultOpen(false);
    try {
      const inc = await api.runScenario(scenario, fault ? { [faultAgent]: fault } : {});
      await refresh();
      setFresh(inc.incident_id);
      setSelected(inc.incident_id);
      setTabState("incidents");
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
          <div className="brand-lockup">
            <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
              <path d="M8 16 16 8m0 0 8 8m-8-8v16m0 0 8-8m-8 8-8-8" />
              <circle cx="8" cy="16" r="3" />
              <circle cx="16" cy="8" r="3" />
              <circle cx="24" cy="16" r="3" />
              <circle cx="16" cy="24" r="3" />
            </svg>
            <span>
              <h1 className="brand">NetCoop AI</h1>
              <span className="brand-caption">Campus network diagnosis</span>
            </span>
          </div>
          <nav className="tabs" role="tablist" aria-label="Views">
            {tabs.filter(([, , on]) => on).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
            ))}
          </nav>
          <div className="run-controls" aria-label="Run a scenario" role="group">
            <span className="mode-pill" title="Every input is synthetic and every action is simulated">
              {health?.mode === "simulation" || !health ? "Simulation" : health.mode}
            </span>
            <label htmlFor="scenario">Scenario</label>
            <select
              id="scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              title={chosen ? `Data: ${chosen.provenance}` : undefined}
            >
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.id} — {s.title}</option>)}
            </select>
            <details
              ref={faultMenu}
              className={fault ? "fault-menu armed" : "fault-menu"}
              open={faultOpen}
              onToggle={(e) => setFaultOpen(e.currentTarget.open)}
            >
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
          <div className="rail-head">
            <h2 className="label">Incidents</h2>
            <span className="rail-count mono">{incidents.length}</span>
          </div>
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
                    onClick={() => { setFresh(null); setSelected(i.incident_id); setTab("incidents"); }}
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
        <main className={tab === "incidents" ? "main main--incident" : "main"}>
          {error && <div className="error-box" role="alert">{error}</div>}
          {tab === "incidents" && (selected ? (
            <IncidentView
              key={selected}
              id={selected}
              onChanged={() => void refresh()}
              layers={layers}
              autoReplay={selected === fresh}
              onAutoPlayed={() => setFresh(null)}
            />
          ) : (
            // No incident yet: the campus map with every switch neutral, beside the hint.
            <div className="incident incident-empty">
              <section className="incident-hero" aria-label="Campus map">
                <CampusMap variant="hero" layers={layers} highlight={null} />
              </section>
              <div className="diagnosis panel empty-state">
                <p className="label">Overview</p>
                <h2>Choose an incident</h2>
                <p className="empty-hint">No incident selected. Pick a scenario in the top bar and press Run diagnosis, or open an incident from the list.</p>
                {chosen && (
                  <dl className="overview-dl">
                    <dt>Selected scenario</dt><dd><span className="mono">{chosen.id}</span> {chosen.title}</dd>
                    <dt>Data</dt><dd className="mono">{chosen.provenance}</dd>
                    <dt>Scenarios available</dt><dd className="mono">{scenarios.length}</dd>
                    <dt>Incidents this session</dt><dd className="mono">{incidents.length}</dd>
                  </dl>
                )}
                <ol className="steps">
                  <li><strong>Specialists</strong> Performance, infrastructure and connectivity agents examine the telemetry in parallel.</li>
                  <li><strong>Correlation</strong> A correlation agent weighs their findings against the topology.</li>
                  <li><strong>Reporting</strong> A reporting agent writes one report; the affected switches light up on the map.</li>
                </ol>
                <p className="muted small">Every message between the agents can be replayed below the map once an incident exists.</p>
              </div>
            </div>
          ))}
          {tab === "map" && <MapView incidents={incidents} layers={layers} complaintSource={COMPLAINT_SOURCE} />}
          {tab === "community" && (
            <CommunityView scenarios={scenarios} onInvestigated={async (id) => { await refresh(); setFresh(null); setSelected(id); setTab("incidents"); }} />
          )}
        </main>
      </div>
    </div>
  );
}
