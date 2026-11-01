/** Link ids along a BFS shortest path; ties broken by link id order. [] if from === to or unreachable. */
export function shortestPath(
  links: { id: string; a: string; b: string }[],
  from: string,
  to: string,
): string[] {
  if (from === to) return [];
  const sorted = [...links].sort((x, y) => x.id.localeCompare(y.id, "en", { numeric: true }));
  const adj = new Map<string, { to: string; id: string }[]>();
  const add = (n: string, e: { to: string; id: string }) => adj.set(n, [...(adj.get(n) ?? []), e]);
  for (const l of sorted) {
    add(l.a, { to: l.b, id: l.id });
    add(l.b, { to: l.a, id: l.id });
  }
  const prev = new Map<string, { node: string; id: string }>();
  const seen = new Set([from]);
  const queue = [from];
  while (queue.length) {
    const cur = queue.shift() as string;
    for (const e of adj.get(cur) ?? []) {
      if (seen.has(e.to)) continue;
      seen.add(e.to);
      prev.set(e.to, { node: cur, id: e.id });
      if (e.to === to) {
        const path: string[] = [];
        for (let n = to; n !== from; ) {
          const p = prev.get(n) as { node: string; id: string };
          path.unshift(p.id);
          n = p.node;
        }
        return path;
      }
      queue.push(e.to);
    }
  }
  return [];
}
