"use client";

import { useMemo } from "react";

import type { AgentGraph as Graph } from "@/lib/api/agents";
import { cn } from "@/lib/utils";

const TYPE_COLOR: Record<string, string> = {
  planner: "#4f46e5", start: "#4f46e5", agent: "#2563eb", tool: "#059669",
  result: "#7c3aed", final: "#7c3aed", produce: "#2563eb", handoff: "#0891b2",
  review: "#d97706", vote: "#db2777", debate: "#dc2626", consensus: "#0d9488", merge: "#7c3aed",
};

interface Placed { id: string; type: string; label: string; x: number; y: number; }

/** Layered left-to-right graph (BFS depth from roots). Small execution graphs. */
export function AgentGraph({ graph, className }: { graph: Graph; className?: string }) {
  const { placed, edges, width, height } = useMemo(() => layout(graph), [graph]);
  const byId = useMemo(() => new Map(placed.map((p) => [p.id, p])), [placed]);

  if (!graph.nodes.length) return null;
  return (
    <div className={cn("overflow-x-auto", className)}>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ minWidth: Math.min(width, 700) }}
        role="img" aria-label="Execution graph">
        {edges.map((e, i) => {
          const a = byId.get(e.source);
          const b = byId.get(e.target);
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          return (
            <path key={i} d={`M ${a.x + 42} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x - 42} ${b.y}`}
              fill="none" stroke="#cbd5e1" strokeWidth={1.2} />
          );
        })}
        {placed.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`}>
            <rect x={-42} y={-16} width={84} height={32} rx={8}
              fill="#fff" stroke={TYPE_COLOR[n.type] ?? "#94a3b8"} strokeWidth={1.5} />
            <circle cx={-30} cy={0} r={4} fill={TYPE_COLOR[n.type] ?? "#94a3b8"} />
            <text x={-22} y={4} className="fill-slate-700 text-[9px]">{shorten(n.label)}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function shorten(s: string): string {
  const t = s.replace(/_agent$/, "").replace(/_/g, " ");
  return t.length > 13 ? t.slice(0, 12) + "…" : t;
}

function layout(graph: Graph): { placed: Placed[]; edges: Graph["edges"]; width: number; height: number } {
  const incoming = new Map<string, number>();
  graph.nodes.forEach((n) => incoming.set(n.id, 0));
  graph.edges.forEach((e) => incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1));

  // Longest-path layering from roots.
  const depth = new Map<string, number>();
  const adj = new Map<string, string[]>();
  graph.edges.forEach((e) => adj.set(e.source, [...(adj.get(e.source) ?? []), e.target]));
  const queue = graph.nodes.filter((n) => (incoming.get(n.id) ?? 0) === 0).map((n) => n.id);
  queue.forEach((id) => depth.set(id, 0));
  let head = 0;
  const guard = graph.nodes.length * 4;
  let steps = 0;
  while (head < queue.length && steps++ < guard) {
    const id = queue[head++];
    const d = depth.get(id) ?? 0;
    for (const nxt of adj.get(id) ?? []) {
      if ((depth.get(nxt) ?? -1) < d + 1) {
        depth.set(nxt, d + 1);
        queue.push(nxt);
      }
    }
  }
  graph.nodes.forEach((n) => { if (!depth.has(n.id)) depth.set(n.id, 0); });

  const layers = new Map<number, string[]>();
  graph.nodes.forEach((n) => {
    const d = depth.get(n.id) ?? 0;
    layers.set(d, [...(layers.get(d) ?? []), n.id]);
  });

  const colW = 150;
  const rowH = 46;
  const maxLayer = Math.max(...[...layers.keys()], 0);
  const maxRows = Math.max(...[...layers.values()].map((v) => v.length), 1);
  const placed: Placed[] = [];
  const label = new Map(graph.nodes.map((n) => [n.id, { type: n.type, label: n.label }]));
  [...layers.entries()].forEach(([d, ids]) => {
    ids.forEach((id, i) => {
      const meta = label.get(id)!;
      placed.push({ id, type: meta.type, label: meta.label,
        x: 60 + d * colW, y: 30 + (i + (maxRows - ids.length) / 2) * rowH });
    });
  });
  return { placed, edges: graph.edges, width: 120 + maxLayer * colW, height: 60 + maxRows * rowH };
}
