"use client";

import { AlertTriangle, Check, Quote, X } from "lucide-react";

import { cn, formatTimestamp } from "@/lib/utils";
import type { AISuggestion } from "@/lib/types";

const CONF_STYLE: Record<string, string> = {
  high: "bg-success-bg text-success",
  medium: "bg-warning-bg text-warning",
  low: "bg-danger-bg text-danger",
};

const TYPE_STYLE: Record<string, string> = {
  task: "bg-brand-50 text-brand-700",
  issue: "bg-danger-bg text-danger",
  decision: "bg-info-bg text-info",
  risk: "bg-warning-bg text-warning",
  follow_up: "bg-slate-100 text-slate-600",
};

export function SuggestionCard({
  suggestion,
  onApprove,
  onReject,
  busy,
}: {
  suggestion: AISuggestion;
  onApprove: () => void;
  onReject: () => void;
  busy?: boolean;
}) {
  const s = suggestion;
  const low = s.confidence === "low";
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium capitalize", TYPE_STYLE[s.suggestion_type])}>
          {s.suggestion_type.replace("_", " ")}
        </span>
        <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium capitalize", CONF_STYLE[s.confidence])}>
          {s.confidence} ({s.confidence_score}%)
        </span>
      </div>

      <p className="text-sm font-medium text-foreground">{s.title}</p>
      {s.reason && <p className="mt-0.5 text-xs text-muted">{s.reason}</p>}

      {s.quote && (
        <div className="mt-2 flex gap-1.5 rounded-md bg-slate-50 px-2 py-1.5 text-xs text-muted">
          <Quote className="mt-0.5 h-3 w-3 shrink-0" />
          <span>
            {s.source_speaker && <span className="font-medium text-foreground/80">{s.source_speaker} </span>}
            {s.source_start_time != null && (
              <span className="font-mono text-brand-500">[{formatTimestamp(s.source_start_time)}] </span>
            )}
            “{s.quote.replace(/^[^:]+:\s*/, "").slice(0, 140)}”
          </span>
        </div>
      )}

      {low && (
        <p className="mt-2 inline-flex items-center gap-1 text-xs text-danger">
          <AlertTriangle className="h-3 w-3" /> Low confidence — please review before approving.
        </p>
      )}

      <div className="mt-2.5 flex gap-2">
        <button
          onClick={onApprove}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-md bg-success-bg px-2.5 py-1 text-xs font-medium text-success hover:brightness-95 disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" /> Approve
        </button>
        <button
          onClick={onReject}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-muted hover:text-danger disabled:opacity-50"
        >
          <X className="h-3.5 w-3.5" /> Reject
        </button>
      </div>
    </div>
  );
}
