import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BlastRadius } from "../api";
import { useLatestBlast } from "./blast";

const reach = (failed: string): BlastRadius =>
  ({ failed, isolated: [], degraded: [], unaffected: [], unknown: [] }) as unknown as BlastRadius;

/** A fetcher whose responses the test resolves or rejects by hand, in any order. */
function manual() {
  const pending = new Map<string, { resolve: (b: BlastRadius) => void; reject: (e: Error) => void }>();
  const fetch = (id: string) => new Promise<BlastRadius>((resolve, reject) => { pending.set(id, { resolve, reject }); });
  return { fetch, pending };
}

describe("useLatestBlast", () => {
  it("ignores a response that arrives after a newer request", async () => {
    const m = manual();
    const { result } = renderHook(() => useLatestBlast(m.fetch));
    act(() => { result.current.request("SW_CAMPUS_4"); });
    act(() => { result.current.request("SW_CAMPUS_5"); });
    await act(async () => { m.pending.get("SW_CAMPUS_5")!.resolve(reach("SW_CAMPUS_5")); });
    await act(async () => { m.pending.get("SW_CAMPUS_4")!.resolve(reach("SW_CAMPUS_4")); });
    expect(result.current.blast?.failed).toBe("SW_CAMPUS_5");
  });

  it("marks the latest device unavailable on failure, and ignores stale failures", async () => {
    const m = manual();
    const { result } = renderHook(() => useLatestBlast(m.fetch));
    act(() => { result.current.request("SW_CAMPUS_4"); });
    await act(async () => { m.pending.get("SW_CAMPUS_4")!.reject(new Error("boom")); });
    expect(result.current.failed).toBe("SW_CAMPUS_4");

    act(() => { result.current.request("SW_CAMPUS_6"); });
    expect(result.current.failed).toBeNull();
    act(() => { result.current.request("SW_CAMPUS_7"); });
    await act(async () => { m.pending.get("SW_CAMPUS_6")!.reject(new Error("late")); });
    expect(result.current.failed).toBeNull();
    await act(async () => { m.pending.get("SW_CAMPUS_7")!.resolve(reach("SW_CAMPUS_7")); });
    expect(result.current.blast?.failed).toBe("SW_CAMPUS_7");
  });

  it("reset drops the current reach and any pending response", async () => {
    const m = manual();
    const { result } = renderHook(() => useLatestBlast(m.fetch));
    act(() => { result.current.request("SW_CAMPUS_4"); });
    act(() => { result.current.reset(); });
    await act(async () => { m.pending.get("SW_CAMPUS_4")!.resolve(reach("SW_CAMPUS_4")); });
    expect(result.current.blast).toBeNull();
  });
});
