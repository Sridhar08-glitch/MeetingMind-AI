"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Maximize2, Minus, Network, Plus, RotateCcw, Search } from "lucide-react";

import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner, EmptyState } from "@/components/ui/Feedback";
import { executiveApi, type GraphNode, type KGraph } from "@/lib/api/executive";

const RING_FOR_TYPE: Record<string, number> = {
  project: 0, meeting: 1, person: 2,
  task: 3, decision: 3, risk: 3, issue: 3, report: 3, segment: 3,
};
const RING_RADIUS = [80, 170, 260, 350];
const TYPE_COLOR: Record<string, string> = {
  project: "#7c3aed", meeting: "#2563eb", person: "#0891b2",
  task: "#059669", decision: "#d97706", risk: "#dc2626", issue: "#db2777",
  report: "#4b5563", segment: "#94a3b8",
};
const SIZE = 820;
const CENTER = SIZE / 2;
const MAX_NODES = 90;

interface Positioned extends GraphNode { x: number; y: number; }
interface ViewTransform { scale: number; tx: number; ty: number; }
const IDENTITY: ViewTransform = { scale: 1, tx: 0, ty: 0 };

function layout(graph: KGraph): { nodes: Positioned[]; edges: { source: string; target: string }[] } {
  const nodes = graph.nodes.slice(0, MAX_NODES);
  const ids = new Set(nodes.map((n) => n.id));
  const byRing: Record<number, GraphNode[]> = { 0: [], 1: [], 2: [], 3: [] };
  for (const n of nodes) byRing[RING_FOR_TYPE[n.type] ?? 3].push(n);

  const positioned: Positioned[] = [];
  for (const ringStr of Object.keys(byRing)) {
    const ring = Number(ringStr);
    const group = byRing[ring];
    group.forEach((n, i) => {
      if (ring === 0 && group.length === 1) {
        positioned.push({ ...n, x: CENTER, y: CENTER });
        return;
      }
      const angle = (2 * Math.PI * i) / Math.max(group.length, 1) - Math.PI / 2;
      positioned.push({
        ...n,
        x: CENTER + RING_RADIUS[ring] * Math.cos(angle),
        y: CENTER + RING_RADIUS[ring] * Math.sin(angle),
      });
    });
  }
  const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  return { nodes: positioned, edges };
}

