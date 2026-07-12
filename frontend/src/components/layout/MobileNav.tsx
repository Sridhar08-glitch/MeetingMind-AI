"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { NAV_ITEMS, activeHref } from "./nav";

/** Slide-in navigation drawer for < lg screens. Accessible dialog: focus-trapped,
 * ESC to close, backdrop click to close, motion-reduced friendly. */
export function MobileNav({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const active = activeHref(pathname);
  const panelRef = useRef<HTMLDivElement>(null);
  // Note: each nav link calls onClose on click, so the drawer closes on navigation.

  // Focus trap + ESC while open.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    panel?.querySelector<HTMLElement>("a,button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !panel) return;
      const focusable = panel.querySelectorAll<HTMLElement>("a,button");
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
      <div className="absolute inset-0 bg-slate-900/40 motion-safe:animate-[fadeIn_150ms_ease-out]" onClick={onClose} />
      <div
        ref={panelRef}
        className="absolute inset-y-0 left-0 flex w-72 max-w-[80vw] flex-col border-r border-border bg-surface shadow-xl motion-safe:animate-[slideInLeft_200ms_ease-out]"
      >
        <div className="flex h-16 items-center justify-between border-b border-border px-5">
          <span className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <BrainCircuit className="h-6 w-6 text-brand-600" /> MeetingMind
          </span>
          <button onClick={onClose} aria-label="Close navigation" className="rounded-lg p-1.5 text-muted hover:bg-slate-100 hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Primary">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              aria-current={href === active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                href === active ? "bg-brand-50 text-brand-700" : "text-foreground hover:bg-slate-50",
              )}
            >
              <Icon className="h-5 w-5" /> {label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
