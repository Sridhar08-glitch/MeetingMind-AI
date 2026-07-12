"use client";

import { useEffect, useMemo, useRef } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, Loader2, X, XCircle } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { mediaApi } from "@/lib/api/media";
import { meetingKeys } from "@/hooks/useMeetings";
import { cn } from "@/lib/utils";
import type { DuplicateAction, MediaImportSession, MediaImportStatus } from "@/lib/types";

const ACTIVE: MediaImportStatus[] = [
  "pending", "analyzing", "downloading", "downloaded", "validating", "importing", "processing",
];
const STATUS_LABEL: Record<MediaImportStatus, string> = {
  pending: "Queued", analyzing: "Analyzing", downloading: "Downloading", downloaded: "Downloaded",
  validating: "Validating", importing: "Importing", processing: "Processing", completed: "Completed",
  failed: "Failed", cancelled: "Cancelled", blocked: "Blocked",
};
const isActive = (s: MediaImportSession) => ACTIVE.includes(s.status);
// Keep terminal failures visible for a while so a refusal isn't missed.
const RECENT_MS = 2 * 60 * 60 * 1000;

/**
 * Persistent, backend-backed view of media imports in progress. Unlike the
 * in-page import panel, this reads `GET /meetings/import/`, so it keeps showing
 * downloads even after navigating away, and surfaces recent failures/refusals.
 */
export function ImportsQueue() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["media-imports"],
    queryFn: () => mediaApi.list(),
    refetchInterval: (q) =>
      (q.state.data as MediaImportSession[] | undefined)?.some(isActive) ? 2500 : false,
    retry: false,
  });
  const sessions = useMemo(() => query.data ?? [], [query.data]);

  // When an import produces or finishes a meeting, refresh the meetings list so
  // the new recording appears without a manual reload.
  const seen = useRef<Set<string>>(new Set());
  useEffect(() => {
    let fresh = false;
    for (const s of sessions) {
      if (s.meeting_id && !seen.current.has(s.meeting_id)) {
        seen.current.add(s.meeting_id);
        fresh = true;
      }
    }
    if (fresh) qc.invalidateQueries({ queryKey: meetingKeys.all });
  }, [sessions, qc]);

  // Use the query's fetch time (not Date.now(), which is impure in render).
  const now = query.dataUpdatedAt || 0;
  const visible = sessions.filter(
    (s) =>
      isActive(s) ||
      ((s.status === "failed" || s.status === "blocked") &&
        now - new Date(s.updated_at).getTime() < RECENT_MS),
  );
  if (!visible.length) return null;

  const activeCount = visible.filter(isActive).length;

  async function resolve(s: MediaImportSession, action: DuplicateAction) {
    await mediaApi.import({
      url: s.source_url,
      episode_id: s.episode_id || undefined,
      requested_media: s.requested_media,
      meeting_language: s.meeting_language,
      transcript_language: s.transcript_language,
      ai_language: s.ai_language,
      on_duplicate: action,
    });
    query.refetch();
  }
  async function cancel(s: MediaImportSession) {
    await mediaApi.cancel(s.id);
    query.refetch();
  }

  return (
    <Card>
      <CardHeader className="flex items-center gap-2">
        <Download className="h-4 w-4 text-brand-600" />
        <CardTitle>Imports{activeCount > 0 ? ` (${activeCount} in progress)` : ""}</CardTitle>
      </CardHeader>
      <CardBody>
        <ul className="space-y-2">
          {visible.map((s) => (
            <Row key={s.id} session={s} onResolve={resolve} onCancel={cancel} />
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

function Row({
  session, onResolve, onCancel,
}: {
  session: MediaImportSession;
  onResolve: (s: MediaImportSession, a: DuplicateAction) => void;
  onCancel: (s: MediaImportSession) => void;
}) {
  const active = isActive(session);
  const done = session.status === "completed";
  const isDup = session.error_code === "duplicate_import";
  const failed = session.status === "failed" || session.status === "blocked";

  return (
    <li className="rounded-lg border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {session.title || session.source_url}
          </p>
          <p className="truncate text-xs text-muted">
            {[session.platform, session.author].filter(Boolean).join(" · ") || session.source_url}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            done && "bg-success-bg text-success",
            active && "bg-brand-50 text-brand-700",
            failed && "bg-danger-bg text-danger",
          )}
        >
          {active && <Loader2 className="h-3 w-3 animate-spin" />}
          {done && <CheckCircle2 className="h-3 w-3" />}
          {failed && <XCircle className="h-3 w-3" />}
          {STATUS_LABEL[session.status]}
          {session.status === "downloading" && ` ${session.progress}%`}
        </span>
        {active && (
          <button
            onClick={() => onCancel(session)}
            className="rounded-md p-1.5 text-muted hover:bg-slate-100 hover:text-foreground"
            aria-label="Cancel import"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {session.status === "downloading" && (
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${session.progress}%` }} />
        </div>
      )}

      {(session.status === "processing" || done) && session.meeting_id && (
        <div className="mt-1.5 flex items-center gap-3 text-xs">
          <span className="text-success">{done ? "Imported and processed." : "Imported → processing."}</span>
          <Link href={`/meetings/${session.meeting_id}`} className="font-medium text-brand-600 hover:text-brand-700">
            Open meeting →
          </Link>
        </div>
      )}

      {isDup && (
        <div className="mt-2 space-y-2 rounded-lg border border-warning/40 bg-warning-bg px-3 py-2">
          <p className="flex items-center gap-1.5 text-xs text-warning">
            <AlertTriangle className="h-3.5 w-3.5" /> {session.error_message || "Already imported."}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => onResolve(session, "replace")}>Reprocess</Button>
            <Button size="sm" variant="outline" onClick={() => onResolve(session, "keep_both")}>Keep both</Button>
            {session.duplicate_meeting_id && (
              <Link href={`/meetings/${session.duplicate_meeting_id}`}>
                <Button size="sm" variant="ghost">Open existing</Button>
              </Link>
            )}
          </div>
        </div>
      )}

      {failed && !isDup && (
        <p className="mt-1.5 flex items-center gap-2 text-xs text-danger">
          <XCircle className="h-3.5 w-3.5" /> {session.error_message || "Import failed."}
        </p>
      )}
    </li>
  );
}
