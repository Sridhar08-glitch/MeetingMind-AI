"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  FileAudio,
  FileVideo,
  Loader2,
  Sparkles,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { getApiErrorCode, getApiErrorDetails, getApiErrorMessage } from "@/lib/api/client";
import { meetingsApi } from "@/lib/api/meetings";
import { mediaApi } from "@/lib/api/media";
import { cn, formatBytes, formatDuration } from "@/lib/utils";
import type { DuplicateAction, MeetingSource } from "@/lib/types";
import { meetingKeys } from "@/hooks/useMeetings";
import { demoApi, type DemoSample } from "@/lib/api/demo";
import { usePreferencesStore } from "@/store/preferences";
import { UrlImportPanel } from "@/components/meetings/UrlImportPanel";

const ACCEPTED_EXTENSIONS = ["mp3", "wav", "m4a", "aac", "mp4", "mov", "avi", "mkv"];
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(",") + ",audio/*,video/*";
const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "avi", "mkv"]);

const SOURCE_OPTIONS: { value: MeetingSource; label: string }[] = [
  { value: "manual_upload", label: "Manual upload" },
  { value: "zoom", label: "Zoom" },
  { value: "google_meet", label: "Google Meet" },
  { value: "ms_teams", label: "Microsoft Teams" },
  { value: "mobile_recording", label: "Mobile recording" },
  { value: "voice_recorder", label: "Voice recorder" },
  { value: "other", label: "Other" },
];

type ItemStatus = "pending" | "uploading" | "queued" | "duplicate" | "error";

interface QueueItem {
  id: string;
  file: File;
  title: string;
  status: ItemStatus;
  progress: number;
  meetingId?: string;
  error?: string;
  duplicateMsg?: string;
  etaSeconds?: number;
}

function extensionOf(name: string): string {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop()!.toLowerCase() : "";
}

// Keep in sync with backend MAX_UPLOAD_SIZE_MB (server is authoritative).
const MAX_UPLOAD_MB = 2048;
// Above this we skip loading the file into a media element for the ETA probe
// (avoids lag on very large files).
const ETA_PROBE_MAX_MB = 300;

let itemCounter = 0;

/** Estimate processing time from the recording's real duration (metadata probe). */
function estimateEta(file: File): Promise<number | undefined> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const isVideo = file.type.startsWith("video") || VIDEO_EXTENSIONS.has(extensionOf(file.name));
    const el = document.createElement(isVideo ? "video" : "audio");
    el.preload = "metadata";
    const done = (v: number | undefined) => {
      URL.revokeObjectURL(url);
      resolve(v);
    };
    el.onloadedmetadata = () =>
      done(Number.isFinite(el.duration) ? Math.max(15, Math.round(el.duration * 0.7)) : undefined);
    el.onerror = () => done(undefined);
    el.src = url;
  });
}

