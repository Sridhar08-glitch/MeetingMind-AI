"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Link2,
  Loader2,
  Music,
  Sparkles,
  Video,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { getApiErrorMessage } from "@/lib/api/client";
import { liveApi } from "@/lib/api/live";
import { mediaApi } from "@/lib/api/media";
import { cn, formatDuration } from "@/lib/utils";
import type {
  AnalyzeResult,
  DuplicateAction,
  MediaImportSession,
  MediaImportStatus,
} from "@/lib/types";

const ACTIVE: MediaImportStatus[] = [
  "pending", "analyzing", "downloading", "downloaded", "validating", "importing", "processing",
];
const STATUS_LABEL: Record<MediaImportStatus, string> = {
  pending: "Queued", analyzing: "Analyzing", downloading: "Downloading", downloaded: "Downloaded",
  validating: "Validating", importing: "Importing", processing: "Processing", completed: "Completed",
  failed: "Failed", cancelled: "Cancelled", blocked: "Blocked",
};

function isActive(s: MediaImportSession) {
  return ACTIVE.includes(s.status);
}

export function UrlImportPanel() {
  const [urlsText, setUrlsText] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [results, setResults] = useState<AnalyzeResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [episodeSel, setEpisodeSel] = useState<Record<string, Set<string>>>({});
  const [reqMedia, setReqMedia] = useState<"audio" | "video">("video");
  const [meetingLang, setMeetingLang] = useState("");
  const [transcriptLang, setTranscriptLang] = useState("original");
  const [aiLang, setAiLang] = useState("");
  const [sessions, setSessions] = useState<MediaImportSession[]>([]);
  const [importing, setImporting] = useState(false);

  const langQ = useQuery({
    queryKey: ["languages"], queryFn: () => liveApi.languages(),
    staleTime: 5 * 60_000, retry: false,
  });
  const langs = langQ.data;

  const urls = useMemo(
    () => Array.from(new Set(urlsText.split("\n").map((u) => u.trim()).filter(Boolean))),
    [urlsText],
  );

  // Poll active import sessions until they reach a terminal state.
  useEffect(() => {
    if (!sessions.some(isActive)) return;
    const timer = setInterval(async () => {
      const active = sessions.filter(isActive);
      const updated = await Promise.all(active.map((s) => mediaApi.get(s.id).catch(() => s)));
      setSessions((prev) => prev.map((p) => updated.find((u) => u.id === p.id) ?? p));
    }, 2000);
    return () => clearInterval(timer);
  }, [sessions]);

  async function analyze() {
    if (!urls.length) return;
    setError(null);
    setAnalyzing(true);
    setResults([]);
    try {
      setResults(await mediaApi.analyze(urls));
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not analyze those URLs."));
    } finally {
      setAnalyzing(false);
    }
  }

  function toggleEpisode(url: string, id: string) {
    setEpisodeSel((prev) => {
      const set = new Set(prev[url] ?? []);
      if (set.has(id)) set.delete(id);
      else set.add(id);
      return { ...prev, [url]: set };
    });
  }

  async function importAll(onDuplicate: DuplicateAction = "reject") {
    setImporting(true);
    setError(null);
    const base = {
      requested_media: reqMedia, meeting_language: meetingLang,
      transcript_language: transcriptLang, ai_language: aiLang, on_duplicate: onDuplicate,
    };
    const created: MediaImportSession[] = [];
    for (const r of results) {
      if (!r.ok || !r.info) continue;
      try {
        if (r.info.is_playlist && r.info.episodes.length) {
          const sel = episodeSel[r.url] ?? new Set<string>();
          const chosen = r.info.episodes.filter((e) => sel.has(e.episode_id));
          const list = chosen.length ? chosen : [r.info.episodes[0]];
          for (const ep of list) {
            created.push(...(await mediaApi.import({ url: r.url, episode_id: ep.episode_id, title: ep.title, ...base })));
          }
        } else {
          created.push(...(await mediaApi.import({ url: r.url, title: r.info.title, ...base })));
        }
      } catch (e) {
        setError(getApiErrorMessage(e, "Some imports could not be started."));
      }
    }
    setSessions((prev) => [...created, ...prev]);
    setResults([]);
    setUrlsText("");
    setImporting(false);
  }

  async function reimport(session: MediaImportSession, action: DuplicateAction) {
    try {
      const next = await mediaApi.import({
        url: session.source_url,
        episode_id: session.episode_id || undefined,
        requested_media: session.requested_media,
        meeting_language: session.meeting_language,
        transcript_language: session.transcript_language,
        ai_language: session.ai_language,
        on_duplicate: action,
      });
      setSessions((prev) => prev.map((p) => (p.id === session.id ? next[0] ?? p : p)));
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not re-import."));
    }
  }

  const analyzedOk = results.filter((r) => r.ok).length;

  return (
    <div className="space-y-5">
      <Field
        label="Media URL(s)"
        htmlFor="import-urls"
        hint="Paste a YouTube/Vimeo link, a direct MP3/MP4 URL, or a podcast RSS feed. One per line to import several."
      >
        <textarea
          id="import-urls"
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          rows={3}
          placeholder={"https://www.youtube.com/watch?v=…\nhttps://example.com/episode.mp3"}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
        />
      </Field>

      <div className="flex items-center gap-2">
        <Button onClick={analyze} disabled={!urls.length || analyzing} isLoading={analyzing} variant="secondary">
          <Link2 className="h-4 w-4" /> Analyze {urls.length > 1 ? `${urls.length} URLs` : "URL"}
        </Button>
        <p className="text-xs text-muted">Only public content can be imported.</p>
      </div>

      {error && <Alert>{error}</Alert>}

      {/* Analyze previews */}
      {results.length > 0 && (
        <div className="space-y-3">
          {results.map((r) => (
            <PreviewCard
              key={r.url}
              result={r}
              selected={episodeSel[r.url] ?? new Set()}
              onToggleEpisode={(id) => toggleEpisode(r.url, id)}
            />
          ))}
        </div>
      )}

      {/* Import options + action */}
      {analyzedOk > 0 && (
        <div className="space-y-4 border-t border-border pt-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Download" htmlFor="req-media" hint="Video keeps the picture; audio is faster.">
              <select
                id="req-media" value={reqMedia}
                onChange={(e) => setReqMedia(e.target.value as "audio" | "video")}
                className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
              >
                <option value="video">Video + audio</option>
                <option value="audio">Audio only</option>
              </select>
            </Field>
            <LangSelect
              label="Meeting language" value={meetingLang} onChange={setMeetingLang}
              options={langs?.transcription ?? {}} autoLabel="Auto-detect"
            />
            <LangSelect
              label="Transcript language" value={transcriptLang} onChange={setTranscriptLang}
              options={langs?.transcript_targets ?? {}} autoValue="original" autoLabel="Keep original"
            />
            <LangSelect
              label="AI output language" value={aiLang} onChange={setAiLang}
              options={langs?.ai_output ?? {}} autoLabel="Same as transcript"
            />
          </div>
          <Button onClick={() => importAll("reject")} disabled={importing} isLoading={importing}>
            <Sparkles className="h-4 w-4" /> Import &amp; process
          </Button>
        </div>
      )}

      {/* Import progress */}
      {sessions.length > 0 && (
        <ul className="space-y-2 border-t border-border pt-4">
          {sessions.map((s) => (
            <ImportRow key={s.id} session={s} onReimport={reimport} />
          ))}
        </ul>
      )}
    </div>
  );
}

