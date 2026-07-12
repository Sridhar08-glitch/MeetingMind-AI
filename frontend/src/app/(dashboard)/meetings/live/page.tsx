"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AudioLines,
  Circle,
  Loader2,
  Mic,
  Monitor,
  Pause,
  Play,
  ScreenShare,
  Square,
  Video,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Alert } from "@/components/ui/Feedback";
import { Markdown } from "@/components/ui/Markdown";
import { liveApi } from "@/lib/api/live";
import { cn, formatTimestamp } from "@/lib/utils";
import { usePreferencesStore } from "@/store/preferences";
import { usePageTitle } from "@/hooks/usePageTitle";
import { useRecorder, type LiveSource } from "@/hooks/useRecorder";

const SOURCES: { id: LiveSource; label: string; hint: string; icon: typeof Mic }[] = [
  { id: "mic", label: "Microphone", hint: "Your voice", icon: Mic },
  { id: "tab", label: "Browser tab", hint: "Share a tab + its audio", icon: ScreenShare },
  { id: "screen", label: "Screen / desktop", hint: "Screen + system audio", icon: Monitor },
  { id: "webcam_mic", label: "Webcam + mic", hint: "Camera and your voice", icon: Video },
  { id: "webcam", label: "Webcam only", hint: "Camera", icon: Video },
];

export default function LiveMeetingPage() {
  usePageTitle("Live meeting");
  const router = useRouter();
  const prefs = usePreferencesStore();
  const recorder = useRecorder();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [source, setSource] = useState<LiveSource>("mic");
  const [title, setTitle] = useState("");
  const [meetingLanguage, setMeetingLanguage] = useState(prefs.meetingLanguage);
  const [transcriptLanguage, setTranscriptLanguage] = useState(prefs.transcriptLanguage);
  const [aiLanguage, setAiLanguage] = useState(prefs.aiLanguage);
  const [remember, setRemember] = useState(prefs.rememberLanguages);

  const caps = useQuery({ queryKey: ["live-languages"], queryFn: () => liveApi.languages(), staleTime: 5 * 60_000 });

  const isSetup = recorder.status === "idle" || recorder.status === "error";
  const isLive = ["connecting", "recording", "paused", "finalizing"].includes(recorder.status);

  // Attach the media stream to the preview element when recording video.
  useEffect(() => {
    if (videoRef.current && recorder.stream && recorder.mediaKind === "video") {
      videoRef.current.srcObject = recorder.stream;
    }
  }, [recorder.stream, recorder.mediaKind]);

  // On finalize completion, jump to the canonical meeting detail page.
  useEffect(() => {
    if (recorder.status === "completed" && recorder.meetingId) {
      router.push(`/meetings/${recorder.meetingId}`);
    }
  }, [recorder.status, recorder.meetingId, router]);

  // Warn before a browser close/refresh while recording. (In-app navigation is
  // safe — the server auto-finalizes the recording into a queued meeting.)
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (["connecting", "recording", "paused"].includes(recorder.status)) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [recorder.status]);

  const begin = () => {
    if (remember) {
      prefs.setLanguages({ meetingLanguage, transcriptLanguage, aiLanguage });
      prefs.setRememberLanguages(true);
    }
    recorder.start(
      source,
      { meeting_language: meetingLanguage, transcript_language: transcriptLanguage, ai_language: aiLanguage },
      title.trim(),
    );
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Live meeting</h1>
        <p className="mt-1 text-sm text-muted">
          Record live and watch the transcript &amp; AI update in real time. Everything runs locally.
        </p>
      </div>

      {recorder.error && <Alert>{recorder.error}</Alert>}

      {isSetup ? (
        <SetupView
          caps={caps.data}
          source={source}
          setSource={setSource}
          title={title}
          setTitle={setTitle}
          meetingLanguage={meetingLanguage}
          setMeetingLanguage={setMeetingLanguage}
          transcriptLanguage={transcriptLanguage}
          setTranscriptLanguage={setTranscriptLanguage}
          aiLanguage={aiLanguage}
          setAiLanguage={setAiLanguage}
          remember={remember}
          setRemember={setRemember}
          onStart={begin}
        />
      ) : (
        <LiveView recorder={recorder} videoRef={videoRef} isLive={isLive} />
      )}
    </div>
  );
}

function langOptions(map: Record<string, string> | undefined): [string, string][] {
  if (!map) return [];
  return Object.entries(map).sort((a, b) => a[1].localeCompare(b[1]));
}

