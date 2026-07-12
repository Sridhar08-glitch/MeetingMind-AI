"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  Activity, BarChart3, Copy, FileText, Gauge, Lightbulb, RefreshCw, TriangleAlert, Wand2,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner, EmptyState, SkeletonGrid, ErrorState } from "@/components/ui/Feedback";
import { Markdown } from "@/components/ui/Markdown";
import { ExplainButton } from "@/components/copilot/ExplainButton";
import { executiveApi, type ExecAlert, type ExecRecommendation } from "@/lib/api/executive";
import { cn } from "@/lib/utils";

type View = "overview" | "recommendations" | "alerts" | "insights" | "brief";

const TABS: { id: View; label: string; icon: typeof Gauge }[] = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "recommendations", label: "Recommendations", icon: Lightbulb },
  { id: "alerts", label: "Alerts", icon: TriangleAlert },
  { id: "insights", label: "Insights", icon: BarChart3 },
  { id: "brief", label: "Brief", icon: FileText },
];

const HEALTH_ORDER = ["project", "meeting", "knowledge", "task", "decision", "risk", "ai"];

function statusColor(status: string): string {
  if (status === "excellent" || status === "good") return "text-success";
  if (status === "warning") return "text-warning";
  return "text-danger";
}
function statusBg(status: string): string {
  if (status === "excellent" || status === "good") return "bg-success";
  if (status === "warning") return "bg-warning";
  return "bg-danger";
}

