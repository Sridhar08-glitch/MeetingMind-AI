"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { liveSocketUrl, type LiveLanguageConfig } from "@/lib/api/live";

export type RecorderStatus =
  | "idle"
  | "connecting"
  | "recording"
  | "paused"
  | "finalizing"
  | "completed"
  | "error";

export type LiveSource = "mic" | "screen" | "tab" | "webcam" | "webcam_mic";

export interface LiveSegment {
  index: number;
  start: number;
  end: number;
  text: string;
  translated_text?: string;
  speaker: string;
  confidence: number | null;
}

export interface LiveAI {
  executive_summary?: string;
  action_items?: unknown[];
  decisions?: unknown[];
  risks?: unknown[];
  keywords?: Record<string, unknown>;
}

const TIMESLICE_MS = 4000;

function pickMimeType(video: boolean): string {
  const candidates = video
    ? ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"]
    : ["audio/webm;codecs=opus", "audio/webm"];
  for (const c of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(c)) return c;
  }
  return video ? "video/webm" : "audio/webm";
}

async function captureStream(source: LiveSource): Promise<MediaStream> {
  const md = navigator.mediaDevices;
  switch (source) {
    case "mic":
      return md.getUserMedia({ audio: true });
    case "webcam":
      return md.getUserMedia({ video: true });
    case "webcam_mic":
      return md.getUserMedia({ video: true, audio: true });
    case "screen":
    case "tab":
      // The browser picker lets the user choose a tab/window/screen + its audio.
      return md.getDisplayMedia({ video: true, audio: true });
    default:
      return md.getUserMedia({ audio: true });
  }
}

export function useRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [segments, setSegments] = useState<LiveSegment[]>([]);
  const [liveAI, setLiveAI] = useState<LiveAI | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [meetingId, setMeetingId] = useState<string | null>(null);
  const [mediaKind, setMediaKind] = useState<"audio" | "video">("audio");
  const [stream, setStream] = useState<MediaStream | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef<number>(0);
  const pausedMsRef = useRef<number>(0);

  const cleanup = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close().catch(() => {});
    wsRef.current?.close();
    rafRef.current = null;
    timerRef.current = null;
    recorderRef.current = null;
    streamRef.current = null;
    audioCtxRef.current = null;
    setStream(null);
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const monitorLevel = useCallback((stream: MediaStream) => {
    if (stream.getAudioTracks().length === 0) return;
    try {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      const buf = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 3));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      /* level meter is optional */
    }
  }, []);

  const start = useCallback(
    async (source: LiveSource, langs: LiveLanguageConfig, title = "") => {
      setError(null);
      setSegments([]);
      setLiveAI(null);
      setMeetingId(null);
      setElapsed(0);
      setStatus("connecting");
      try {
        const mediaStream = await captureStream(source);
        streamRef.current = mediaStream;
        setStream(mediaStream);
        const hasVideo = mediaStream.getVideoTracks().length > 0;
        setMediaKind(hasVideo ? "video" : "audio");
        monitorLevel(mediaStream);

        const ws = new WebSocket(liveSocketUrl());
        wsRef.current = ws;
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          ws.send(
            JSON.stringify({
              type: "start",
              source,
              media_kind: hasVideo ? "video" : "audio",
              title,
              meeting_language: langs.meeting_language,
              transcript_language: langs.transcript_language,
              ai_language: langs.ai_language,
              file_extension: "webm",
            }),
          );
          const mime = pickMimeType(hasVideo);
          const rec = new MediaRecorder(mediaStream, { mimeType: mime });
          recorderRef.current = rec;
          rec.ondataavailable = (e) => {
            if (e.data && e.data.size > 0 && ws.readyState === WebSocket.OPEN) ws.send(e.data);
          };
          rec.start(TIMESLICE_MS);
          startedAtRef.current = Date.now();
          pausedMsRef.current = 0;
          timerRef.current = setInterval(() => {
            if (recorderRef.current?.state === "recording") {
              setElapsed(Math.floor((Date.now() - startedAtRef.current - pausedMsRef.current) / 1000));
            }
          }, 500);
        };

        ws.onmessage = (ev) => {
          if (typeof ev.data !== "string") return;
          const msg = JSON.parse(ev.data);
          switch (msg.type) {
            case "started":
              setStatus("recording");
              break;
            case "transcript":
              setSegments((prev) => [...prev, ...(msg.segments as LiveSegment[])]);
              break;
            case "ai":
              setLiveAI(msg.ai as LiveAI);
              break;
            case "status":
              setStatus(msg.status === "paused" ? "paused" : "recording");
              break;
            case "finalizing":
              setStatus("finalizing");
              break;
            case "completed":
              setMeetingId(msg.meeting_id);
              setStatus("completed");
              cleanup();
              break;
            case "error":
              setError(msg.message);
              setStatus("error");
              break;
          }
        };

        ws.onerror = () => {
          setError("Live connection failed.");
          setStatus("error");
        };
      } catch (e) {
        setError(
          e instanceof DOMException && e.name === "NotAllowedError"
            ? "Permission denied. Allow microphone/screen access to record."
            : "Could not start recording.",
        );
        setStatus("error");
        cleanup();
      }
    },
    [cleanup, monitorLevel],
  );

  const pause = useCallback(() => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.pause();
      pausedMsRef.current += 0; // pause tracking handled by state check in timer
      wsRef.current?.send(JSON.stringify({ type: "pause" }));
      setStatus("paused");
    }
  }, []);

  const resume = useCallback(() => {
    if (recorderRef.current?.state === "paused") {
      recorderRef.current.resume();
      wsRef.current?.send(JSON.stringify({ type: "resume" }));
      setStatus("recording");
    }
  }, []);

  const stop = useCallback(() => {
    setStatus("finalizing");
    try {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.requestData();
        recorderRef.current.stop();
      }
    } catch {
      /* ignore */
    }
    wsRef.current?.send(JSON.stringify({ type: "stop" }));
  }, []);

  return {
    status,
    error,
    segments,
    liveAI,
    elapsed,
    level,
    meetingId,
    mediaKind,
    stream,
    start,
    pause,
    resume,
    stop,
  };
}
