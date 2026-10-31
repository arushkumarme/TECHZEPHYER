import { useState } from "react";
import type { TraceEvent } from "../api";
import { AGENT_LABELS, layoutTrace, type Row } from "../lib/lanes";

const LANE_W = 128;
const ROW_H = 26;
const TOP = 34;
const REPLIES = new Set(["finding", "decision", "report_ready", "clarification_response"]);

// Every message between the orchestrator and the agents, in order: the visible evidence
// that agents exchange and reconcile findings (SRC-1 p7 §10).
export function Swimlane({ events }: { events: TraceEvent[] }) {
  const { lanes, rows } = layoutTrace(events);
  const [selected, setSelected] = useState<number | null>(null);
  const width = lanes.length * LANE_W;
  const height = TOP + rows.length * ROW_H + 8;
  const x = (lane: number) => lane * LANE_W + LANE_W / 2;
  const chosen = selected === null ? null : rows[selected];

  return (
    <div className="swim">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Message exchange: ${rows.filter((r) => r.kind === "message").length} messages between ${lanes.length} participants`}
      >
        <defs>
          <marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="context-stroke" />
          </marker>
        </defs>
        {lanes.map((lane, i) => (
          <g key={lane}>
            <text className="lane-label" x={x(i)} y={18} textAnchor="middle">
              {AGENT_LABELS[lane] ?? lane}
            </text>
            <line className="lane-line" x1={x(i)} x2={x(i)} y1={TOP - 6} y2={height} />
          </g>
        ))}
        {rows.map((row, i) => {
          const y = TOP + i * ROW_H + ROW_H / 2;
          return (
            <g key={i}>
              {row.kind === "state" ? (
                <>
                  <rect className="state-band" x={0} y={y - 9} width={width} height={18} />
                  <text className="state-text" x={6} y={y + 4}>{row.label}</text>
                </>
              ) : (
                <MessageArrow row={row} y={y} x={x} />
              )}
              <rect
                className="row-hit"
                x={0}
                y={y - ROW_H / 2}
                width={width}
                height={ROW_H}
                tabIndex={0}
                role="button"
                aria-label={row.kind === "state" ? `State ${row.label}` : `${row.type}: ${row.summary}`}
                onClick={() => setSelected(i)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setSelected(i)}
              />
            </g>
          );
        })}
      </svg>
      <p className="swim-detail" aria-live="polite">
        {chosen === null
          ? "Select a row to read the message."
          : chosen.kind === "state"
            ? `State change: ${chosen.detail}`
            : `${chosen.type}${chosen.messageId ? ` (${chosen.messageId})` : ""}: ${chosen.summary}${chosen.invalid ? ` — rejected: ${chosen.error}` : ""}`}
      </p>
    </div>
  );
}

function MessageArrow({ row, y, x }: { row: Extract<Row, { kind: "message" }>; y: number; x: (l: number) => number }) {
  const cls = [
    "arrow",
    REPLIES.has(row.type) ? "reply" : "",
    row.type.startsWith("clarification") ? "clarify" : "",
    row.invalid || row.type === "agent_error" ? "error" : "",
  ].join(" ");
  if (row.from === row.to) {
    return <circle cx={x(row.from)} cy={y} r={4} className={cls} />;
  }
  const x1 = x(row.from) + (row.to > row.from ? 4 : -4);
  const x2 = x(row.to) + (row.to > row.from ? -4 : 4);
  return (
    <g>
      <line className={cls} x1={x1} x2={x2} y1={y} y2={y} markerEnd="url(#head)" />
      <text className="arrow-label" x={(x1 + x2) / 2} y={y - 4} textAnchor="middle">
        {row.type.replace(/_/g, " ")}
      </text>
    </g>
  );
}