function LangSelect({
  label, value, onChange, options, autoValue = "", autoLabel,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Record<string, string>;
  autoValue?: string;
  autoLabel: string;
}) {
  return (
    <Field label={label} htmlFor={`lang-${label}`}>
      <select
        id={`lang-${label}`} value={value} onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
      >
        <option value={autoValue}>{autoLabel}</option>
        {Object.entries(options).map(([code, name]) => (
          <option key={code} value={code}>{name}</option>
        ))}
      </select>
    </Field>
  );
}

function PreviewCard({
  result, selected, onToggleEpisode,
}: {
  result: AnalyzeResult;
  selected: Set<string>;
  onToggleEpisode: (id: string) => void;
}) {
  if (!result.ok || !result.info) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-bg px-3 py-2 text-sm">
        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
        <div className="min-w-0">
          <p className="truncate text-foreground">{result.url}</p>
          <p className="text-xs text-danger">{result.error ?? "Could not analyze this URL."}</p>
        </div>
      </div>
    );
  }
  const info = result.info;
  const Icon = info.media_kind === "audio" ? Music : Video;
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="flex gap-3">
        {info.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={info.thumbnail_url} alt="" className="h-16 w-28 shrink-0 rounded-lg object-cover" />
        ) : (
          <div className="flex h-16 w-28 shrink-0 items-center justify-center rounded-lg bg-slate-100">
            <Icon className="h-6 w-6 text-brand-500" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">{info.title || result.url}</p>
          <p className="truncate text-xs text-muted">
            {[info.platform, info.author].filter(Boolean).join(" · ")}
          </p>
          <p className="mt-0.5 flex items-center gap-2 text-xs text-muted">
            {info.duration ? (
              <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> {formatDuration(info.duration)}</span>
            ) : null}
            {info.license ? <span>· {info.license}</span> : null}
            {info.is_playlist ? <span>· {info.episodes.length} episodes</span> : null}
          </p>
        </div>
      </div>

      {info.is_playlist && info.episodes.length > 0 && (
        <div className="mt-3 max-h-48 space-y-1 overflow-y-auto border-t border-border pt-2">
          <p className="text-xs font-medium text-muted">Choose episodes (defaults to the latest):</p>
          {info.episodes.map((ep) => (
            <label key={ep.episode_id} className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 hover:bg-slate-50">
              <input
                type="checkbox"
                checked={selected.has(ep.episode_id)}
                onChange={() => onToggleEpisode(ep.episode_id)}
                className="h-3.5 w-3.5 rounded border-border text-brand-600 focus:ring-brand-400"
              />
              <span className="min-w-0 flex-1 truncate text-xs text-foreground">{ep.title}</span>
              {ep.duration ? <span className="shrink-0 text-xs text-muted">{formatDuration(ep.duration)}</span> : null}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function ImportRow({
  session, onReimport,
}: {
  session: MediaImportSession;
  onReimport: (s: MediaImportSession, action: DuplicateAction) => void;
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
            session.status === "cancelled" && "bg-slate-100 text-muted",
          )}
        >
          {active && <Loader2 className="h-3 w-3 animate-spin" />}
          {done && <CheckCircle2 className="h-3 w-3" />}
          {failed && <XCircle className="h-3 w-3" />}
          {STATUS_LABEL[session.status]}
        </span>
      </div>

      {session.status === "downloading" && (
        <div className="mt-2 space-y-1">
          <div className="flex justify-between text-xs text-muted">
            <span>Downloading…</span>
            <span>{session.progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${session.progress}%` }} />
          </div>
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
            <Button size="sm" variant="secondary" onClick={() => onReimport(session, "replace")}>Reprocess</Button>
            <Button size="sm" variant="outline" onClick={() => onReimport(session, "keep_both")}>Keep both</Button>
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
