"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Clock,
  Download,
  ExternalLink,
  Globe,
  Layers,
  Loader2,
  RefreshCw,
  Star,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { ProcessingBadge, UploadBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Alert, EmptyState, FullPageSpinner } from "@/components/ui/Feedback";
import { Timeline } from "@/components/meetings/Timeline";
import { MediaThumbnail } from "@/components/meetings/MediaThumbnail";
import { MediaPlayer } from "@/components/meetings/MediaPlayer";
import { TranscriptPanel } from "@/components/meetings/TranscriptPanel";
import { AISummaryPanel } from "@/components/meetings/AISummaryPanel";
import { ChatPanel } from "@/components/meetings/ChatPanel";
import { AIReviewCenter } from "@/components/workspace/AIReviewCenter";
import { getApiErrorMessage } from "@/lib/api/client";
import { meetingsApi } from "@/lib/api/meetings";
import { cn, formatBytes, formatDateTime, formatDuration } from "@/lib/utils";
import type { MeetingFile } from "@/lib/types";
import { isInProgress, useMeeting, useToggleFavorite } from "@/hooks/useMeetings";
import { useQueryClient } from "@tanstack/react-query";
import { meetingKeys } from "@/hooks/useMeetings";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useRecentsStore } from "@/store/recents";

const SOURCE_LABELS: Record<string, string> = {
  manual_upload: "Manual upload",
  live: "Live recording",
  screen_recording: "Screen recording",
  webcam_recording: "Webcam recording",
  zoom: "Zoom",
  google_meet: "Google Meet",
  ms_teams: "Microsoft Teams",
  mobile_recording: "Mobile recording",
  voice_recorder: "Voice recorder",
  public_video: "Public video",
  podcast: "Podcast",
  rss_feed: "RSS feed",
  direct_url: "Direct URL",
  batch_import: "Batch import",
  other: "Other",
};

