import { CheckCircle2, CircleAlert, CircleDot } from "lucide-react";

import { cn, formatDateTime } from "@/lib/utils";
import type { MeetingEvent } from "@/lib/types";

const FAILURE_EVENTS = new Set(["validation_failed", "processing_failed"]);

function formatDuration(ms: number | null): string | null {
  if (ms == null) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Vertical processing timeline built from the meeting's structured event log. */
export function Timeline({ events }: { events: MeetingEvent[] }) {
  if (events.length === 0) {
    return <p className="py-6 text-center text-sm text-muted">No activity yet.</p>;
  }

  return (
    <ol className="relative space-y-4">
      {events.map((event, i) => {
        const isFailure = FAILURE_EVENTS.has(event.event_type);
        const isLast = i === events.length - 1;
        const Icon = isFailure ? CircleAlert : isLast ? CircleDot : CheckCircle2;
        const dur = formatDuration(event.duration_ms);
        return (
          <li key={event.id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  isFailure ? "text-danger" : isLast ? "text-brand-600" : "text-success",
                )}
                aria-hidden
              />
              {!isLast && <span className="mt-1 w-px flex-1 bg-border" />}
            </div>
            <div className="-mt-0.5 pb-1">
              <p className="text-sm font-medium text-foreground">
                {event.message || event.event_type_display}
              </p>
              <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted">
                <time>{formatDateTime(event.created_at)}</time>
                <span className="capitalize">· {event.source}</span>
                {dur && <span>· {dur}</span>}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
