import { useCallback, useEffect, useRef, useState } from "react";
import type { TraceEvent } from "../api";

export const STRIP_AGENTS = [
  "performance_agent",
  "infrastructure_agent",
  "connectivity_agent",
  "correlation_agent",
  "reporting_agent",
] as const;

/** Unique campus switch ids mentioned in a text, in order of first appearance. */
export function devicesIn(summary: string): string[] {
  return [...new Set(summary.match(/SW_CAMPUS_\d+/g) ?? [])];
}

export type AgentStatus = "idle" | "waiting" | "replied" | "error";

export function agentActivity(
  events: TraceEvent[],
  upTo: number,
): Record<string, { messages: number; status: AgentStatus }> {
  const seen = events.slice(0, upTo + 1).filter((e) => e.kind === "message");
  const out: Record<string, { messages: number; status: AgentStatus }> = {};
  for (const agent of STRIP_AGENTS) {
    let messages = 0;
    let error = false;
    let sentValid = false;
    let received = false;
    for (const e of seen) {
      const sent = e.sender === agent;
      const got = e.recipient === agent;
      if (!sent && !got) continue;
      messages += 1;
      if (sent) {
        if (!e.valid || e.type === "agent_error") error = true;
        else sentValid = true;
      }
      if (got) {
        received = true;
        if (!e.valid) error = true;
      }
    }
    const status: AgentStatus = error
      ? "error"
      : sentValid
        ? "replied"
        : received
          ? "waiting"
          : "idle";
    out[agent] = { messages, status };
  }
  return out;
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export function useReplay(
  rowCount: number,
  opts: { auto: boolean; stepMs?: number; resetKey: string },
): {
  cursor: number;
  playing: boolean;
  play(): void;
  pause(): void;
  step(): void;
  restart(): void;
} {
  const stepMs = opts.stepMs ?? 450;
  const last = rowCount - 1;
  // null means "never started": everything is revealed.
  const [pos, setPos] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const autoStarted = useRef(false);
  const lastKey = useRef(opts.resetKey);

  // Auto-play is due but its effect has not run yet: render as already started at row 0,
  // so the fully revealed trace never shows for one frame before the replay begins.
  const autoPending = opts.auto && !autoStarted.current && rowCount > 0 && !prefersReducedMotion();
  const cursor = autoPending ? 0 : pos === null ? last : Math.min(pos, last);

  // Auto-play once, the first time rows exist.
  useEffect(() => {
    if (!opts.auto || autoStarted.current || rowCount <= 0) return;
    autoStarted.current = true;
    if (prefersReducedMotion()) return;
    setPos(0);
    setPlaying(true);
  }, [opts.auto, rowCount]);

  // A new incident: stop, reveal everything, never auto-play again.
  useEffect(() => {
    if (lastKey.current === opts.resetKey) return;
    lastKey.current = opts.resetKey;
    autoStarted.current = true;
    setPlaying(false);
    setPos(null);
  }, [opts.resetKey]);

  // Advance one row per tick while playing.
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setPos((p) => Math.min((p ?? last) + 1, last));
    }, stepMs);
    return () => clearInterval(id);
  }, [playing, last, stepMs]);

  // Stop once the last row is revealed.
  useEffect(() => {
    if (playing && cursor >= last) setPlaying(false);
  }, [playing, cursor, last]);

  const start = useCallback(
    (from: number) => {
      if (prefersReducedMotion()) {
        setPos(null);
        setPlaying(false);
        return;
      }
      setPos(from);
      setPlaying(true);
    },
    [],
  );

  const play = useCallback(() => {
    start(pos === null || cursor >= last ? 0 : cursor);
  }, [start, pos, cursor, last]);
  const pause = useCallback(() => {
    setPos(cursor);
    setPlaying(false);
  }, [cursor]);
  // From a fully revealed trace, Step starts over at the first row; otherwise it advances one.
  const step = useCallback(() => {
    setPos(pos === null || cursor >= last ? 0 : Math.min(cursor + 1, last));
    setPlaying(false);
  }, [pos, cursor, last]);
  const restart = useCallback(() => start(0), [start]);

  return { cursor, playing: playing || autoPending, play, pause, step, restart };
}
