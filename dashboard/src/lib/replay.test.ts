import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { TraceEvent } from "../api";
import { agentActivity, devicesIn, STRIP_AGENTS, useReplay } from "./replay";

const ev = (over: Partial<TraceEvent>): TraceEvent => ({
  kind: "message", at: "2026-10-31T12:00:00Z", seq: 1, summary: "", message_id: "M1",
  sender: "orchestrator", recipient: "performance_agent", type: "task_request", valid: true,
  error_code: null, ...over,
});

describe("devicesIn", () => {
  it("returns unique devices in order of first appearance", () => {
    expect(devicesIn("decision: link_congestion on SW_CAMPUS_4, SW_CAMPUS_4 and SW_CAMPUS_10"))
      .toEqual(["SW_CAMPUS_4", "SW_CAMPUS_10"]);
  });
  it("returns an empty list when none are mentioned", () => {
    expect(devicesIn("nothing here")).toEqual([]);
  });
});

describe("agentActivity", () => {
  const task = ev({});
  const finding = ev({ sender: "performance_agent", recipient: "orchestrator", type: "finding" });

  it("covers the five strip agents", () => {
    expect(STRIP_AGENTS).toHaveLength(5);
    expect(Object.keys(agentActivity([], -1))).toEqual([...STRIP_AGENTS]);
  });
  it("marks replied after a valid finding", () => {
    const a = agentActivity([task, finding], 1);
    expect(a.performance_agent).toEqual({ messages: 2, status: "replied" });
  });
  it("marks error for an invalid message from the agent", () => {
    const a = agentActivity([task, ev({ ...finding, valid: false })], 1);
    expect(a.performance_agent.status).toBe("error");
  });
  it("marks error for an invalid message addressed to the agent", () => {
    const a = agentActivity([ev({ valid: false })], 0);
    expect(a.performance_agent.status).toBe("error");
  });
  it("marks error for agent_error sent by the agent", () => {
    const a = agentActivity([task, ev({ ...finding, type: "agent_error" })], 1);
    expect(a.performance_agent.status).toBe("error");
  });
  it("is waiting after only a task", () => {
    expect(agentActivity([task], 0).performance_agent).toEqual({ messages: 1, status: "waiting" });
  });
  it("is idle with no messages, and respects upTo", () => {
    expect(agentActivity([task, finding], 1).reporting_agent).toEqual({ messages: 0, status: "idle" });
    expect(agentActivity([task, finding], 0).performance_agent.status).toBe("waiting");
  });
  it("ignores state events", () => {
    const s = ev({ kind: "state", sender: null, recipient: null, type: "RECEIVED" });
    expect(agentActivity([s], 0).performance_agent.status).toBe("idle");
  });
});

describe("useReplay", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  const opts = { auto: true, stepMs: 100, resetKey: "a" };

  it("auto-plays from 0 to the end then stops", () => {
    const { result } = renderHook(() => useReplay(5, opts));
    expect(result.current.cursor).toBe(0);
    expect(result.current.playing).toBe(true);
    act(() => { vi.advanceTimersByTime(400); });
    expect(result.current.cursor).toBe(4);
    expect(result.current.playing).toBe(false);
  });

  it("starts auto-play when rows arrive after first render", () => {
    const { result, rerender } = renderHook(({ n }) => useReplay(n, opts), { initialProps: { n: 0 } });
    expect(result.current.playing).toBe(false);
    rerender({ n: 5 });
    expect(result.current.cursor).toBe(0);
    act(() => { vi.advanceTimersByTime(400); });
    expect(result.current.cursor).toBe(4);
  });

  it("never renders the fully revealed trace before auto-play starts", () => {
    // Every committed render once rows exist must already be at row 0 (no one-frame flash).
    const seen: number[] = [];
    const { rerender } = renderHook(({ n }) => {
      const r = useReplay(n, opts);
      if (n > 0) seen.push(r.cursor);
      return r;
    }, { initialProps: { n: 0 } });
    rerender({ n: 5 });
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((c) => c === 0)).toBe(true);
  });

  it("shows everything when auto is false", () => {
    const { result } = renderHook(() => useReplay(5, { ...opts, auto: false }));
    expect(result.current.cursor).toBe(4);
    expect(result.current.playing).toBe(false);
  });

  it("pause freezes the cursor", () => {
    const { result } = renderHook(() => useReplay(5, opts));
    act(() => { vi.advanceTimersByTime(200); });
    act(() => { result.current.pause(); });
    const at = result.current.cursor;
    act(() => { vi.advanceTimersByTime(500); });
    expect(result.current.cursor).toBe(at);
    expect(result.current.playing).toBe(false);
  });

  it("step advances one row", () => {
    const { result } = renderHook(() => useReplay(5, { ...opts, auto: false }));
    act(() => { result.current.restart(); });
    act(() => { result.current.pause(); });
    expect(result.current.cursor).toBe(0);
    act(() => { result.current.step(); });
    expect(result.current.cursor).toBe(1);
  });

  it("restart replays from the start", () => {
    const { result } = renderHook(() => useReplay(5, { ...opts, auto: false }));
    act(() => { result.current.restart(); });
    expect(result.current.cursor).toBe(0);
    expect(result.current.playing).toBe(true);
    act(() => { vi.advanceTimersByTime(400); });
    expect(result.current.cursor).toBe(4);
  });

  it("resetKey change stops the timer and reveals everything", () => {
    const { result, rerender } = renderHook(({ k }) => useReplay(5, { ...opts, resetKey: k }), {
      initialProps: { k: "a" },
    });
    act(() => { vi.advanceTimersByTime(100); });
    rerender({ k: "b" });
    expect(result.current.playing).toBe(false);
    const at = result.current.cursor;
    expect(at).toBe(4);
    act(() => { vi.advanceTimersByTime(500); });
    expect(result.current.cursor).toBe(at);
    expect(result.current.playing).toBe(false);
  });

  it("play jumps to the end under prefers-reduced-motion", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce") }));
    const { result } = renderHook(() => useReplay(5, { ...opts, auto: false }));
    act(() => { result.current.play(); });
    expect(result.current.cursor).toBe(4);
    expect(result.current.playing).toBe(false);
  });

  it("clears the timer on unmount", () => {
    const { unmount } = renderHook(() => useReplay(5, opts));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
