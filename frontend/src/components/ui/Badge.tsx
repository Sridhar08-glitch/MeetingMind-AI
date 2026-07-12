import { cn } from "@/lib/utils";
import type { ProcessingStatus, UploadStatus } from "@/lib/types";

const processingStyles: Record<ProcessingStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  queued: "bg-warning-bg text-warning",
  running: "bg-warning-bg text-warning",
  retrying: "bg-warning-bg text-warning",
  completed: "bg-success-bg text-success",
  failed: "bg-danger-bg text-danger",
  canceled: "bg-slate-100 text-slate-500",
};

const processingLabels: Record<ProcessingStatus, string> = {
  pending: "Not started",
  queued: "Queued",
  running: "Processing",
  retrying: "Retrying",
  completed: "Completed",
  failed: "Failed",
  canceled: "Canceled",
};

const uploadStyles: Record<UploadStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  uploading: "bg-info-bg text-info",
  uploaded: "bg-info-bg text-info",
  stored: "bg-info-bg text-info",
  verified: "bg-success-bg text-success",
  failed: "bg-danger-bg text-danger",
};

const uploadLabels: Record<UploadStatus, string> = {
  pending: "Pending",
  uploading: "Uploading",
  uploaded: "Uploaded",
  stored: "Stored",
  verified: "Verified",
  failed: "Upload failed",
};

const base = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium";

export function ProcessingBadge({ status }: { status: ProcessingStatus }) {
  return <span className={cn(base, processingStyles[status])}>{processingLabels[status]}</span>;
}

export function UploadBadge({ status }: { status: UploadStatus }) {
  return <span className={cn(base, uploadStyles[status])}>{uploadLabels[status]}</span>;
}
