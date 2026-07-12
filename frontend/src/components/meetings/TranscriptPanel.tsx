"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronRight, Download, GripHorizontal, Pencil, Play, RotateCcw, Search, X } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { getApiErrorMessage } from "@/lib/api/client";
import { meetingsApi } from "@/lib/api/meetings";
import { cn, formatTimestamp } from "@/lib/utils";
import type { TranscriptFormat, TranscriptSegment } from "@/lib/types";
import { meetingKeys, useTranscript } from "@/hooks/useMeetings";
import { SpeakersPanel } from "@/components/meetings/SpeakersPanel";

const FORMATS: TranscriptFormat[] = ["txt", "md", "srt", "vtt", "json"];

interface TranscriptPanelProps {
  meetingId: string;
  processing: boolean;
  /** Playback position from the media player (seconds) — drives speaker highlight. */
  currentTime?: number;
  /** Seek the media player to a timestamp (seconds). */
  onSeek?: (t: number) => void;
}

interface SpeakerGroup {
  key: number;
  speaker: string;
  segments: TranscriptSegment[];
}

export function TranscriptPanel({ meetingId, processing, currentTime, onSeek }: TranscriptPanelProps) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useTranscript(meetingId, { poll: processing });
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [height, setHeight] = useState(560);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [showTranslated, setShowTranslated] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: meetingKeys.transcript(meetingId) });
    queryClient.invalidateQueries({ queryKey: meetingKeys.detail(meetingId) });
  };

  const editMutation = useMutation({
    mutationFn: ({ segId, text }: { segId: string; text: string }) =>
      meetingsApi.editSegment(meetingId, segId, text),
    onSuccess: () => { setEditingId(null); invalidate(); },
  });
  const restoreMutation = useMutation({
    mutationFn: (segId: string) => meetingsApi.restoreSegment(meetingId, segId),
    onSuccess: invalidate,
  });

  const transcript = data?.transcript ?? null;
  const segments = useMemo(() => data?.segments ?? [], [data]);
  const speakers = useMemo(() => data?.speakers ?? [], [data]);
  const editedCount = segments.filter((s) => s.is_edited).length;

  const filtered = useMemo(() => {
    if (!query.trim()) return segments;
    const q = query.toLowerCase();
    return segments.filter((s) => s.text.toLowerCase().includes(q) || s.speaker.toLowerCase().includes(q));
  }, [segments, query]);

  // The segment currently being spoken (for speaker highlight).
  const activeIndex = useMemo(() => {
    if (currentTime == null) return -1;
    const hit = segments.find((s) => currentTime >= s.start_time && currentTime < s.end_time);
    return hit ? hit.index : -1;
  }, [segments, currentTime]);

  // Consecutive same-speaker runs become collapsible groups (only when not searching).
  const groups = useMemo<SpeakerGroup[]>(() => {
    const out: SpeakerGroup[] = [];
    let key = 0;
    for (const seg of segments) {
      const last = out[out.length - 1];
      if (last && last.speaker === (seg.speaker || "")) last.segments.push(seg);
      else out.push({ key: key++, speaker: seg.speaker || "", segments: [seg] });
    }
    return out;
  }, [segments]);

  // Follow the active segment while playing — scroll only *within* the transcript
  // box (not the whole page), and only when the segment is out of view.
  useEffect(() => {
    if (activeIndex < 0) return;
    const container = listRef.current;
    const el = document.getElementById(`segment-${activeIndex}`);
    if (!container || !el) return;
    const c = container.getBoundingClientRect();
    const e = el.getBoundingClientRect();
    if (e.top < c.top || e.bottom > c.bottom) {
      container.scrollTop += e.top - c.top - container.clientHeight / 2 + el.clientHeight / 2;
    }
  }, [activeIndex]);

  const download = async (fmt: TranscriptFormat) => {
    try {
      const blob = await meetingsApi.downloadTranscript(meetingId, fmt);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `transcript.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(getApiErrorMessage(e, "Download failed."));
    }
  };

  const startEdit = (seg: TranscriptSegment) => {
    setEditingId(seg.id);
    setDraft(seg.text);
  };

  const toggleGroup = (key: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // Drag-to-resize the scroll area height.
  const onResizeStart = (e: React.PointerEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = height;
    const move = (ev: PointerEvent) => setHeight(Math.min(1200, Math.max(220, startH + (ev.clientY - startY))));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const renderSegment = (seg: TranscriptSegment, showSpeaker: boolean) => (
    <div
      key={seg.id}
      id={`segment-${seg.index}`}
      className={cn(
        "group flex scroll-mt-24 gap-3 rounded px-1 transition-colors",
        seg.index === activeIndex && "bg-brand-50 ring-1 ring-brand-200",
      )}
    >
      <button
        type="button"
        onClick={() => onSeek?.(seg.start_time)}
        disabled={!onSeek}
        title={onSeek ? "Play from here" : undefined}
        className={cn(
          "flex shrink-0 items-center gap-1 pt-1 font-mono text-xs text-brand-500",
          onSeek && "hover:text-brand-700",
        )}
      >
        {onSeek && <Play className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />}
        {formatTimestamp(seg.start_time)}
      </button>
      <div className="flex-1">
        {showSpeaker && seg.speaker && <p className="text-xs font-semibold text-foreground">{seg.speaker}</p>}
        {editingId === seg.id ? (
          <div className="space-y-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
              autoFocus
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => editMutation.mutate({ segId: seg.id, text: draft })}
                isLoading={editMutation.isPending}
                disabled={!draft.trim()}
              >
                <Check className="h-3.5 w-3.5" /> Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                <X className="h-3.5 w-3.5" /> Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p className={cn("text-sm text-foreground/90", seg.is_edited && "border-l-2 border-brand-300 pl-2")}>
            {highlight(showTranslated && seg.translated_text ? seg.translated_text : seg.text, query)}
            {seg.is_edited && <span className="ml-2 text-xs text-brand-500">(edited)</span>}
          </p>
        )}
      </div>
      {editingId !== seg.id && (
        <div className="flex shrink-0 items-start gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={() => startEdit(seg)}
            className="rounded p-1 text-muted hover:bg-slate-100 hover:text-foreground"
            aria-label="Edit segment"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          {seg.is_edited && (
            <button
              onClick={() => restoreMutation.mutate(seg.id)}
              className="rounded p-1 text-muted hover:bg-slate-100 hover:text-foreground"
              aria-label="Restore original"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle>Transcript</CardTitle>
        {transcript && (
          <div className="flex flex-wrap items-center gap-2">
            {transcript.target_language && transcript.translated_text && (
              <div className="flex overflow-hidden rounded-lg border border-border text-xs font-medium">
                <button
                  onClick={() => setShowTranslated(false)}
                  className={cn("px-2.5 py-1", !showTranslated ? "bg-brand-50 text-brand-700" : "text-muted hover:bg-slate-50")}
                >
                  Original
                </button>
                <button
                  onClick={() => setShowTranslated(true)}
                  className={cn("px-2.5 py-1 uppercase", showTranslated ? "bg-brand-50 text-brand-700" : "text-muted hover:bg-slate-50")}
                >
                  {transcript.target_language}
                </button>
              </div>
            )}
            {editedCount > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => { await meetingsApi.restoreTranscript(meetingId); invalidate(); }}
              >
                <RotateCcw className="h-3.5 w-3.5" /> Restore all ({editedCount})
              </Button>
            )}
            <div className="relative">
              <Button size="sm" variant="outline" onClick={() => setDownloadOpen((v) => !v)}>
                <Download className="h-3.5 w-3.5" /> Download
                <ChevronDown className="h-3.5 w-3.5" />
              </Button>
              {downloadOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setDownloadOpen(false)} />
                  <div className="absolute right-0 z-20 mt-1 w-40 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg">
                    {FORMATS.map((f) => (
                      <button
                        key={f}
                        onClick={() => {
                          download(f);
                          setDownloadOpen(false);
                        }}
                        className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm text-foreground hover:bg-slate-50"
                      >
                        <span>Transcript</span>
                        <span className="font-mono text-xs uppercase text-muted">.{f}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </CardHeader>

      {transcript && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 border-b border-border bg-slate-50/60 px-5 py-2.5 text-xs text-muted">
          <Metric label="Language" value={transcript.detected_language?.toUpperCase() || "—"} />
          <Metric label="Words" value={String(transcript.word_count)} />
          <Metric label="Confidence" value={pct(transcript.avg_confidence)} />
          <Metric label="Model" value={transcript.model_used || "—"} />
          <Metric label="Processing" value={ms(transcript.processing_ms)} />
          {transcript.transcription_speed != null && (
            <Metric label="Speed" value={`${transcript.transcription_speed}× real-time`} />
          )}
          <Metric label="Provider" value={transcript.provider} />
        </div>
      )}

      <CardBody>
        {isLoading ? (
          <p className="py-8 text-center text-sm text-muted">Loading transcript…</p>
        ) : !transcript || segments.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted">
            {processing ? "Transcribing… this updates automatically." : "No transcript yet."}
          </p>
        ) : (
          <>
            {speakers.length > 0 && (
              <div className="mb-4">
                <SpeakersPanel meetingId={meetingId} speakers={speakers} />
              </div>
            )}
            <div className="relative mb-4">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <Input
                className="pl-9"
                placeholder="Search the transcript…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>

            <div
              ref={listRef}
              className="space-y-3 overflow-y-auto scrollbar-thin pr-2"
              style={{ maxHeight: height }}
            >
              {query.trim() ? (
                filtered.length === 0 ? (
                  <p className="py-6 text-center text-sm text-muted">No segments match “{query}”.</p>
                ) : (
                  filtered.map((seg) => renderSegment(seg, true))
                )
              ) : (
                groups.map((g) => {
                  const isCollapsed = collapsed.has(g.key);
                  const first = g.segments[0];
                  const last = g.segments[g.segments.length - 1];
                  return (
                    <div key={g.key} className="space-y-2">
                      <button
                        onClick={() => toggleGroup(g.key)}
                        className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left hover:bg-slate-50"
                      >
                        {isCollapsed ? (
                          <ChevronRight className="h-3.5 w-3.5 text-muted" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-muted" />
                        )}
                        <span className="text-xs font-semibold text-foreground">{g.speaker || "Speaker"}</span>
                        <span className="font-mono text-[11px] text-muted">
                          {formatTimestamp(first.start_time)}–{formatTimestamp(last.end_time)}
                        </span>
                        {isCollapsed && (
                          <span className="text-[11px] text-muted">· {g.segments.length} lines</span>
                        )}
                      </button>
                      {!isCollapsed && (
                        <div className="space-y-2 pl-1">{g.segments.map((seg) => renderSegment(seg, false))}</div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Drag handle to resize the transcript height. */}
            <div
              onPointerDown={onResizeStart}
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize transcript"
              className="mt-1 flex cursor-ns-resize items-center justify-center rounded py-1 text-muted/50 hover:bg-slate-50 hover:text-muted"
            >
              <GripHorizontal className="h-4 w-4" />
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="text-muted/70">{label}:</span> <span className="font-medium text-foreground/80">{value}</span>
    </span>
  );
}

function pct(v: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}
function ms(v: number | null): string {
  if (!v) return "—";
  return v < 1000 ? `${v} ms` : `${(v / 1000).toFixed(1)} s`;
}

/** Highlight case-insensitive matches of `q` within `text`. */
function highlight(text: string, q: string) {
  if (!q.trim()) return text;
  const parts = text.split(new RegExp(`(${escapeRegExp(q)})`, "ig"));
  return parts.map((part, i) =>
    part.toLowerCase() === q.toLowerCase()
      ? <mark key={i} className="rounded bg-warning-bg px-0.5 text-warning">{part}</mark>
      : part,
  );
}
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
