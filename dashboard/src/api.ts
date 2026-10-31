// Typed client for the NetCoop AI backend (src/netcoop/api). Paths are relative so the
// same build works behind the Vite dev proxy and when served by FastAPI.

export interface Health {
  status: string;
  mode: "simulation";
  banner: string;
  version: string;
  features: { community_signals: boolean; geospatial: boolean; llm: boolean };
}

export interface ScenarioInfo {
  id: string;
  title: string;
  provenance: string;
  pdf_suggested_scenario: string | null;
}

export interface IncidentSummary {
  incident_id: string;
  state: string | null;
  label: string | null;
  source: string | null;
  created_at: string | null;
  status: string | null;
  top_cause: string | null;
  confidence: number | null;
  affected_devices: string[];
  resumable: boolean;
}

export interface Evidence {
  metric: string;
  value: number | string;
  interpretation: string;
}

export interface RecommendationStatus {
  action: string;
  requires_human_approval: boolean;
  approval_state: string;
  simulated: boolean;
  reviewer?: string;
  simulated_outcome?: string | null;
}

export interface Report {
  incident_id: string;
  status: string;
  suspected_root_cause: string;
  confidence: number;
  affected_devices: string[];
  supporting_evidence: Evidence[];
  alternative_causes: string[];
  recommended_actions: string[];
  evidence_sources: string[];
  limitations: string[];
  netcoop_extensions?: {
    mode: string;
    data_provenance: string;
    topology_provenance?: string;
    confidence_method: string;
    confidence_category: string;
    narrative?: string;
    not_assessable?: { entity: string; metric: string; reason: string; detail: string }[];
    recommendation_status?: RecommendationStatus[];
    community_signals?: {
      candidate_id: string;
      zone: string;
      trust_label: string;
      distinct_reporters: number;
    }[];
    top_cause_type?: string;
  };
}

export interface IncidentDetail extends IncidentSummary {
  transitions: { seq: number; from_state: string | null; to_state: string; trigger: string; at: string }[];
  report: Report | null;
}

export interface TraceEvent {
  kind: "state" | "message";
  at: string;
  seq: number;
  summary: string;
  message_id: string | null;
  sender: string | null;
  recipient: string | null;
  type: string | null;
  valid: boolean;
  error_code: string | null;
}

export interface ReviewItem {
  index: number;
  action: string;
  approval_state: string;
  reviewer: string | null;
}

export interface Candidate {
  candidate_id: string;
  zone: string;
  entities: string[];
  symptom_categories: string[];
  complaint_count: number;
  distinct_reporters: number;
}

type Point = [number, number];
export interface MapLayers {
  crs: string;
  bounds: Point[];
  banner: string;
  provenance_note: string;
  zones: { zone: string; label: string; polygon: Point[]; provenance: string }[];
  devices: { id: string; role: string; zone: string; position: Point; core: boolean; provenance: string }[];
  links: { id: string; a: string; b: string; from: Point; to: Point; provenance: string }[];
}

export interface BlastRadius {
  failed: string;
  isolated: string[];
  degraded: string[];
  unaffected: string[];
  unknown: string[];
  basis: string;
}

export interface Overlay {
  reported_areas: { zone: string; trust_label: string; distinct_reporters: number }[];
  detected_faults: { entity: string; cause: string; confidence: number; trust_label: string }[];
  corroborated: { zone: string }[];
  blast_radius: Record<string, BlastRadius>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => call<Health>("/api/health"),
  scenarios: () => call<ScenarioInfo[]>("/api/scenarios"),
  runScenario: (id: string, faults: Record<string, string>) =>
    post<IncidentSummary>(`/api/scenarios/${id}/run`, { fault_injection: faults }),
  incidents: () => call<IncidentSummary[]>("/api/incidents"),
  incident: (id: string) => call<IncidentDetail>(`/api/incidents/${id}`),
  trace: (id: string) => call<{ events: TraceEvent[] }>(`/api/incidents/${id}/trace`),
  review: (id: string) => call<ReviewItem[]>(`/api/incidents/${id}/review`),
  decide: (id: string, index: number, decision: "approve" | "reject", reviewer: string) =>
    post<{ simulated_outcome: string | null; incident_state: string }>(
      `/api/incidents/${id}/review/${index}`,
      { decision, reviewer, note: "" },
    ),
  resume: (id: string) => post<IncidentSummary>(`/api/incidents/${id}/resume`, {}),
  complain: (text: string, reporter: string) =>
    post<{ accepted: boolean; zone: string | null; reason: string | null; symptoms: string[]; notice: string }>(
      "/api/community/complaints",
      { text, reporter },
    ),
  candidates: () => call<Candidate[]>("/api/community/candidates"),
  investigate: (cand: string, scenario: string) =>
    post<IncidentSummary>(`/api/community/candidates/${cand}/investigate`, { scenario_id: scenario }),
  layers: () => call<MapLayers>("/api/geo/layers"),
  overlay: (id: string) => call<Overlay>(`/api/geo/incidents/${id}`),
  blast: (entity: string) => call<BlastRadius>(`/api/geo/blast-radius/${entity}`),
};
