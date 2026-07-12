"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Ban, Loader2, RotateCcw } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert, FullPageSpinner } from "@/components/ui/Feedback";
import { JobStatusBadge } from "@/components/jobs/JobStatusBadge";
import { getApiErrorMessage } from "@/lib/api/client";
import { formatDateTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { JobLog, JobStatus } from "@/lib/types";
import { isJobActive, useJob, useJobControl } from "@/hooks/useJobs";

function fmtMs(ms: number | null): string {
  if (!ms || ms <= 0) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

const LEVEL_COLOR: Record<JobLog["level"], string> = {
  debug: "text-muted",
  info: "text-foreground/80",
  warning: "text-warning",
  error: "text-danger",
};

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: job, isLoading, isError, error } = useJob(id);
  const control = useJobControl(id);

  if (isLoading) return <FullPageSpinner />;
  if (isError || !job) return <Alert>{getApiErrorMessage(error, "Could not load this job.")}</Alert>;

  const active = isJobActive(job.status);
  const canRetry = job.status === "failed" || job.status === "canceled";
  const canCancel = active;

  return (
    <div className="space-y-6">
      <Link href="/jobs" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to jobs
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold text-foreground">{job.pipeline || job.job_type_display}</h1>
            <JobStatusBadge status={job.status as JobStatus} />
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{job.priority_display}</span>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-muted">
            <span>Queue: {job.queue_name}</span>
            <span>Attempt: {job.retry_count}/{job.max_retries}</span>
            <span>Runtime: {fmtMs(job.duration_ms)}</span>
            {job.worker_id && <span>Worker: {job.worker_id}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {canRetry && (
            <Button variant="outline" size="sm" onClick={() => control.mutate("retry")} isLoading={control.isPending}>
              <RotateCcw className="h-4 w-4" /> Retry
            </Button>
          )}
          {canCancel && (
            <Button variant="outline" size="sm" onClick={() => control.mutate("cancel")} isLoading={control.isPending}>
              <Ban className="h-4 w-4" /> Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Live progress */}
      <Card className="px-5 py-4">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="inline-flex items-center gap-2 font-medium text-foreground">
            {active && <Loader2 className="h-4 w-4 animate-spin text-brand-500" />}
            {job.current_stage ? `Stage: ${job.current_stage}` : active ? "Starting…" : "Idle"}
          </span>
          <span className="text-muted">{job.progress}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${job.progress}%` }} />
        </div>
      </Card>

      {job.error_message && (
        <Alert>{job.error_message}</Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader><CardTitle>Logs & timeline</CardTitle></CardHeader>
            <CardBody>
              {job.logs.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted">No log entries yet.</p>
              ) : (
                <ol className="space-y-2 font-mono text-xs">
                  {job.logs.map((log) => (
                    <li key={log.id} className="flex gap-3">
                      <span className="shrink-0 text-muted">{formatDateTime(log.created_at)}</span>
                      {log.stage && <span className="shrink-0 text-brand-500">{log.stage}</span>}
                      <span className={cn("flex-1", LEVEL_COLOR[log.level])}>{log.message}</span>
                      {log.duration_ms != null && <span className="shrink-0 text-muted">{fmtMs(log.duration_ms)}</span>}
                    </li>
                  ))}
                </ol>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Details</CardTitle></CardHeader>
            <CardBody>
              <dl className="space-y-2 text-sm">
                <Row label="Type" value={job.job_type_display} />
                <Row label="Created" value={formatDateTime(job.created_at)} />
                {job.started_at && <Row label="Started" value={formatDateTime(job.started_at)} />}
                {job.finished_at && <Row label="Finished" value={formatDateTime(job.finished_at)} />}
                {job.cancelled_at && <Row label="Cancelled" value={formatDateTime(job.cancelled_at)} />}
              </dl>
            </CardBody>
          </Card>

          {job.stack_trace && (
            <Card>
              <CardHeader><CardTitle>Stack trace</CardTitle></CardHeader>
              <CardBody>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-danger">
                  {job.stack_trace}
                </pre>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="text-right text-foreground/90">{value}</dd>
    </div>
  );
}
