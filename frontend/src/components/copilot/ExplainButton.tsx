"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HelpCircle, X } from "lucide-react";

import { executiveApi } from "@/lib/api/executive";
import { Spinner } from "@/components/ui/Feedback";
import { cn } from "@/lib/utils";

/**
 * AI Explain Mode — a one-click "Why?" that reveals the stored explanation for a
 * metric (formula, evidence, confidence, knowledge version). Nothing appears as a
 * mysterious AI score.
 */
export function ExplainButton({ metric, scope = "organization", className }: {
  metric: string;
  scope?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["explain", scope, metric],
    queryFn: () => executiveApi.explain(metric, scope),
    enabled: open,
    retry: false,
  });

  return (
    <div className={cn("relative inline-block", className)}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-xs text-muted hover:text-brand-600"
        aria-label={`Why is ${metric} this value?`}
      >
        <HelpCircle className="h-3.5 w-3.5" /> Why?
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 rounded-lg border border-border bg-surface p-3 text-left shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Explanation</span>
            <button onClick={() => setOpen(false)} className="text-muted hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          {q.isLoading && <Spinner className="h-4 w-4" />}
          {q.isError && <p className="text-xs text-muted">No explanation recorded yet — refresh the dashboard.</p>}
          {q.data && (
            <div className="space-y-2 text-xs">
              {q.data.value != null && (
                <p className="text-2xl font-bold text-foreground">{Math.round(q.data.value)}</p>
              )}
              <div>
                <p className="font-semibold text-foreground">How it&apos;s calculated</p>
                <p className="text-muted">{q.data.formula}</p>
              </div>
              {q.data.evidence && Object.keys(q.data.evidence).length > 0 && (
                <div>
                  <p className="font-semibold text-foreground">Evidence</p>
                  <ul className="text-muted">
                    {Object.entries(q.data.evidence).slice(0, 8).map(([k, v]) => (
                      <li key={k}>
                        <span className="text-foreground">{k.replace(/_/g, " ")}:</span> {String(v)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-border pt-2 text-[11px] text-muted">
                <span>Knowledge v{q.data.knowledge_version}</span>
                <span>Snapshot v{q.data.snapshot_version}</span>
                {q.data.confidence != null && <span>Confidence {Math.round(q.data.confidence)}%</span>}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
