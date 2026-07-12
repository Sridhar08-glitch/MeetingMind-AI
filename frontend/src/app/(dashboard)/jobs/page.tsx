"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Activity, CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Alert, FullPageSpinner } from "@/components/ui/Feedback";
import { JobStatusBadge } from "@/components/jobs/JobStatusBadge";
import { getApiErrorMessage } from "@/lib/api/client";
import { formatDateTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { HealthComponent, JobStatus } from "@/lib/types";
import { useHealth, useJobMetrics, useJobs } from "@/hooks/useJobs";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "succeeded", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "canceled", label: "Cancelled" },
];

function fmtMs(ms: number | null): string {
  if (!ms || ms <= 0) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

const HEALTH_DOT: Record<string, string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  down: "bg-danger",
};

export default function JobsDashboardPage() {
  const [status, setStatus] = useState("");
  const params = useMemo(() => ({ status: status || undefined }), [status]);

  const { data: metrics } = useJobMetrics();
  const { data: health } = useHealth();
  const { data: jobs, isLoading, isError, error } = useJobs(params);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Background jobs</h1>
        <p className="mt-1 text-sm text-muted">
          Live view of the processing platform — pipelines, retries and worker health.
        </p>
      </div>

      {/* Health strip */}
      {health && (
        <Card className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3">
          <span className="text-sm font-medium text-foreground">System health</span>
          {Object.entries(health.components).map(([name, comp]: [string, HealthComponent]) => (
            <span key={name} className="inline-flex items-center gap-1.5 text-sm text-muted">
              <span className={cn("h-2 w-2 rounded-full", HEALTH_DOT[comp.status] ?? "bg-slate-300")} />
              <span className="capitalize">{name}</span>
              <span className="text-xs text-muted/70">{comp.status}</span>
            </span>
          ))}
        </Card>
      )}

      {/* Metrics cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <MetricCard icon={Loader2} label="Running" value={metrics?.running_jobs ?? 0} tone="info" />
        <MetricCard icon={Activity} label="Queued" value={metrics?.queued_jobs ?? 0} tone="warning" />
        <MetricCard icon={CheckCircle2} label="Completed" value={metrics?.completed_jobs ?? 0} tone="success" />
        <MetricCard icon={XCircle} label="Failed" value={metrics?.failed_jobs ?? 0} tone="danger" />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Success rate" value={metrics ? `${metrics.success_rate}%` : "—"} />
        <StatCard label="Retry rate" value={metrics ? `${metrics.retry_rate}%` : "—"} />
        <StatCard label="Avg runtime" value={fmtMs(metrics?.average_runtime_ms ?? null)} />
        <StatCard label="Longest runtime" value={fmtMs(metrics?.longest_runtime_ms ?? null)} />
      </div>

      {/* Pipeline stats */}
      {metrics && metrics.pipelines.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border px-5 py-3 text-sm font-semibold text-foreground">
            Pipelines
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-2.5 font-medium">Pipeline</th>
                <th className="px-5 py-2.5 font-medium">Total</th>
                <th className="px-5 py-2.5 font-medium">Success rate</th>
                <th className="px-5 py-2.5 font-medium">Avg runtime</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {metrics.pipelines.map((p) => (
                <tr key={p.pipeline}>
                  <td className="px-5 py-2.5 font-medium text-foreground">{p.pipeline}</td>
                  <td className="px-5 py-2.5 text-muted">{p.total}</td>
                  <td className="px-5 py-2.5 text-muted">{p.success_rate}%</td>
                  <td className="px-5 py-2.5 text-muted">{fmtMs(p.avg_runtime_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Filter + jobs table */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Recent jobs</h2>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-9 rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <FullPageSpinner />
      ) : isError ? (
        <Alert>{getApiErrorMessage(error, "Could not load jobs.")}</Alert>
      ) : !jobs || jobs.results.length === 0 ? (
        <Card className="px-5 py-12 text-center text-sm text-muted">No jobs yet.</Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Pipeline</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Progress</th>
                <th className="px-5 py-3 font-medium">Stage</th>
                <th className="px-5 py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {jobs.results.map((job) => (
                <tr key={job.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3">
                    <Link href={`/jobs/${job.id}`} className="font-medium text-foreground hover:text-brand-600">
                      {job.pipeline || job.job_type_display}
                    </Link>
                  </td>
                  <td className="px-5 py-3"><JobStatusBadge status={job.status as JobStatus} /></td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full bg-brand-500" style={{ width: `${job.progress}%` }} />
                      </div>
                      <span className="text-xs text-muted">{job.progress}%</span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-muted">{job.current_stage || "—"}</td>
                  <td className="px-5 py-3 text-muted">{formatDateTime(job.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  tone: "info" | "warning" | "success" | "danger";
}) {
  const toneMap = {
    info: "bg-info-bg text-info",
    warning: "bg-warning-bg text-warning",
    success: "bg-success-bg text-success",
    danger: "bg-danger-bg text-danger",
  };
  return (
    <Card className="flex items-center gap-3 px-5 py-4">
      <span className={cn("flex h-10 w-10 items-center justify-center rounded-lg", toneMap[tone])}>
        <Icon className="h-5 w-5" />
      </span>
      <div>
        <p className="text-xs text-muted">{label}</p>
        <p className="text-xl font-bold text-foreground">{value}</p>
      </div>
    </Card>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="px-5 py-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-foreground">{value}</p>
    </Card>
  );
}
