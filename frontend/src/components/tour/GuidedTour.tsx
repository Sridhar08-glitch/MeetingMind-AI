"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useTourStore } from "@/store/tour";
import { useAuthStore } from "@/store/auth";

interface Step {
  title: string;
  body: string;
  /** Route to navigate to when this step opens (so the tour walks the product). */
  route?: string;
  cta?: string;
}

const STEPS: Step[] = [
  {
    title: "Welcome to MeetingMind AI",
    body:
      "This demo workspace is fully populated with realistic meetings, transcripts, AI summaries, decisions and tasks — no upload needed. Let's take a 30-second tour.",
    route: "/copilot",
    cta: "Start tour",
  },
  {
    title: "1 · Open a meeting",
    body:
      "This is your Meetings library — a mix of sprint plannings, standups, sales calls, interviews, executive reviews and design reviews (audio and video). Click any meeting to open it.",
    route: "/meetings",
  },
  {
    title: "2 · Review the AI summary",
    body:
      "Inside a meeting, the AI Review Center gives you an executive summary, action items, decisions, risks and keywords — every item grounded in the transcript, with a version history.",
  },
  {
    title: "3 · Ask the AI a question",
    body:
      "Open the chat panel on a meeting and ask anything, e.g. \"What did we decide about authentication?\" Answers are grounded and cite the exact transcript moments — click a citation to jump there.",
  },
  {
    title: "4 · Review action items",
    body:
      "The Workspace turns meeting outcomes into work. Approve AI-suggested tasks in the Approvals queue and track them on the Kanban board — decisions and risks are captured too.",
    route: "/workspace",
  },
  {
    title: "You're all set",
    body:
      "Explore the Knowledge Hub, Executive dashboard and AI Agents whenever you like. You can restart this tour or reset the demo anytime from Settings. Enjoy!",
    cta: "Finish",
  },
];

export function GuidedTour() {
  const router = useRouter();
  const hydrated = useAuthStore((s) => s.hydrated);
  const accessToken = useAuthStore((s) => s.accessToken);
  const { open, step, tourSeen, start, next, prev, skip, finish } = useTourStore();
  const cardRef = useRef<HTMLDivElement>(null);

  // Auto-start once, on first authenticated visit.
  useEffect(() => {
    if (hydrated && accessToken && !tourSeen && !open) start();
  }, [hydrated, accessToken, tourSeen, open, start]);

  const navigate = useCallback(
    (target: number) => {
      const route = STEPS[target]?.route;
      if (route) router.push(route);
    },
    [router],
  );

  const handleNext = useCallback(() => {
    if (step >= STEPS.length - 1) {
      finish();
      return;
    }
    const target = step + 1;
    navigate(target);
    next();
  }, [step, navigate, next, finish]);

  useEffect(() => {
    if (open) cardRef.current?.focus();
  }, [open, step]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") skip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, skip]);

  if (!open) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-900/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label="Product tour"
    >
      <div
        ref={cardRef}
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl border border-border bg-surface p-6 shadow-xl outline-none animate-[fadeUp_200ms_ease-out]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
              <Sparkles className="h-5 w-5" aria-hidden />
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-muted">
              Demo tour · {step + 1} of {STEPS.length}
            </span>
          </div>
          <button
            type="button"
            onClick={skip}
            aria-label="Skip tour"
            className="rounded-md p-1 text-muted hover:bg-slate-100 hover:text-foreground"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <h2 className="mt-4 text-lg font-semibold text-foreground">{current.title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">{current.body}</p>

        {/* progress dots */}
        <div className="mt-5 flex items-center gap-1.5" aria-hidden>
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={
                "h-1.5 rounded-full transition-all " +
                (i === step ? "w-6 bg-brand-600" : "w-1.5 bg-slate-200")
              }
            />
          ))}
        </div>

        <div className="mt-6 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={skip}
            className="text-sm font-medium text-muted hover:text-foreground"
          >
            Skip
          </button>
          <div className="flex items-center gap-2">
            {step > 0 && !isLast && (
              <Button variant="ghost" size="sm" onClick={prev}>
                Back
              </Button>
            )}
            <Button size="sm" onClick={handleNext}>
              {current.cta ?? "Next"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
