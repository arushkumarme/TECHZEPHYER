import { useCallback, useRef, useState } from "react";
import type { BlastRadius } from "../api";

/**
 * The blast radius of the most recently clicked switch. Responses to earlier clicks that
 * arrive late are ignored, and a failed request is remembered per device so its popover
 * can say the reach is unavailable instead of waiting forever.
 */
export function useLatestBlast(fetchBlast: (id: string) => Promise<BlastRadius>): {
  blast: BlastRadius | null;
  /** The device whose latest request failed, if any. */
  failed: string | null;
  request(id: string): void;
  reset(): void;
} {
  const [blast, setBlast] = useState<BlastRadius | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const latest = useRef<{ id: string; n: number } | null>(null);
  const fetchRef = useRef(fetchBlast);
  fetchRef.current = fetchBlast;

  const request = useCallback((id: string) => {
    const ticket = { id, n: (latest.current?.n ?? 0) + 1 };
    latest.current = ticket;
    setFailed(null);
    fetchRef.current(id).then(
      (b) => { if (latest.current === ticket) setBlast(b); },
      () => { if (latest.current === ticket) setFailed(id); },
    );
  }, []);

  const reset = useCallback(() => {
    latest.current = null;
    setBlast(null);
    setFailed(null);
  }, []);

  return { blast, failed, request, reset };
}
