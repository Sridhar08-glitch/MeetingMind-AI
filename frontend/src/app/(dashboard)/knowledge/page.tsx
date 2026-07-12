"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  AlertTriangle, BrainCircuit, Clock, FileText, GitBranch, History, Lightbulb, MessageSquare,
  RefreshCw, Search, Sparkles, TrendingUp,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState, Spinner, SkeletonGrid, SkeletonList } from "@/components/ui/Feedback";
import { Markdown } from "@/components/ui/Markdown";
import { knowledgeApi, type ChatAnswer, type ChatSource, type SearchResult } from "@/lib/api/knowledge";
import { executiveApi } from "@/lib/api/executive";
import { cn } from "@/lib/utils";

type Tab = "search" | "chat" | "insights" | "recommendations" | "brief" | "timeline" | "timetravel" | "versions";

const TABS: { id: Tab; label: string; icon: typeof Search }[] = [
  { id: "search", label: "Org Search", icon: Search },
  { id: "chat", label: "Ask the Org", icon: MessageSquare },
  { id: "insights", label: "Insights", icon: TrendingUp },
  { id: "recommendations", label: "Recommendations", icon: Lightbulb },
  { id: "brief", label: "Executive Brief", icon: FileText },
  { id: "timeline", label: "Timeline", icon: Clock },
  { id: "timetravel", label: "Time Travel", icon: History },
  { id: "versions", label: "Versions", icon: GitBranch },
];