/** A friendly, stage-aware processing message derived from the latest event. */
function processingStage(status: string, events: { message?: string; created_at: string }[]): string {
  if (status === "queued") return "⏳ Queued for processing…";
  const latest = [...(events ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const msg = (latest?.message ?? "").toLowerCase();
  if (/speech|transcri/.test(msg)) return "🎤 Transcribing audio…";
  if (/ai|summar|analysis/.test(msg)) return "🧠 Generating summary…";
  if (/knowledge|index/.test(msg)) return "📚 Updating knowledge…";
  if (/normal|extract|media|audio/.test(msg)) return "🎧 Preparing audio…";
  if (/segment|clean/.test(msg)) return "✍️ Building the transcript…";
  return "⚙️ Processing… this page updates automatically.";
}

export default function MeetingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const { data: meeting, isLoading, isError, error } = useMeeting(id);
  const toggleFavorite = useToggleFavorite();
  const recordRecent = useRecentsStore((s) => s.record);

  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const setMediaEl = useCallback((el: HTMLMediaElement | null) => {
    mediaRef.current = el;
  }, []);
  const seek = useCallback((t: number) => {
    const el = mediaRef.current;
    if (!el) return;
    el.currentTime = t;
    void el.play().catch(() => {});
  }, []);

  usePageTitle(meeting?.title);

  // Track the meeting in "recently opened".
  useEffect(() => {
    if (meeting) recordRecent({ id: meeting.id, title: meeting.title });
  }, [meeting?.id, meeting?.title, recordRecent]); // eslint-disable-line react-hooks/exhaustive-deps

  // The transcript/AI panels poll only while processing; the last poll usually
  // lands just before the results are committed, so when processing finishes we
  // refetch them once here — otherwise they'd show "nothing yet" until reload.
  const wasProcessing = useRef(false);
  useEffect(() => {
    const nowProcessing = isInProgress(meeting?.processing_status);
    if (wasProcessing.current && !nowProcessing) {
      queryClient.invalidateQueries({ queryKey: meetingKeys.transcript(id) });
      queryClient.invalidateQueries({ queryKey: meetingKeys.ai(id) });
      queryClient.invalidateQueries({ queryKey: meetingKeys.detail(id) });
    }
    wasProcessing.current = nowProcessing;
  }, [meeting?.processing_status, id, queryClient]);

  if (isLoading) return <FullPageSpinner />;
  if (isError || !meeting) return <Alert>{getApiErrorMessage(error, "Could not load this meeting.")}</Alert>;

  const processing = isInProgress(meeting.processing_status);
  const current = meeting.current_file;
  const meta = current?.media_metadata;
  const canReprocess = ["completed", "failed", "canceled", "pending"].includes(meeting.processing_status);

  const handleDownload = async (file: MeetingFile) => {
    const blob = await meetingsApi.download(meeting.id, file.version);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.original_filename || file.stored_filename || "recording";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const handleReprocess = async () => {
    try {
      await meetingsApi.reprocess(meeting.id);
      queryClient.invalidateQueries({ queryKey: meetingKeys.detail(meeting.id) });
    } catch (err) {
      alert(getApiErrorMessage(err, "Could not re-queue processing."));
    }
  };

  return (
    <div className="space-y-6">
      <Link href="/meetings" className="inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back to meetings
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-4">
          <MediaThumbnail
            thumbnailUrl={current?.thumbnail_url}
            mediaKind={current?.media_kind}
            className="h-20 w-28 shrink-0"
            alt={meeting.title}
          />
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-foreground">{meeting.title}</h1>
              <ProcessingBadge status={meeting.processing_status} />
              {meeting.upload_status && <UploadBadge status={meeting.upload_status} />}
            </div>
            {meeting.description && <p className="max-w-2xl text-sm text-muted">{meeting.description}</p>}
            <div className="flex flex-wrap gap-4 pt-1 text-sm text-muted">
              <span className="inline-flex items-center gap-1.5">
                <Clock className="h-4 w-4" /> {formatDuration(meeting.duration_seconds)}
              </span>
              <span>Language: {meeting.language.toUpperCase()}</span>
              <span>Source: {SOURCE_LABELS[meeting.source] ?? meeting.source}</span>
              <span>Uploaded: {formatDateTime(current?.uploaded_at ?? meeting.created_at)}</span>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => toggleFavorite.mutate(meeting.id)}
            aria-pressed={meeting.is_favorite}
          >
            <Star className={cn("h-4 w-4", meeting.is_favorite && "fill-amber-400 text-amber-500")} />
            {meeting.is_favorite ? "Starred" : "Star"}
          </Button>
          {canReprocess && (
            <Button variant="outline" size="sm" onClick={handleReprocess}>
              <RefreshCw className="h-4 w-4" /> Reprocess
            </Button>
          )}
          {current?.download_url && (
            <Button variant="outline" size="sm" onClick={() => handleDownload(current)}>
              <Download className="h-4 w-4" /> Download
            </Button>
          )}
        </div>
      </div>

      {processing && (
        <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-brand-700">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          <span>{processingStage(meeting.processing_status, meeting.events)}</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          {current?.download_url && (current.media_kind === "audio" || current.media_kind === "video") && (
            <MediaPlayer
              key={`${meeting.id}:${current.version}`}
              meetingId={meeting.id}
              version={current.version}
              mediaKind={current.media_kind}
              setMediaEl={setMediaEl}
              onTime={setCurrentTime}
            />
          )}
          <TranscriptPanel
            meetingId={meeting.id}
            processing={processing}
            currentTime={currentTime}
            onSeek={seek}
          />
          <AISummaryPanel meetingId={meeting.id} processing={processing} />
          <AIReviewCenter meetingId={meeting.id} />
          <ChatPanel meetingId={meeting.id} />
        </div>

        <div className="space-y-6">
          {(meeting.source_url || (meeting.source_metadata && Object.keys(meeting.source_metadata).length > 0)) && (
            <Card>
              <CardHeader className="flex items-center gap-2">
                <Globe className="h-4 w-4 text-brand-600" />
                <CardTitle>Source information</CardTitle>
              </CardHeader>
              <CardBody>
                <dl className="space-y-2 text-sm">
                  <DetailRow label="Type" value={SOURCE_LABELS[meeting.source] ?? meeting.source} />
                  {meeting.source_metadata?.platform && (
                    <DetailRow label="Platform" value={String(meeting.source_metadata.platform)} />
                  )}
                  {meeting.source_metadata?.author && (
                    <DetailRow label="Author / channel" value={String(meeting.source_metadata.author)} />
                  )}
                  {meeting.source_metadata?.podcast && (
                    <DetailRow label="Podcast" value={String(meeting.source_metadata.podcast)} />
                  )}
                  {meeting.source_metadata?.episode && (
                    <DetailRow label="Episode" value={String(meeting.source_metadata.episode)} />
                  )}
                  {meeting.source_metadata?.published_at && (
                    <DetailRow label="Published" value={String(meeting.source_metadata.published_at)} />
                  )}
                  {meeting.source_metadata?.license && (
                    <DetailRow label="License" value={String(meeting.source_metadata.license)} />
                  )}
                  {meeting.source_metadata?.imported_at && (
                    <DetailRow label="Imported" value={formatDateTime(String(meeting.source_metadata.imported_at))} />
                  )}
                  {meeting.source_url && (
                    <div className="flex items-center justify-between gap-3 pt-1">
                      <dt className="shrink-0 text-muted">Original</dt>
                      <a
                        href={meeting.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex min-w-0 items-center gap-1 truncate font-medium text-brand-600 hover:text-brand-700"
                      >
                        <span className="truncate">Open original</span>
                        <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                      </a>
                    </div>
                  )}
                </dl>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>File details</CardTitle>
            </CardHeader>
            <CardBody>
              {current ? (
                <dl className="space-y-2 text-sm">
                  <DetailRow label="Original name" value={current.original_filename || "—"} />
                  <DetailRow label="Type" value={current.content_type || current.file_extension.toUpperCase() || "—"} />
                  <DetailRow label="Size" value={formatBytes(current.size_bytes)} />
                  <DetailRow label="Duration" value={formatDuration(meeting.duration_seconds)} />
                  {meta?.sample_rate && <DetailRow label="Sample rate" value={`${meta.sample_rate} Hz`} />}
                  {meta?.channels != null && <DetailRow label="Channels" value={String(meta.channels)} />}
                  {meta?.audio_codec && <DetailRow label="Audio codec" value={meta.audio_codec} />}
                  {meta?.video_codec && <DetailRow label="Video codec" value={meta.video_codec} />}
                  <DetailRow
                    label="Checksum"
                    value={current.checksum_sha256 ? `${current.checksum_sha256.slice(0, 12)}…` : "—"}
                    mono
                  />
                </dl>
              ) : (
                <p className="py-4 text-center text-sm text-muted">No file uploaded.</p>
              )}
            </CardBody>
          </Card>

          {meeting.files.length > 1 && (
            <Card>
              <CardHeader className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-brand-600" />
                <CardTitle>Versions</CardTitle>
              </CardHeader>
              <CardBody>
                <ul className="space-y-2 text-sm">
                  {meeting.files.map((f) => (
                    <li key={f.id} className="flex items-center justify-between">
                      <button
                        onClick={() => handleDownload(f)}
                        className="text-left text-foreground/90 hover:text-brand-600"
                      >
                        v{f.version} · {formatBytes(f.size_bytes)}
                        {f.is_current && <span className="ml-2 text-xs text-brand-600">current</span>}
                      </button>
                      <span className="text-xs text-muted">{formatDateTime(f.uploaded_at ?? "")}</span>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Processing timeline</CardTitle>
            </CardHeader>
            <CardBody>
              {meeting.events.length === 0 ? (
                <EmptyState title="No activity yet" />
              ) : (
                <Timeline events={meeting.events} />
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className={mono ? "text-right font-mono text-xs text-foreground/90" : "text-right text-foreground/90 break-all"}>
        {value}
      </dd>
    </div>
  );
}