function SetupView(props: {
  caps: Awaited<ReturnType<typeof liveApi.languages>> | undefined;
  source: LiveSource;
  setSource: (s: LiveSource) => void;
  title: string;
  setTitle: (s: string) => void;
  meetingLanguage: string;
  setMeetingLanguage: (s: string) => void;
  transcriptLanguage: string;
  setTranscriptLanguage: (s: string) => void;
  aiLanguage: string;
  setAiLanguage: (s: string) => void;
  remember: boolean;
  setRemember: (b: boolean) => void;
  onStart: () => void;
}) {
  const { caps } = props;
  const selectCls =
    "h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Source</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-3">
            {SOURCES.map((s) => (
              <button
                key={s.id}
                onClick={() => props.setSource(s.id)}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-xl border p-4 text-center transition-colors",
                  props.source === s.id
                    ? "border-brand-400 bg-brand-50 text-brand-700"
                    : "border-border bg-surface text-muted hover:text-foreground",
                )}
              >
                <s.icon className="h-6 w-6" />
                <span className="text-sm font-medium text-foreground">{s.label}</span>
                <span className="text-xs text-muted">{s.hint}</span>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Language</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <Field label="Meeting Language (input)" hint="What's being spoken.">
            <select value={props.meetingLanguage} onChange={(e) => props.setMeetingLanguage(e.target.value)} className={selectCls}>
              {caps?.detect && <option value="">🌐 Auto Detect (recommended)</option>}
              {langOptions(caps?.transcription).map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </select>
          </Field>

          <Field label="Transcript Language" hint="Keep the original, or translate it.">
            <select value={props.transcriptLanguage} onChange={(e) => props.setTranscriptLanguage(e.target.value)} className={selectCls}>
              <option value="original">Original language</option>
              {langOptions(caps?.transcript_targets).map(([code, name]) => (
                <option key={code} value={code}>Translate to {name}</option>
              ))}
            </select>
          </Field>

          <Field label="AI Output Language" hint="Summary, tasks, decisions, chat, reports, agents…">
            <select value={props.aiLanguage} onChange={(e) => props.setAiLanguage(e.target.value)} className={selectCls}>
              <option value="">Same as transcript</option>
              {langOptions(caps?.ai_output).map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </select>
          </Field>

          <label className="flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={props.remember} onChange={(e) => props.setRemember(e.target.checked)} className="h-4 w-4 accent-brand-600" />
            Remember these language settings
          </label>
        </CardBody>
      </Card>

      <Card>
        <CardBody className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex-1">
            <Field label="Title (optional)" htmlFor="live-title">
              <input
                id="live-title"
                value={props.title}
                onChange={(e) => props.setTitle(e.target.value)}
                placeholder="Live meeting"
                className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
              />
            </Field>
          </div>
          <Button size="lg" onClick={props.onStart}>
            <Circle className="h-4 w-4 fill-current" /> Start recording
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}

function LiveView({
  recorder,
  videoRef,
  isLive,
}: {
  recorder: ReturnType<typeof useRecorder>;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  isLive: boolean;
}) {
  const mmss = useMemo(() => {
    const m = Math.floor(recorder.elapsed / 60);
    const s = recorder.elapsed % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }, [recorder.elapsed]);

  return (
    <div className="space-y-6">
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className={cn("flex h-3 w-3 rounded-full", recorder.status === "recording" ? "animate-pulse bg-danger" : "bg-muted")} />
            <span className="font-mono text-lg font-semibold text-foreground">{mmss}</span>
            <span className="text-sm capitalize text-muted">
              {recorder.status === "finalizing" ? "Finalizing…" : recorder.status}
            </span>
          </div>
          {/* Level meter */}
          <div className="flex flex-1 items-center gap-2 sm:max-w-xs">
            <AudioLines className="h-4 w-4 text-muted" />
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-brand-500 transition-[width] duration-75" style={{ width: `${Math.round(recorder.level * 100)}%` }} />
            </div>
          </div>
          <div className="flex gap-2">
            {recorder.status === "recording" && (
              <Button variant="outline" size="sm" onClick={recorder.pause}>
                <Pause className="h-4 w-4" /> Pause
              </Button>
            )}
            {recorder.status === "paused" && (
              <Button variant="outline" size="sm" onClick={recorder.resume}>
                <Play className="h-4 w-4" /> Resume
              </Button>
            )}
            <Button variant="danger" size="sm" onClick={recorder.stop} disabled={recorder.status === "finalizing"}>
              {recorder.status === "finalizing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
              Stop &amp; process
            </Button>
          </div>
        </CardBody>
      </Card>

      <p className="-mt-3 px-1 text-xs text-muted">
        Your recording is safe — if you navigate away it&apos;s saved and queued for processing automatically.
      </p>

      {recorder.mediaKind === "video" && (
        <Card>
          <CardBody>
            <video ref={videoRef} autoPlay muted playsInline className="max-h-[320px] w-full rounded-lg bg-black" />
          </CardBody>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Live transcript</CardTitle>
          </CardHeader>
          <CardBody>
            {recorder.segments.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted">
                {isLive ? "Listening… transcript will stream in as you speak." : "No transcript."}
              </p>
            ) : (
              <div className="max-h-[420px] space-y-2 overflow-y-auto scrollbar-thin pr-2">
                {recorder.segments.map((seg) => (
                  <div key={`${seg.index}-${seg.start}`} className="flex gap-3">
                    <span className="shrink-0 pt-0.5 font-mono text-xs text-brand-500">{formatTimestamp(seg.start)}</span>
                    <div className="flex-1">
                      <p className="text-sm text-foreground/90">{seg.text}</p>
                      {seg.translated_text && <p className="mt-0.5 text-sm text-brand-600">{seg.translated_text}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Live AI</CardTitle>
          </CardHeader>
          <CardBody>
            {recorder.liveAI?.executive_summary ? (
              <div className="space-y-3 text-sm">
                <Markdown className="text-foreground/90">{recorder.liveAI.executive_summary}</Markdown>
                {Array.isArray(recorder.liveAI.action_items) && recorder.liveAI.action_items.length > 0 && (
                  <p className="text-xs text-muted">{recorder.liveAI.action_items.length} action item(s) detected</p>
                )}
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted">
                AI updates every ~30s while you record. The full analysis runs when you stop.
              </p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