export default function UploadPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const defaultSource = usePreferencesStore((s) => s.defaultSource);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [description, setDescription] = useState("");
  const [source, setSource] = useState<MeetingSource>(defaultSource);
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState<"file" | "url">("file");

  // URL import is shown only when at least one importer (yt-dlp/feed/direct) is available.
  const sourcesQuery = useQuery({
    queryKey: ["media-sources"],
    queryFn: () => mediaApi.sources(),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const urlImportAvailable = sourcesQuery.data?.import_available ?? false;

  const samplesQuery = useQuery({
    queryKey: ["demo-samples"],
    queryFn: () => demoApi.samples(),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const samples = samplesQuery.data ?? [];

  const patch = useCallback((id: string, changes: Partial<QueueItem>) => {
    setQueue((q) => q.map((it) => (it.id === id ? { ...it, ...changes } : it)));
  }, []);

  const addFiles = useCallback((files: File[]) => {
    setLocalError(null);
    const valid: QueueItem[] = [];
    for (const file of files) {
      const ext = extensionOf(file.name);
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        setLocalError(`Unsupported file type ".${ext}". Allowed: ${ACCEPTED_EXTENSIONS.join(", ")}.`);
        continue;
      }
      if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        const gb = (file.size / 1024 / 1024 / 1024).toFixed(2);
        setLocalError(`"${file.name}" is ${gb} GB — over the ${(MAX_UPLOAD_MB / 1024).toFixed(0)} GB limit. Please upload a smaller file.`);
        continue;
      }
      const item: QueueItem = {
        id: `q-${(itemCounter += 1)}`,
        file,
        title: file.name.replace(/\.[^.]+$/, ""),
        status: "pending",
        progress: 0,
      };
      valid.push(item);
      // Skip the media-element ETA probe for very large files (avoids lag).
      if (file.size <= ETA_PROBE_MAX_MB * 1024 * 1024) {
        estimateEta(file).then((eta) => eta && patch(item.id, { etaSeconds: eta }));
      }
    }
    if (valid.length) setQueue((q) => [...q, ...valid]);
  }, [patch]);

  const addSample = useCallback(
    async (sample: DemoSample) => {
      try {
        const file = await demoApi.sampleFile(sample);
        addFiles([file]);
      } catch {
        setLocalError("Could not load that sample recording. Please try again.");
      }
    },
    [addFiles],
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (dropped.length) addFiles(dropped);
  };

  const uploadOne = async (item: QueueItem, onDuplicate: DuplicateAction = "reject") => {
    patch(item.id, { status: "uploading", progress: 0, error: undefined, duplicateMsg: undefined });
    try {
      const meeting = await meetingsApi.upload(
        {
          file: item.file,
          title: item.title.trim() || undefined,
          description: description.trim() || undefined,
          source,
          on_duplicate: onDuplicate,
        },
        (percent) => patch(item.id, { progress: percent }),
      );
      patch(item.id, { status: "queued", progress: 100, meetingId: meeting.id });
      queryClient.invalidateQueries({ queryKey: meetingKeys.all });
    } catch (err) {
      const code = getApiErrorCode(err);
      if (code === "duplicate_upload") {
        patch(item.id, { status: "duplicate", duplicateMsg: getApiErrorMessage(err) });
        const details = getApiErrorDetails(err);
        const existingId = details?.existing_meeting_id as string | undefined;
        if (existingId) patch(item.id, { meetingId: existingId });
      } else {
        patch(item.id, { status: "error", error: getApiErrorMessage(err, "Upload failed.") });
      }
    }
  };

  const uploadAll = async () => {
    setRunning(true);
    // Sequential so we don't hammer the worker; re-read latest queue each step.
    for (const item of queue) {
      if (item.status === "pending") {
        await uploadOne(item);
      }
    }
    setRunning(false);
  };

  const remove = (id: string) => setQueue((q) => q.filter((it) => it.id !== id));
  const pendingCount = queue.filter((it) => it.status === "pending").length;
  const allQueued = queue.length > 0 && queue.every((it) => it.status === "queued");

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link
        href="/meetings"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to meetings
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-foreground">Upload meetings</h1>
        <p className="mt-1 text-sm text-muted">
          Upload audio/video files or import from a public URL (video platforms, direct links, podcasts).
          Each is validated, then queued for transcription and AI analysis.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recordings</CardTitle>
        </CardHeader>
        <CardBody className="space-y-5">
          {urlImportAvailable && (
            <div className="flex rounded-lg border border-border bg-slate-50 p-1 text-sm">
              {(["file", "url"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={cn(
                    "flex-1 rounded-md px-3 py-1.5 font-medium transition-colors",
                    tab === t ? "bg-surface text-foreground shadow-sm" : "text-muted hover:text-foreground",
                  )}
                >
                  {t === "file" ? "Upload files" : "Import from URL"}
                </button>
              ))}
            </div>
          )}

          {tab === "url" ? (
            <UrlImportPanel />
          ) : (
          <>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT_ATTR}
            multiple
            className="sr-only"
            onChange={(e) => {
              const chosen = Array.from(e.target.files ?? []);
              if (chosen.length) addFiles(chosen);
              if (inputRef.current) inputRef.current.value = "";
            }}
          />

          {/* Dropzone */}
          <div
            role="button"
            tabIndex={0}
            aria-label="Choose files or drag and drop them here"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400",
              isDragging
                ? "border-brand-500 bg-brand-50"
                : "border-border bg-slate-50/60 hover:border-brand-300 hover:bg-slate-50",
            )}
          >
            <UploadCloud className={cn("h-10 w-10", isDragging ? "text-brand-600" : "text-muted")} />
            <div>
              <p className="text-sm font-medium text-foreground">
                Drag &amp; drop files, or <span className="text-brand-600 underline">browse</span>
              </p>
              <p className="mt-1 text-xs text-muted">
                {ACCEPTED_EXTENSIONS.join(", ").toUpperCase()} · up to {(MAX_UPLOAD_MB / 1024).toFixed(0)} GB · multiple allowed
              </p>
            </div>
          </div>

          {/* Sample recordings */}
          {queue.length === 0 && samples.length > 0 && (
            <div className="rounded-xl border border-border bg-slate-50/60 p-4">
              <div className="mb-1 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-brand-500" />
                <p className="text-sm font-semibold text-foreground">Or try a sample recording</p>
              </div>
              <p className="mb-3 text-xs text-muted">
                Real audio &amp; video meetings — add one to the queue and upload to watch it process for real.
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {samples.map((sample) => {
                  const SampleIcon = sample.media === "video" ? FileVideo : FileAudio;
                  return (
                    <button
                      key={sample.filename}
                      type="button"
                      onClick={() => addSample(sample)}
                      className="flex items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2 text-left transition-colors hover:border-brand-300 hover:bg-brand-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
                    >
                      <SampleIcon className="h-5 w-5 shrink-0 text-brand-500" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-foreground">{sample.title}</span>
                        <span className="block truncate text-xs text-muted">
                          {sample.project} · {sample.media}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {localError && <Alert>{localError}</Alert>}

          {/* Queue */}
          {queue.length > 0 && (
            <ul className="space-y-2">
              {queue.map((item) => (
                <QueueRow key={item.id} item={item} onRemove={remove} onUpload={uploadOne} />
              ))}
            </ul>
          )}

          {/* Shared metadata */}
          {queue.length > 0 && (
            <div className="space-y-4 border-t border-border pt-4">
              <Field label="Description" htmlFor="description" hint="Applied to all uploads in this batch.">
                <textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                  placeholder="Optional context about these meetings…"
                  className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
                />
              </Field>
              <Field label="Source" htmlFor="source" hint="Where these recordings came from.">
                <select
                  id="source"
                  value={source}
                  onChange={(e) => setSource(e.target.value as MeetingSource)}
                  className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
                >
                  {SOURCE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-1">
            <Button variant="outline" onClick={() => router.push("/meetings")}>
              {allQueued ? "Done" : "Cancel"}
            </Button>
            {queue.length > 0 && (
              <div className="flex gap-2">
                {allQueued && queue.length === 1 && queue[0].meetingId && (
                  <Button variant="secondary" onClick={() => router.push(`/meetings/${queue[0].meetingId}`)}>
                    Open meeting
                  </Button>
                )}
                <Button onClick={uploadAll} disabled={pendingCount === 0 || running} isLoading={running}>
                  <UploadCloud className="h-4 w-4" />
                  {pendingCount > 0 ? `Upload ${pendingCount} & process` : "All uploaded"}
                </Button>
              </div>
            )}
          </div>
          </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function QueueRow({
  item,
  onRemove,
  onUpload,
}: {
  item: QueueItem;
  onRemove: (id: string) => void;
  onUpload: (item: QueueItem, onDuplicate?: DuplicateAction) => void;
}) {
  const ext = extensionOf(item.file.name);
  const Icon = VIDEO_EXTENSIONS.has(ext) ? FileVideo : FileAudio;

  return (
    <li className="rounded-lg border border-border bg-surface px-3 py-2.5">
      <div className="flex items-center gap-3">
        <Icon className="h-7 w-7 shrink-0 text-brand-500" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
          <p className="text-xs text-muted">
            {formatBytes(item.file.size)} · {ext.toUpperCase()}
            {item.etaSeconds && item.status === "pending" && (
              <span className="ml-2 inline-flex items-center gap-1 text-muted">
                <Clock className="h-3 w-3" /> ~{formatDuration(item.etaSeconds)} to process
              </span>
            )}
          </p>
        </div>
        <StatusPill item={item} />
        {(item.status === "pending" || item.status === "error") && (
          <button
            onClick={() => onRemove(item.id)}
            className="rounded-md p-1.5 text-muted hover:bg-slate-100 hover:text-foreground"
            aria-label="Remove from queue"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {item.status === "uploading" && (
        <div className="mt-2 space-y-1">
          <div className="flex justify-between text-xs text-muted">
            <span>Uploading…</span>
            <span>{item.progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${item.progress}%` }} />
          </div>
        </div>
      )}

      {item.status === "queued" && item.meetingId && (
        <div className="mt-1.5 flex items-center gap-3 text-xs">
          <span className="text-success">Uploaded → queued for processing.</span>
          <Link href={`/meetings/${item.meetingId}`} className="font-medium text-brand-600 hover:text-brand-700">
            View progress →
          </Link>
        </div>
      )}

      {item.status === "duplicate" && (
        <div className="mt-2 space-y-2 rounded-lg border border-warning/40 bg-warning-bg px-3 py-2">
          <p className="text-xs text-warning">{item.duplicateMsg ?? "You already uploaded this file."}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => onUpload(item, "replace")}>
              Replace
            </Button>
            <Button size="sm" variant="outline" onClick={() => onUpload(item, "keep_both")}>
              Keep both
            </Button>
            {item.meetingId && (
              <Link href={`/meetings/${item.meetingId}`}>
                <Button size="sm" variant="ghost">
                  Open existing
                </Button>
              </Link>
            )}
          </div>
        </div>
      )}

      {item.status === "error" && item.error && (
        <div className="mt-1.5 flex items-center gap-2 text-xs text-danger">
          <XCircle className="h-3.5 w-3.5" /> {item.error}
          <button onClick={() => onUpload(item)} className="font-medium underline hover:no-underline">
            Retry
          </button>
        </div>
      )}
    </li>
  );
}

function StatusPill({ item }: { item: QueueItem }) {
  const map: Record<ItemStatus, { label: string; cls: string; icon?: typeof CheckCircle2 }> = {
    pending: { label: "Ready", cls: "bg-slate-100 text-muted" },
    uploading: { label: "Uploading", cls: "bg-brand-50 text-brand-700", icon: Loader2 },
    queued: { label: "Queued", cls: "bg-success-bg text-success", icon: CheckCircle2 },
    duplicate: { label: "Duplicate", cls: "bg-warning-bg text-warning" },
    error: { label: "Failed", cls: "bg-danger-bg text-danger", icon: XCircle },
  };
  const s = map[item.status];
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", s.cls)}>
      {Icon && <Icon className={cn("h-3 w-3", item.status === "uploading" && "animate-spin")} />}
      {s.label}
    </span>
  );
}
