import type { TraceEvent } from "../api";

// Canonical left-to-right order: who starts work, the hub, specialists, then the agents
// that combine and report. Labels are what an operator calls each participant.
export const AGENT_LABELS: Record<string, string> = {
  community_module: "Community reports",
  orchestrator: "Orchestrator",
  performance_agent: "Performance",
  infrastructure_agent: "Infrastructure",
  connectivity_agent: "Connectivity",
  correlation_agent: "Correlation",
  reporting_agent: "Reporting",
};
const ORDER = Object.keys(AGENT_LABELS);

export type Row =
  | { kind: "state"; label: string; detail: string; at: string }
  | {
      kind: "message";
      from: number;
      to: number;
      type: string;
      summary: string;
      messageId: string | null;
      invalid: boolean;
      error: string | null;
      at: string;
    };

export function layoutTrace(events: TraceEvent[]): { lanes: string[]; rows: Row[] } {
  const present = new Set<string>(["orchestrator"]);
  for (const e of events) {
    if (e.kind === "message") {
      if (e.sender) present.add(e.sender);
      if (e.recipient) present.add(e.recipient);
    }
  }
  const lanes = ORDER.filter((a) => present.has(a));
  const index = (a: string | null) => Math.max(0, lanes.indexOf(a ?? "orchestrator"));
  const rows: Row[] = events.map((e) =>
    e.kind === "state"
      ? { kind: "state", label: e.type ?? "", detail: e.summary, at: e.at }
      : {
          kind: "message",
          from: index(e.sender),
          to: index(e.recipient),
          type: e.type ?? "message",
          summary: e.summary,
          messageId: e.message_id,
          invalid: !e.valid,
          error: e.error_code,
          at: e.at,
        },
  );
  return { lanes, rows };
}