export default function KnowledgeHubPage() {
  const [tab, setTab] = useState<Tab>("search");
  const qc = useQueryClient();
  const stats = useQuery({ queryKey: ["knowledge", "stats"], queryFn: () => knowledgeApi.stats() });

  const reindex = useMutation({
    mutationFn: () => knowledgeApi.reindex(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
            <BrainCircuit className="h-6 w-6 text-brand-500" /> Knowledge Hub
          </h1>
          <p className="mt-1 text-sm text-muted">
            Organization-wide intelligence across every meeting, project and decision — always evidence-based.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => reindex.mutate()} isLoading={reindex.isPending}>
          <RefreshCw className="mr-1.5 h-4 w-4" /> Re-index
        </Button>
      </div>

      <Freshness s={stats.data} />

      <div className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === id
                ? "border-brand-500 text-brand-600"
                : "border-transparent text-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "search" && <SearchTab />}
      {tab === "chat" && <ChatTab />}
      {tab === "insights" && <InsightsTab />}
      {tab === "recommendations" && <RecommendationsTab />}
      {tab === "brief" && <BriefTab />}
      {tab === "timeline" && <TimelineTab />}
      {tab === "timetravel" && <TimeTravelTab />}
      {tab === "versions" && <VersionsTab />}
    </div>
  );
}

// ---- Timeline (11A) --------------------------------------------------------

function TimelineTab() {
  const [topic, setTopic] = useState("");
  const [submitted, setSubmitted] = useState("");
  const q = useQuery({
    queryKey: ["knowledge", "timeline", submitted],
    queryFn: () => executiveApi.timeline(submitted),
    enabled: submitted.length > 0,
  });

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setSubmitted(topic.trim()); }} className="flex gap-2">
        <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Watch a topic evolve — e.g. authentication" />
        <Button type="submit">Trace</Button>
      </form>
      {q.isFetching && <Spinner />}
      {q.data && (
        <div className="space-y-4">
          <p className="text-sm text-muted">
            <span className="font-medium text-foreground">{q.data.total_mentions}</span> mentions of &ldquo;{q.data.topic}&rdquo; over time.
          </p>
          {q.data.periods.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Mentions over time</CardTitle></CardHeader>
              <CardBody className="flex items-end gap-1.5">
                {q.data.periods.map((p, i) => {
                  const max = Math.max(...q.data!.periods.map((x) => x.count));
                  return (
                    <div key={i} className="flex flex-1 flex-col items-center gap-1">
                      <div className="w-full rounded-t bg-brand-400" style={{ height: `${Math.max(6, (p.count / max) * 120)}px` }} />
                      <span className="text-[10px] text-muted">{new Date(p.period).toLocaleDateString(undefined, { month: "short", year: "2-digit" })}</span>
                    </div>
                  );
                })}
              </CardBody>
            </Card>
          )}
          <div className="space-y-2">
            {q.data.milestones.map((m, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">{m.event}</span>
                <span className="flex-1 text-foreground">{m.title || m.entity_type}</span>
                <span className="text-xs text-muted">v{m.version} · {new Date(m.at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Time Travel (11A) -----------------------------------------------------

function TimeTravelTab() {
  const [date, setDate] = useState("");
  const [submitted, setSubmitted] = useState("");
  const q = useQuery({
    queryKey: ["knowledge", "timetravel", submitted],
    queryFn: () => executiveApi.timeTravel(submitted),
    enabled: submitted.length > 0,
  });

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); if (date) setSubmitted(date); }} className="flex gap-2">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
        />
        <Button type="submit">What did we know?</Button>
      </form>
      {q.isFetching && <Spinner />}
      {q.data && (
        <Card>
          <CardHeader><CardTitle>Knowledge as of {new Date(q.data.as_of).toLocaleDateString()}</CardTitle></CardHeader>
          <CardBody className="space-y-3">
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <span className="text-muted">Knowledge <span className="font-semibold text-foreground">v{q.data.knowledge_version}</span></span>
              <span className="text-muted">{q.data.items} items known</span>
              <span className="text-muted">{q.data.meetings} meetings</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(q.data.by_entity_type).map(([t, n]) => (
                <span key={t} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-foreground">{t}: {n}</span>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

// ---- Knowledge Versions (11A) ----------------------------------------------

function VersionsTab() {
  const q = useQuery({ queryKey: ["knowledge", "versions"], queryFn: () => executiveApi.versions() });
  if (q.isLoading) return <SkeletonGrid count={4} cols={2} />;
  if (!q.data || q.data.length === 0) {
    return <EmptyState title="No versions yet" description="Re-index your meetings to start versioning organizational knowledge." />;
  }
  return (
    <div className="space-y-2">
      {q.data.map((v) => (
        <Card key={v.version} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-sm">
          <span className="flex items-center gap-1.5 font-semibold text-foreground">
            <GitBranch className="h-4 w-4 text-brand-500" /> v{v.version}
          </span>
          <span className="text-muted">{new Date(v.indexed_at).toLocaleString()}</span>
          {v.embedding_version && <span className="text-xs text-muted">{v.embedding_version}</span>}
          <span className="ml-auto flex flex-wrap gap-x-3 text-xs text-muted">
            <span>{v.meetings} meetings</span><span>{v.decisions} decisions</span>
            <span>{v.risks} risks</span><span>{v.items} items</span>
          </span>
        </Card>
      ))}
    </div>
  );
}

function Freshness({ s }: { s?: { items_indexed: number; meetings_indexed: number; projects_included: number; last_updated: string | null } }) {
  if (!s) return null;
  return (
    <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3 text-sm">
      <span className="flex items-center gap-1.5 font-medium text-foreground">
        <Clock className="h-4 w-4 text-brand-500" /> Knowledge Freshness
      </span>
      <span className="text-muted">{s.items_indexed} items indexed</span>
      <span className="text-muted">{s.meetings_indexed} meetings</span>
      <span className="text-muted">{s.projects_included} projects</span>
      <span className="text-muted">
        Last updated: {s.last_updated ? new Date(s.last_updated).toLocaleString() : "never"}
      </span>
    </Card>
  );
}

// ---- Search ----------------------------------------------------------------

function SearchTab() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const results = useQuery({
    queryKey: ["knowledge", "search", submitted],
    queryFn: () => knowledgeApi.search(submitted),
    enabled: submitted.length > 0,
  });

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => { e.preventDefault(); setSubmitted(q.trim()); }}
        className="flex gap-2"
      >
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search across all meetings, decisions, tasks, risks…" />
        <Button type="submit">Search</Button>
      </form>

      {results.isFetching && <Spinner />}
      {results.data && results.data.results.length === 0 && (
        <EmptyState title="No matches" description="Nothing in your indexed knowledge matches that query." />
      )}
      <div className="space-y-2">
        {results.data?.results.map((r) => <ResultRow key={`${r.entity_type}-${r.entity_id}`} r={r} />)}
      </div>
    </div>
  );
}

function ResultRow({ r }: { r: SearchResult }) {
  return (
    <Card className="px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">{r.entity_type}</span>
        <span className="text-xs text-muted">{r.confidence}% match</span>
      </div>
      <p className="mt-1.5 text-sm text-foreground">{r.snippet}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {r.meeting_id && (
          <Link href={`/meetings/${r.meeting_id}`} className="font-medium text-brand-600 hover:underline">
            {r.meeting_title ?? "Meeting"}
          </Link>
        )}
        {r.speaker && <span>{r.speaker}</span>}
        {r.timestamp != null && <span>@ {Math.round(r.timestamp)}s</span>}
        <span>{new Date(r.occurred_at).toLocaleDateString()}</span>
      </div>
    </Card>
  );
}

// ---- Chat ------------------------------------------------------------------

function ChatTab() {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<ChatAnswer | null>(null);
  const ask = useMutation({
    mutationFn: (question: string) => knowledgeApi.chat(question),
    onSuccess: setAnswer,
  });

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask.mutate(q.trim()); }}
        className="flex gap-2"
      >
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything across all your meetings…" />
        <Button type="submit" isLoading={ask.isPending}>Ask</Button>
      </form>

      {ask.isPending && <Spinner />}
      {answer && (
        <Card>
          <CardBody className="space-y-4">
            <p className="whitespace-pre-wrap text-sm text-foreground">{answer.answer}</p>
            {answer.sources.length > 0 && (
              <div className="space-y-2 border-t border-border pt-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                  <Sparkles className="h-3.5 w-3.5" /> Sources
                </p>
                {answer.sources.map((s, i) => <SourceRow key={i} s={s} />)}
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function SourceRow({ s }: { s: ChatSource }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <div className="flex items-center justify-between gap-2 text-xs">
        {s.meeting_id ? (
          <Link href={`/meetings/${s.meeting_id}`} className="font-medium text-brand-600 hover:underline">
            {s.meeting_title ?? "Meeting"}
          </Link>
        ) : (
          <span className="font-medium text-foreground">{s.entity_type}</span>
        )}
        <span className="text-muted">{s.confidence}%</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        {s.speaker && <span className="font-medium">{s.speaker}: </span>}
        &ldquo;{s.quote}&rdquo;
        {s.timestamp != null && <span className="ml-1">(@ {Math.round(s.timestamp)}s)</span>}
      </p>
    </div>
  );
}

// ---- Insights --------------------------------------------------------------

function InsightsTab() {
  const q = useQuery({ queryKey: ["knowledge", "insights"], queryFn: () => knowledgeApi.insights() });
  if (q.isLoading) return <SkeletonList rows={4} />;
  const ins = q.data;
  if (!ins) return null;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Top topics</CardTitle></CardHeader>
        <CardBody className="flex flex-wrap gap-2">
          {ins.top_topics.length === 0 && <span className="text-sm text-muted">No topics yet.</span>}
          {ins.top_topics.map((t) => (
            <span key={t.label} className="rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-700">
              {t.label} · {t.meetings} mtg
            </span>
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>Recurring risks</CardTitle></CardHeader>
        <CardBody className="space-y-2">
          {ins.recurring_risks.length === 0 && <span className="text-sm text-muted">None detected.</span>}
          {ins.recurring_risks.map((r) => (
            <div key={r.topic} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 text-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-warning" /> {r.topic}
              </span>
              <span className="text-xs text-muted">{r.count}× · {r.severity}</span>
            </div>
          ))}
        </CardBody>
      </Card>

      <Card className="md:col-span-2">
        <CardHeader><CardTitle>Project health</CardTitle></CardHeader>
        <CardBody className="space-y-3">
          {ins.project_health.length === 0 && <span className="text-sm text-muted">No projects yet.</span>}
          {ins.project_health.map((p) => (
            <div key={p.project_id} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-foreground">{p.name}</span>
                <span className="text-xs text-muted">
                  {p.completed}/{p.tasks} tasks · {p.open_risks} risks · {p.meetings} meetings
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.round(p.completion_rate * 100)}%` }} />
              </div>
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

// ---- Recommendations -------------------------------------------------------

const PRIORITY_STYLE: Record<string, string> = {
  high: "border-l-danger", medium: "border-l-warning", low: "border-l-brand-400",
};

function RecommendationsTab() {
  const q = useQuery({ queryKey: ["knowledge", "recommendations"], queryFn: () => knowledgeApi.recommendations() });
  if (q.isLoading) return <SkeletonList rows={5} />;
  if (!q.data || q.data.length === 0) {
    return <EmptyState title="All clear" description="No recommendations right now — nothing needs attention." />;
  }
  return (
    <div className="space-y-3">
      {q.data.map((r, i) => (
        <Card key={i} className={cn("border-l-4 px-4 py-3", PRIORITY_STYLE[r.priority] ?? "border-l-slate-300")}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-foreground">{r.title}</span>
            <span className="text-xs uppercase tracking-wide text-muted">{r.priority}</span>
          </div>
          <p className="mt-1 text-sm text-muted">{r.detail}</p>
        </Card>
      ))}
    </div>
  );
}

// ---- Executive Brief -------------------------------------------------------

function BriefTab() {
  const [period, setPeriod] = useState<"daily" | "weekly" | "monthly">("weekly");
  const q = useQuery({ queryKey: ["knowledge", "brief", period], queryFn: () => knowledgeApi.brief(period) });

  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {(["daily", "weekly", "monthly"] as const).map((p) => (
          <Button key={p} size="sm" variant={period === p ? "primary" : "outline"} onClick={() => setPeriod(p)}>
            {p[0].toUpperCase() + p.slice(1)}
          </Button>
        ))}
      </div>
      {q.isLoading && <Spinner />}
      {q.data && (
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>{period[0].toUpperCase() + period.slice(1)} Executive Brief</CardTitle>
            <span className="text-xs text-muted">
              {q.data.provider === "fallback" ? "Generated locally" : `${q.data.provider} · ${q.data.model}`}
            </span>
          </CardHeader>
          <CardBody>
            <Markdown>{q.data.brief}</Markdown>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
