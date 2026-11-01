import type { IncidentDetail, Report, TraceEvent } from "../../api";

// Trimmed from docs/results/example-S-02-report.json and example-S-02-trace.txt.
export const S02_REPORT: Report = {
  incident_id: "INC-0014",
  status: "diagnosed",
  suspected_root_cause: "Likely link congestion causing egress queue drops on SW_CAMPUS_4",
  confidence: 0.6649,
  affected_devices: ["SW_CAMPUS_4"],
  supporting_evidence: [
    { metric: "link_utilization_pct", value: 78.88, interpretation: "Elevated link utilization on SW_CAMPUS_4 (sustained)" },
    { metric: "queue_drops", value: 35, interpretation: "Elevated egress queue drops on SW_CAMPUS_4 (sustained)" },
  ],
  alternative_causes: ["Device or hardware failure on SW_CAMPUS_4 (heuristic score 0.48)"],
  recommended_actions: ["Inspect egress link utilization and traffic distribution on the affected device (SW_CAMPUS_4)"],
  evidence_sources: ["infrastructure_agent", "performance_agent"],
  limitations: [
    "Root cause requires further verification by an operator.",
    "Confidence is a heuristic score from a documented method (doc 08), not a probability.",
  ],
  netcoop_extensions: {
    mode: "simulation",
    data_provenance: "synthetic-generator",
    topology_provenance: "SIMULATED",
    confidence_method: "heuristic",
    confidence_category: "medium",
    not_assessable: [
      { entity: "SW_CAMPUS_1", metric: "interface_errors", reason: "MISSING", detail: "" },
      { entity: "SW_CAMPUS_4", metric: "interface_errors", reason: "MISSING", detail: "" },
    ],
    hypotheses: [{ cause_type: "link_congestion", entities: ["SW_CAMPUS_4"], score: 0.6649 }],
  },
};

export const S02_DETAIL: IncidentDetail = {
  incident_id: "INC-0014",
  state: "AWAITING_REVIEW",
  label: "S-02",
  source: "scenario",
  created_at: "2026-10-31T15:55:50Z",
  status: "diagnosed",
  top_cause: "link_congestion",
  confidence: 0.6649,
  affected_devices: ["SW_CAMPUS_4"],
  resumable: false,
  transitions: [],
  report: S02_REPORT,
};

const msg = (seq: number, sender: string, recipient: string, type: string, summary: string): TraceEvent => ({
  kind: "message", at: "2026-10-31T15:55:50Z", seq, summary, message_id: `INC-0014-MSG-${seq}`,
  sender, recipient, type, valid: true, error_code: null,
});

export const S02_TRACE: TraceEvent[] = [
  msg(1, "orchestrator", "performance_agent", "task_request", "goal=assess_performance"),
  msg(2, "performance_agent", "orchestrator", "finding", "40 observations"),
  msg(3, "orchestrator", "correlation_agent", "task_request", "goal=correlate"),
  msg(4, "correlation_agent", "orchestrator", "decision", "diagnosed top=link_congestion ['SW_CAMPUS_4']"),
];
