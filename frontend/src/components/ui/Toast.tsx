"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

import { useToastStore, type Toast } from "@/store/toast";
import { cn } from "@/lib/utils";

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
} as const;

const STYLES: Record<Toast["variant"], string> = {
  success: "border-success/30 bg-success-bg text-success",
  error: "border-danger/30 bg-danger-bg text-danger",
  info: "border-brand-200 bg-brand-50 text-brand-700",
};

function ToastCard({ toast }: { toast: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss);
  const router = useRouter();
  const Icon = ICONS[toast.variant];

  useEffect(() => {
    if (!toast.duration) return;
    const t = setTimeout(() => dismiss(toast.id), toast.duration);
    return () => clearTimeout(t);
  }, [toast.id, toast.duration, dismiss]);

  const clickable = Boolean(toast.href);

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={
        clickable
          ? () => {
              router.push(toast.href!);
              dismiss(toast.id);
            }
          : undefined
      }
      className={cn(
        "pointer-events-auto flex w-80 items-start gap-3 rounded-xl border px-4 py-3 shadow-lg motion-safe:animate-[slideInLeft_180ms_ease-out]",
        STYLES[toast.variant],
        clickable && "cursor-pointer hover:brightness-[0.98]",
      )}
    >
      <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{toast.title}</p>
        {toast.message && <p className="mt-0.5 text-xs text-muted">{toast.message}</p>}
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          dismiss(toast.id);
        }}
        className="rounded p-0.5 text-muted hover:bg-black/5 hover:text-foreground"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

/** Fixed bottom-right stack of toasts. Mounted once in the dashboard layout. */
export function ToastViewport() {
  const toasts = useToastStore((s) => s.toasts);
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} />
      ))}
    </div>
  );
}
