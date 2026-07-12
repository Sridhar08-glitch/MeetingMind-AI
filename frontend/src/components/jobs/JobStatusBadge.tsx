import { cn } from "@/lib/utils";
import type { JobStatus } from "@/lib/types";

const styles: Record<JobStatus, string> = {
  queued: "bg-warning-bg text-warning",
  waiting: "bg-warning-bg text-warning",
  running: "bg-info-bg text-info",
  retrying: "bg-warning-bg text-warning",
  paused: "bg-slate-100 text-slate-600",
  cancellation_requested: "bg-warning-bg text-warning",
  canceled: "bg-slate-100 text-slate-500",
  succeeded: "bg-success-bg text-success",
  failed: "bg-danger-bg text-danger",
  expired: "bg-danger-bg text-danger",
};

const labels: Record<JobStatus, string> = {
  queued: "Queued",
  waiting: "Waiting",
  running: "Running",
  retrying: "Retrying",
  paused: "Paused",
  cancellation_requested: "Cancelling",
  canceled: "Cancelled",
  succeeded: "Completed",
  failed: "Failed",
  expired: "Expired",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", styles[status])}>
      {labels[status]}
    </span>
  );
}
