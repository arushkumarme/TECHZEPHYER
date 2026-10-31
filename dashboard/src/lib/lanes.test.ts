import { describe, expect, it } from "vitest";
import type { TraceEvent } from "../api";
import { layoutTrace, AGENT_LABELS } from "./lanes";

const ev = (over: Partial<TraceEvent>): TraceEvent => ({
  kind: "message", at: "2026-10-31T12:00:00Z", seq: 1, summary: "", message_id: "M1",
  sender: "orchestrator", recipient: "performance_agent", type: "task_request", valid: true,
  error_code: null, ...over,
});

describe("layoutTrace", () => {
  it("orders lanes canonically and only includes participants", () => {
    const { lanes } = layoutTrace([
      ev({ sender: "orchestrator", recipient: "correlation_agent" }),
      ev({ sender: "performance_agent", recipient: "orchestrator", type: "finding" }),
    ]);
    expect(lanes).toEqual(["orchestrator", "performance_agent", "correlation_agent"]);
  });

  it("draws messages as arrows between lanes and states as bands", () => {
    const { rows } = layoutTrace([
      ev({ kind: "state", summary: "- -> RECEIVED (cli)", type: "RECEIVED", sender: null,
           recipient: null, message_id: null }),
      ev({}),
      ev({ sender: "performance_agent", recipient: "orchestrator", type: "finding",
           message_id: "M1.R" }),
    ]);
    expect(rows[0]).toMatchObject({ kind: "state", label: "RECEIVED" });
    expect(rows[1]).toMatchObject({ kind: "message", from: 0, to: 1, type: "task_request" });
    expect(rows[2]).toMatchObject({ kind: "message", from: 1, to: 0, type: "finding" });
  });

  it("keeps invalid messages visible and flagged", () => {
    const { rows } = layoutTrace([ev({ valid: false, error_code: "MESSAGE_INVALID" })]);
    expect(rows[0]).toMatchObject({ invalid: true, error: "MESSAGE_INVALID" });
  });

  it("has a plain-language label for every lane", () => {
    expect(AGENT_LABELS.performance_agent).toBe("Performance");
    expect(Object.keys(AGENT_LABELS)).toHaveLength(7);
  });
});
