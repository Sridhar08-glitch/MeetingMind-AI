"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckSquare,
  Gavel,
  History,
  ListChecks,
  RefreshCw,
  Sparkles,
  Tag,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { getApiErrorMessage } from "@/lib/api/client";
import { meetingsApi } from "@/lib/api/meetings";
import { cn } from "@/lib/utils";
import type { AIAnalysis } from "@/lib/types";
import { meetingKeys, useAIAnalysis } from "@/hooks/useMeetings";

const SEVERITY: Record<string, string> = {
  high: "bg-danger-bg text-danger",
  medium: "bg-warning-bg text-warning",
  low: "bg-slate-100 text-slate-600",
};

export function AISummaryPanel({ meetingId, processing }: { meetingId: string; processing: boolean }) {
  const queryClient = useQueryClient();
  const { data: ai, isLoading } = useAIAnalysis(meetingId, { poll: processing });
  const [showHistory, setShowHistory] = useState(false);

  const history = useQuery({
    queryKey: [...meetingKeys.ai(meetingId), "history"],
    queryFn: () => meetingsApi.aiHistory(meetingId),
    enabled: showHistory,
  });

  const regenerate = useMutation({
    mutationFn: () => meetingsApi.regenerateAI(meetingId),
    onSuccess: () => {
      // Poll for the new version.
      setTimeout(() => queryClient.invalidateQueries({ queryKey: meetingKeys.ai(meetingId) }), 1500);
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-600" /> AI insights
        </CardTitle>
        {ai && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">
              v{ai.version} · {ai.provider}/{ai.model_used}
            </span>
            <Button size="sm" variant="ghost" onClick={() => setShowHistory((s) => !s)}>
              <History className="h-3.5 w-3.5" /> History
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => regenerate.mutate()}
              isLoading={regenerate.isPending}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Regenerate
            </Button>
          </div>
        )}
      </CardHeader>

      <CardBody className="space-y-5">
        {isLoading ? (
          <p className="py-6 text-center text-sm text-muted">Loading AI insights…</p>
        ) : !ai ? (
          <p className="py-6 text-center text-sm text-muted">
            {processing
              ? "Generating summary with the local model… this updates automatically."
              : "No AI summary yet."}
            {regenerate.isError && (
              <span className="mt-2 block text-danger">{getApiErrorMessage(regenerate.error)}</span>
            )}
          </p>
        ) : (
          <>
            {showHistory && (
              <div className="rounded-lg border border-border bg-slate-50 p-3 text-sm">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Version history</p>
                {history.data?.map((v) => (
                  <div key={v.id} className="flex justify-between py-0.5 text-muted">
                    <span>v{v.version} · {v.provider}/{v.model_used}{v.is_current && " (current)"}</span>
                    <span>{new Date(v.created_at).toLocaleString()}</span>
                  </div>
                )) ?? <p className="text-muted">Loading…</p>}
              </div>
            )}

            {/* Executive summary */}
            <Section icon={Sparkles} title="Executive summary">
              <p className="text-sm text-foreground/90">{ai.executive_summary || "—"}</p>
            </Section>

            {ai.bullet_summary.length > 0 && (
              <Section icon={ListChecks} title="Key points">
                <ul className="list-disc space-y-1 pl-5 text-sm text-foreground/90">
                  {ai.bullet_summary.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </Section>
            )}

            {ai.action_items.length > 0 && (
              <Section icon={CheckSquare} title={`Action items (${ai.action_items.length})`}>
                <ul className="space-y-2">
                  {ai.action_items.map((a, i) => (
                    <li key={i} className="rounded-lg border border-border p-2.5 text-sm">
                      <p className="font-medium text-foreground">{a.task}</p>
                      <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
                        {a.owner && <Chip>{a.owner}</Chip>}
                        {a.priority && <span className={cn("rounded px-1.5 py-0.5", SEVERITY[a.priority.toLowerCase()] ?? "bg-slate-100")}>{a.priority}</span>}
                        {a.due_date && <Chip>due {a.due_date}</Chip>}
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {ai.decisions.length > 0 && (
              <Section icon={Gavel} title={`Decisions (${ai.decisions.length})`}>
                <ul className="space-y-2">
                  {ai.decisions.map((d, i) => (
                    <li key={i} className="rounded-lg border border-border p-2.5 text-sm">
                      <p className="font-medium text-foreground">{d.decision}</p>
                      {d.reason && <p className="text-xs text-muted">Why: {d.reason}</p>}
                      {d.participants?.length > 0 && <p className="text-xs text-muted">{d.participants.join(", ")}</p>}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {ai.risks.length > 0 && (
              <Section icon={AlertTriangle} title={`Risks (${ai.risks.length})`}>
                <ul className="space-y-2">
                  {ai.risks.map((r, i) => (
                    <li key={i} className="rounded-lg border border-border p-2.5 text-sm">
                      <div className="flex items-center gap-2">
                        <span className={cn("rounded px-1.5 py-0.5 text-xs", SEVERITY[r.severity?.toLowerCase()] ?? "bg-slate-100")}>{r.severity || "risk"}</span>
                        <p className="font-medium text-foreground">{r.risk}</p>
                      </div>
                      {r.mitigation && <p className="mt-1 text-xs text-muted">Mitigation: {r.mitigation}</p>}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {(ai.follow_ups.length > 0 || ai.deadlines.length > 0) && (
              <div className="grid gap-4 sm:grid-cols-2">
                {ai.follow_ups.length > 0 && (
                  <Section title="Follow-ups">
                    <ul className="list-disc space-y-1 pl-5 text-sm text-foreground/90">
                      {ai.follow_ups.map((f, i) => <li key={i}>{f.item}{f.owner && ` — ${f.owner}`}</li>)}
                    </ul>
                  </Section>
                )}
                {ai.deadlines.length > 0 && (
                  <Section title="Deadlines">
                    <ul className="list-disc space-y-1 pl-5 text-sm text-foreground/90">
                      {ai.deadlines.map((d, i) => <li key={i}>{d.item} — {d.date}</li>)}
                    </ul>
                  </Section>
                )}
              </div>
            )}

            <Section icon={Tag} title="Keywords">
              <div className="flex flex-wrap gap-1.5">
                {allKeywords(ai).map((k, i) => <Chip key={i}>{k}</Chip>)}
                {allKeywords(ai).length === 0 && <span className="text-sm text-muted">—</span>}
              </div>
            </Section>
          </>
        )}
      </CardBody>
    </Card>
  );
}

function Section({ icon: Icon, title, children }: { icon?: typeof Sparkles; title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand-600">
        {Icon && <Icon className="h-3.5 w-3.5" />} {title}
      </p>
      {children}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">{children}</span>;
}

function allKeywords(ai: AIAnalysis): string[] {
  const k = ai.keywords;
  return [...(k.topics ?? []), ...(k.technologies ?? []), ...(k.people ?? []), ...(k.companies ?? [])];
}