export default function KnowledgeGraphPage() {
  const [mode, setMode] = useState<"people" | "knowledge">("people");
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewTransform>(IDENTITY);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);

  const q = useQuery({
    queryKey: ["graph", mode],
    queryFn: () => (mode === "people" ? executiveApi.peopleGraph() : executiveApi.knowledgeGraph()),
  });

  const { nodes, edges } = useMemo(() => (q.data ? layout(q.data) : { nodes: [], edges: [] }), [q.data]);
  const posById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const neighbors = useMemo(() => {
    if (!selected) return new Set<string>();
    const s = new Set<string>([selected]);
    for (const e of edges) {
      if (e.source === selected) s.add(e.target);
      if (e.target === selected) s.add(e.source);
    }
    return s;
  }, [selected, edges]);

  const matches = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return null;
    return new Set(nodes.filter((n) => n.label.toLowerCase().includes(term)).map((n) => n.id));
  }, [search, nodes]);

  const selectedNode = selected ? posById.get(selected) : null;

  const switchMode = (m: "people" | "knowledge") => { setMode(m); setView(IDENTITY); setSelected(null); };

  // Wheel-to-zoom (native non-passive listener so we can preventDefault).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const px = ((e.clientX - rect.left) / rect.width) * SIZE;
      const py = ((e.clientY - rect.top) / rect.height) * SIZE;
      setView((v) => {
        const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const scale = Math.min(4, Math.max(0.4, v.scale * factor));
        // Keep the point under the cursor stationary.
        const k = scale / v.scale;
        return { scale, tx: px - (px - v.tx) * k, ty: py - (py - v.ty) * k };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [nodes.length]);

  const zoomBy = (factor: number) =>
    setView((v) => {
      const scale = Math.min(4, Math.max(0.4, v.scale * factor));
      const k = scale / v.scale;
      return { scale, tx: CENTER - (CENTER - v.tx) * k, ty: CENTER - (CENTER - v.ty) * k };
    });

  const fit = () => {
    if (!nodes.length) return setView(IDENTITY);
    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs) - 40, maxX = Math.max(...xs) + 40;
    const minY = Math.min(...ys) - 40, maxY = Math.max(...ys) + 40;
    const w = maxX - minX, h = maxY - minY;
    const scale = Math.min(4, Math.max(0.4, Math.min(SIZE / w, SIZE / h)));
    setView({ scale, tx: (SIZE - (minX + maxX) * scale) / 2, ty: (SIZE - (minY + maxY) * scale) / 2 });
  };

  const svgPoint = (clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: ((clientX - rect.left) / rect.width) * SIZE, y: ((clientY - rect.top) / rect.height) * SIZE };
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
            <Network className="h-6 w-6 text-brand-500" /> Knowledge Graph
          </h1>
          <p className="mt-1 text-sm text-muted">
            Navigate how people, meetings, decisions, tasks, risks and projects connect. Scroll to zoom, drag to pan.
          </p>
        </div>
        <div className="flex gap-1">
          <Button size="sm" variant={mode === "people" ? "primary" : "outline"} onClick={() => switchMode("people")}>People</Button>
          <Button size="sm" variant={mode === "knowledge" ? "primary" : "outline"} onClick={() => switchMode("knowledge")}>Knowledge</Button>
        </div>
      </div>

      {q.isLoading && <Spinner />}
      {q.data && nodes.length === 0 && (
        <EmptyState title="No graph yet" description="Upload and process meetings to build the knowledge graph." />
      )}

      {nodes.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
          <Card className="relative overflow-hidden">
            {/* Controls */}
            <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search nodes…"
                  className="h-8 w-44 pl-7 text-xs"
                  aria-label="Search graph nodes"
                />
              </div>
            </div>
            <div className="absolute right-3 top-3 z-10 flex flex-col gap-1">
              <IconBtn label="Zoom in" onClick={() => zoomBy(1.2)}><Plus className="h-4 w-4" /></IconBtn>
              <IconBtn label="Zoom out" onClick={() => zoomBy(1 / 1.2)}><Minus className="h-4 w-4" /></IconBtn>
              <IconBtn label="Fit to screen" onClick={fit}><Maximize2 className="h-4 w-4" /></IconBtn>
              <IconBtn label="Reset view" onClick={() => setView(IDENTITY)}><RotateCcw className="h-4 w-4" /></IconBtn>
            </div>

            <svg
              ref={svgRef}
              viewBox={`0 0 ${SIZE} ${SIZE}`}
              className="w-full touch-none select-none cursor-grab active:cursor-grabbing"
              role="img"
              aria-label="Knowledge graph"
              onPointerDown={(e) => {
                const p = svgPoint(e.clientX, e.clientY);
                drag.current = { x: p.x, y: p.y, tx: view.tx, ty: view.ty };
                (e.target as Element).setPointerCapture?.(e.pointerId);
              }}
              onPointerMove={(e) => {
                if (!drag.current) return;
                const p = svgPoint(e.clientX, e.clientY);
                setView((v) => ({ ...v, tx: drag.current!.tx + (p.x - drag.current!.x), ty: drag.current!.ty + (p.y - drag.current!.y) }));
              }}
              onPointerUp={() => { drag.current = null; }}
              onPointerLeave={() => { drag.current = null; }}
            >
              <g transform={`translate(${view.tx},${view.ty}) scale(${view.scale})`}>
                {edges.map((e, i) => {
                  const a = posById.get(e.source);
                  const b = posById.get(e.target);
                  if (!a || !b) return null;
                  const active = selected != null && (e.source === selected || e.target === selected);
                  return (
                    <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke={active ? "#6366f1" : "#e2e8f0"} strokeWidth={active ? 1.8 : 0.8} />
                  );
                })}
                {nodes.map((n) => {
                  const dimmed = (selected != null && !neighbors.has(n.id)) || (matches != null && !matches.has(n.id));
                  const isSel = n.id === selected;
                  const isMatch = matches?.has(n.id);
                  return (
                    <g key={n.id} transform={`translate(${n.x},${n.y})`}
                       onClick={(e) => { e.stopPropagation(); setSelected(isSel ? null : n.id); }}
                       className="cursor-pointer" opacity={dimmed ? 0.2 : 1}>
                      {isMatch && <circle r={11} fill="none" stroke="#f59e0b" strokeWidth={2} />}
                      <circle r={isSel ? 9 : 6} fill={TYPE_COLOR[n.type] ?? "#94a3b8"} stroke="#fff" strokeWidth={1.5} />
                      {(isSel || isMatch || n.type === "person" || n.type === "project") && (
                        <text x={10} y={4} className="fill-slate-600 text-[10px]" style={{ pointerEvents: "none" }}>{n.label.slice(0, 22)}</text>
                      )}
                    </g>
                  );
                })}
              </g>
            </svg>
            <div className="absolute bottom-2 right-3 text-[10px] text-muted">{Math.round(view.scale * 100)}%</div>
          </Card>

          <div className="space-y-4">
            <Card>
              <CardBody className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">Legend</p>
                {Object.entries(TYPE_COLOR).filter(([t]) => nodes.some((n) => n.type === t)).map(([t, c]) => (
                  <div key={t} className="flex items-center gap-2 text-sm capitalize text-foreground">
                    <span className="h-3 w-3 rounded-full" style={{ background: c }} /> {t}
                  </div>
                ))}
              </CardBody>
            </Card>

            {selectedNode && (
              <Card className="animate-fade-up">
                <CardBody className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted capitalize">{selectedNode.type}</p>
                  <p className="text-sm font-medium text-foreground">{selectedNode.label}</p>
                  {selectedNode.type === "meeting" && selectedNode.ref && (
                    <Link href={`/meetings/${selectedNode.ref}`} className="text-xs font-medium text-brand-600 hover:underline">
                      Open meeting →
                    </Link>
                  )}
                  <p className="text-xs text-muted">{neighbors.size - 1} connected node(s)</p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {[...neighbors].filter((id) => id !== selected).slice(0, 12).map((id) => {
                      const nb = posById.get(id);
                      if (!nb) return null;
                      return (
                        <button key={id} onClick={() => setSelected(id)}
                          className="rounded-full px-2 py-0.5 text-[11px] text-white"
                          style={{ background: TYPE_COLOR[nb.type] ?? "#94a3b8" }}>
                          {nb.label.slice(0, 18)}
                        </button>
                      );
                    })}
                  </div>
                </CardBody>
              </Card>
            )}
            {!selectedNode && <p className="px-1 text-xs text-muted">Click any node to explore its connections.</p>}
            {q.data?.counts && (
              <p className="px-1 text-xs text-muted">
                {q.data.counts.people ?? 0} people · {nodes.length} nodes · {edges.length} links
                {matches != null && ` · ${matches.size} match${matches.size === 1 ? "" : "es"}`}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} aria-label={label} title={label}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-muted shadow-sm hover:bg-slate-50 hover:text-foreground">
      {children}
    </button>
  );
}
