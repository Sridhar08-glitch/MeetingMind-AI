"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle, ArrowRight, FileText, Gauge, Lightbulb, ListChecks, Sparkles, TrendingUp,
} from "lucide-react";

import { Card, CardBody } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Spinner, EmptyState } from "@/components/ui/Feedback";
import { executiveApi, type NLResult } from "@/lib/api/executive";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";

interface Suggestion {
  label: string;
  action: (ctx: { ask: (q: string) => void; go: (href: string) => void }) => void;
}

const SUGGESTIONS: Suggestion[] = [
  { label: "Generate Executive Brief", action: ({ go }) => go("/executive?view=brief") },
  { label: "Show overdue tasks", action: ({ ask }) => ask("overdue tasks") },
  { label: "Find Redis discussions", action: ({ ask }) => ask("Redis") },
  { label: "Compare ERP vs CRM", action: ({ ask }) => ask("compare ERP and CRM") },
  { label: "Prepare Sprint Report", action: ({ go }) => go("/executive?view=brief") },
  { label: "Show project health", action: ({ go }) => go("/executive") },
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

const STATUS_COLOR: Record<string, string> = {
  excellent: "text-success", good: "text-success", warning: "text-warning", critical: "text-danger",
};

export default function CopilotPage() {
  const router = useRouter();
  const params = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const firstName = (user?.full_name || user?.email || "there").split(/[ @]/)[0];

  const [q, setQ] = useState(() => params.get("q") ?? "");
  const [result, setResult] = useState<NLResult | null>(null);

  const dashboard = useQuery({ queryKey: ["exec", "dashboard"], queryFn: () => executiveApi.dashboard() });
  const changes = useQuery({ queryKey: ["exec", "whatChanged"], queryFn: () => executiveApi.whatChanged() });

  const ask = useMutation({
    mutationFn: (query: string) => executiveApi.nlQuery(query),
    onSuccess: setResult,
  });

  const runAsk = (query: string) => { setQ(query); ask.mutate(query); };
  const ctx = { ask: runAsk, go: (href: string) => router.push(href) };

  // Deep link from the command palette: /copilot?q=… (trigger the mutation only;
  // `q` was already initialised from the param above).
  useEffect(() => {
    const initial = params.get("q");
    if (initial) ask.mutate(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const d = dashboard.data;
  const newDecisions = (changes.data?.new_decisions as unknown[] | undefined)?.length ?? 0;
  const newRisks = (changes.data?.new_risks as unknown[] | undefined)?.length ?? 0;
  const blockedProjects = d?.project_health.filter((p) => p.status === "warning" || p.status === "critical").length ?? 0;

  const tiles = [
    { label: "Workspace Score", value: d ? Math.round(d.score.score) : "—", icon: Gauge, href: "/executive",
      accent: d ? STATUS_COLOR[d.score.status] ?? "text-foreground" : "text-foreground" },
    { label: "Recommendations", value: d?.recommendations.length ?? "—", icon: Lightbulb, href: "/executive?view=recommendations", accent: "text-brand-600" },
    { label: "Open Alerts", value: d?.alerts.length ?? "—", icon: AlertTriangle, href: "/executive?view=alerts", accent: "text-warning" },
    { label: "Blocked Projects", value: blockedProjects, icon: ListChecks, href: "/executive", accent: "text-danger" },
    { label: "New Decisions", value: newDecisions, icon: FileText, href: "/knowledge", accent: "text-foreground" },
    { label: "New Risks", value: newRisks, icon: TrendingUp, href: "/knowledge", accent: "text-foreground" },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          {greeting()}, {firstName}
        </h1>
        <p className="mt-1 text-sm text-muted">Here&apos;s your workspace at a glance — ask the Copilot anything.</p>
      </div>

      {/* Copilot input */}
      <Card className="border-brand-200 bg-gradient-to-br from-brand-50/60 to-surface">
        <CardBody className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-brand-700">
            <Sparkles className="h-5 w-5" /> MeetingMind AI Copilot
          </div>
          <form
            onSubmit={(e) => { e.preventDefault(); if (q.trim()) runAsk(q.trim()); }}
            className="flex gap-2"
          >
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="What would you like to do today?"
              className="h-12 flex-1 rounded-lg border border-border bg-surface px-4 text-sm text-foreground placeholder:text-muted focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
            <Button type="submit" size="lg" isLoading={ask.isPending}>
              Ask <ArrowRight className="h-4 w-4" />
            </Button>
          </form>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s.label}
                onClick={() => s.action(ctx)}
                className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
              >
                {s.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted">
            Tip: press <kbd className="rounded border border-border px-1">Ctrl</kbd>+<kbd className="rounded border border-border px-1">K</kbd> anywhere for the command palette.
          </p>
        </CardBody>
      </Card>

      {/* Copilot answer / search-everywhere results */}
      {ask.isPending && <Spinner />}
      {result && (
        <div className="space-y-3">
          <p className="text-sm text-muted">
            {result.count} result{result.count === 1 ? "" : "s"} for <span className="font-medium text-foreground">&ldquo;{result.query}&rdquo;</span>
          </p>
          {result.results.length === 0 && (
            <EmptyState title="Nothing found" description="No indexed knowledge matches that request yet." />
          )}
          {result.results.map((r) => (
            <Card key={`${r.entity_type}-${r.entity_id}`} className="px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">{r.entity_type}</span>
                <span className="text-xs text-muted">{r.confidence}% match</span>
              </div>
              <p className="mt-1.5 text-sm text-foreground">{r.snippet}</p>
              {r.meeting_id && (
                <Link href={`/meetings/${r.meeting_id}`} className="mt-1 inline-block text-xs font-medium text-brand-600 hover:underline">
                  {r.meeting_title ?? "Meeting"}
                </Link>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* AI Workspace Home tiles */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        {tiles.map((t) => (
          <Link key={t.label} href={t.href}>
            <Card className="h-full transition-shadow hover:shadow-md">
              <CardBody className="space-y-1">
                <t.icon className="h-5 w-5 text-muted" />
                <p className={cn("text-2xl font-bold", t.accent)}>{t.value}</p>
                <p className="text-xs text-muted">{t.label}</p>
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>

      {dashboard.isLoading && <Spinner />}
    </div>
  );
}
