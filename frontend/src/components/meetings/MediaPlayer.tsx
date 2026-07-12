"use client";

import { useState } from "react";

import { meetingsApi } from "@/lib/api/meetings";
import type { MediaKind } from "@/lib/types";

interface MediaPlayerProps {
  meetingId: string;
  version?: number;
  mediaKind: MediaKind;
  /** Called with the underlying media element so the parent can seek it. */
  setMediaEl: (el: HTMLMediaElement | null) => void;
  /** Current playback position in seconds. */
  onTime: (t: number) => void;
}

/**
 * Plays a meeting recording by streaming from the Range-capable /stream endpoint.
 * The browser fetches only the bytes it needs (and can seek), so even multi-GB
 * recordings play without loading the whole file into memory — the old whole-file
 * blob download froze the page on large videos.
 */
export function MediaPlayer({ meetingId, version, mediaKind, setMediaEl, onTime }: MediaPlayerProps) {
  const [failed, setFailed] = useState(false);
  const src = meetingsApi.streamUrl(meetingId, version);

  if (failed) return null; // media can't be loaded — hide the player, keep the rest of the page

  if (mediaKind === "video") {
    return (
      <video
        ref={setMediaEl}
        src={src}
        controls
        preload="metadata"
        onError={() => setFailed(true)}
        onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)}
        className="max-h-[360px] w-full rounded-xl bg-black"
      />
    );
  }
  return (
    <audio
      ref={setMediaEl}
      src={src}
      controls
      preload="metadata"
      onError={() => setFailed(true)}
      onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)}
      className="w-full"
    />
  );
}