export default function ExecutivePage() {
  const params = useSearchParams();
  const initial = (params.get("view") as View) || "overview";
  const [view, setView] = useState<View>(TABS.some((t) => t.id === initial) ? initial : "overview");
  const qc = useQueryClient();

  const dash = useQuery({ queryKey: ["exec", "dashboard"], queryFn: () => executiveApi.dashboard() });
  const refresh = useMutation({
    mutationFn: () => executiveApi.refresh(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exec"] }),
  });

  const d = dash.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
            <BarChart3 className="h-6 w-6 text-brand-500" /> Executive Dashboard
          </h1>
          <p className="mt-1 text-sm text-muted">
            Workspace health, knowledge, trends and risks — every metric explainable and versioned.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {d && (
            <span className="hidden text-xs text-muted sm:block">
              Snapshot v{d.snapshot_version} · Knowledge v{d.knowledge_version}
              {d.stale && <span className="ml-1 rounded bg-warning/15 px-1.5 py-0.5 text-warning">stale</span>}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => refresh.mutate()} isLoading={refresh.isPending}>
            <RefreshCw className="mr-1.5 h-4 w-4" /> Refresh
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={cn(
              "flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              view === id ? "border-brand-500 text-brand-600" : "border-transparent text-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {dash.isLoading && <SkeletonGrid count={6} />}
      {dash.isError && <ErrorState title="Couldn't load the dashboard" onRetry={() => dash.refetch()} />}
      {d && view === "overview" && <Overview d={d} />}
      {d && view === "recommendations" && <Recommendations recs={d.recommendations} />}
      {d && view === "alerts" && <Alerts alerts={d.alerts} />}
      {d && view === "insights" && <Insights d={d} />}
      {view === "brief" && <Brief />}
    </div>
  );
}

function Overview({ d }: { d: NonNullable<Awaited<ReturnType<typeof executiveApi.dashboard>>> }) {
  const overall = d.health.overall;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1">
          <CardBody className="flex flex-col items-center justify-center py-8 text-center">
            <p className="text-sm font-medium text-muted">Workspace Score</p>
            <p className={cn("mt-1 text-5xl font-bold", statusColor(d.score.status))}>{Math.round(d.score.score)}</p>
            <p className="text-xs text-muted">out of 100 · {d.score.status}</p>
            <p className={cn("mt-3 text-sm font-medium capitalize", statusColor(overall.status))}>
              Health: {overall.status}
            </p>
          </CardBody>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader><CardTitle>Score breakdown</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            {Object.entries(d.score.breakdown).map(([key, part]) => (
              <div key={key} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="capitalize text-foreground">{key.replace(/_/g, " ")}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted">{Math.round(part.score)}</span>
                    <ExplainButton metric={`score.${key}`} />
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.round(part.score)}%` }} />
                </div>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Workspace Health</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {HEALTH_ORDER.map((key) => {
            const dim = d.health.dimensions[key];
            if (!dim) return null;
            return (
              <Card key={key}>
                <CardBody className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className={cn("h-2 w-2 rounded-full", statusBg(dim.status))} />
                    <ExplainButton metric={`health.${key}`} />
                  </div>
                  <p className={cn("text-2xl font-bold", statusColor(dim.status))}>{Math.round(dim.score)}</p>
                  <p className="text-xs capitalize text-muted">{key} health</p>
                </CardBody>
              </Card>
            );
          })}
        </div>
      </div>

      {d.predictions.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4" /> Predictive Health</CardTitle></CardHeader>
          <CardBody className="space-y-2">
            {d.predictions.map((p, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-foreground">
                <Wand2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                <span>{p.message}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

const PRIORITY_STYLE: Record<string, string> = {
  high: "border-l-danger", medium: "border-l-warning", low: "border-l-brand-400",
};

function Recommendations({ recs }: { recs: ExecRecommendation[] }) {
  const qc = useQueryClient();
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => executiveApi.setRecommendationStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exec"] }),
  });

  if (recs.length === 0) return <EmptyState title="All clear" description="No recommendations right now." />;
  return (
    <div className="space-y-3">
      {recs.map((r) => (
        <Card key={r.id} className={cn("border-l-4 px-4 py-3", PRIORITY_STYLE[r.priority] ?? "border-l-slate-300")}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-foreground">{r.recommendation}</span>
            <span className="text-xs text-muted">{Math.round(r.confidence)}% confidence</span>
          </div>
          <p className="mt-1 text-sm text-muted">{r.reason}</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            {Object.entries(r.impact).filter(([, v]) => v > 0).map(([k, v]) => (
              <span key={k}>{v} {k.replace(/supporting_/, "")}</span>
            ))}
            {r.consensus && "position" in (r.consensus as Record<string, unknown>) && (
              <span className="rounded bg-brand-50 px-1.5 py-0.5 text-brand-700">
                consensus: {String((r.consensus as Record<string, unknown>).position).slice(0, 40)}
              </span>
            )}
          </div>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setStatus.mutate({ id: r.id, status: "acknowledged" })}>Acknowledge</Button>
            <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: r.id, status: "done" })}>Mark done</Button>
            <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: r.id, status: "dismissed" })}>Dismiss</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-l-danger", warning: "border-l-warning", info: "border-l-brand-400",
};

function Alerts({ alerts }: { alerts: ExecAlert[] }) {
  const qc = useQueryClient();
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => executiveApi.setAlertStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exec"] }),
  });

  if (alerts.length === 0) return <EmptyState title="No open alerts" description="Nothing needs your attention." />;
  return (
    <div className="space-y-3">
      {alerts.map((a) => (
        <Card key={a.id} className={cn("border-l-4 px-4 py-3", SEVERITY_STYLE[a.severity] ?? "border-l-slate-300")}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-foreground">{a.title}</span>
            <span className={cn("text-xs uppercase", statusColor(a.severity === "info" ? "good" : a.severity === "warning" ? "warning" : "critical"))}>{a.severity}</span>
          </div>
          <p className="mt-1 text-sm text-muted">{a.detail}</p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setStatus.mutate({ id: a.id, status: "acknowledged" })}>Acknowledge</Button>
            <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: a.id, status: "resolved" })}>Resolve</Button>
            <Button size="sm" variant="ghost" onClick={() => setStatus.mutate({ id: a.id, status: "dismissed" })}>Dismiss</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

function Insights({ d }: { d: NonNullable<Awaited<ReturnType<typeof executiveApi.dashboard>>> }) {
  const oi = d.organization_insights as Record<string, unknown>;
  const boards = d.analytics.leaderboards ?? {};
  const entries = Object.entries(oi).filter(([, v]) => v != null);
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map(([key, v]) => (
          <Card key={key}>
            <CardBody>
              <p className="text-xs uppercase tracking-wide text-muted">{key.replace(/_/g, " ")}</p>
              <p className="mt-1 text-sm font-medium text-foreground">{renderInsight(v)}</p>
            </CardBody>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {Object.entries(boards).map(([name, rows]) => (
          <Card key={name}>
            <CardHeader><CardTitle className="capitalize">{name.replace(/_/g, " ")}</CardTitle></CardHeader>
            <CardBody className="space-y-1.5">
              {rows.length === 0 && <span className="text-sm text-muted">No data yet.</span>}
              {rows.slice(0, 8).map((row, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-foreground">{row.name ?? row.label ?? "—"}</span>
                  <span className="text-xs text-muted">{row.count ?? row.meetings ?? ""}</span>
                </div>
              ))}
            </CardBody>
          </Card>
        ))}
      </div>
    </div>
  );
}

function renderInsight(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    return String(o.name ?? o.label ?? o.topic ?? JSON.stringify(o));
  }
  return String(v);
}

function Brief() {
  const [period, setPeriod] = useState<"today" | "week" | "month">("week");
  const q = useQuery({ queryKey: ["exec", "brief", period], queryFn: () => executiveApi.brief(period) });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex gap-1">
          {(["today", "week", "month"] as const).map((p) => (
            <Button key={p} size="sm" variant={period === p ? "primary" : "outline"} onClick={() => setPeriod(p)}>
              {p[0].toUpperCase() + p.slice(1)}
            </Button>
          ))}
        </div>
        {q.data && (
          <>
            <Button size="sm" variant="ghost" onClick={() => q.refetch()} isLoading={q.isFetching}>
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Regenerate
            </Button>
            <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(q.data.executive_summary)}>
              <Copy className="mr-1 h-3.5 w-3.5" /> Copy
            </Button>
          </>
        )}
      </div>

      {q.isLoading && <Spinner />}
      {q.data && (
        <Card>
          <CardHeader><CardTitle>{period[0].toUpperCase() + period.slice(1)} Executive Brief</CardTitle></CardHeader>
          <CardBody className="space-y-4">
            <Markdown>{q.data.executive_summary}</Markdown>
            <BriefSection title="Critical risks" items={q.data.critical_risks.map((r) => `${r.risk} (${r.severity})`)} />
            <BriefSection title="Important decisions" items={q.data.important_decisions.map((x) => x.decision)} />
            <BriefSection title="Upcoming deadlines" items={q.data.upcoming_deadlines.map((x) => `${x.title} — ${x.due_date}`)} />
            <BriefSection title="Top achievements" items={q.data.top_achievements.map((x) => x.title)} />
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function BriefSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="border-t border-border pt-3">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</p>
      <ul className="list-inside list-disc space-y-0.5 text-sm text-foreground">
        {items.slice(0, 8).map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </div>
  );
}
