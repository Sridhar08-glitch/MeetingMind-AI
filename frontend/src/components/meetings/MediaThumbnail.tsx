import Image from "next/image";
import { AudioLines, Film } from "lucide-react";

import { cn } from "@/lib/utils";
import type { MediaKind } from "@/lib/types";

interface Props {
  thumbnailUrl?: string | null;
  mediaKind?: MediaKind;
  className?: string;
  alt?: string;
}

/**
 * Renders a video's first-frame thumbnail when available, otherwise a
 * kind-appropriate placeholder (a film reel for video, a waveform for audio).
 */
export function MediaThumbnail({ thumbnailUrl, mediaKind, className, alt = "" }: Props) {
  if (thumbnailUrl) {
    return (
      <div className={cn("relative overflow-hidden rounded-lg bg-slate-100", className)}>
        <Image src={thumbnailUrl} alt={alt} fill className="object-cover" unoptimized sizes="240px" />
      </div>
    );
  }

  const Icon = mediaKind === "video" ? Film : AudioLines;
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-lg bg-gradient-to-br from-brand-50 to-slate-100 text-brand-400",
        className,
      )}
      aria-hidden
    >
      <Icon className="h-8 w-8" />
    </div>
  );
}
