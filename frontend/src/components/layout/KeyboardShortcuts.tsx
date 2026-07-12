"use client";

import { useEffect, useState } from "react";
import { Keyboard, X } from "lucide-react";

const SHORTCUTS: { keys: string[]; desc: string }[] = [
  { keys: ["Ctrl", "K"], desc: "Open the command palette" },
  { keys: ["/"], desc: "Search everything" },
  { keys: ["?"], desc: "Show this shortcuts help" },
  { keys: ["↑", "↓"], desc: "Move between results" },
  { keys: ["Enter"], desc: "Open the selected result" },
  { keys: ["Esc"], desc: "Close a dialog or panel" },
];

function isTypingTarget(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null;
  if (!node) return false;
  const tag = node.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || node.isContentEditable;
}

/** "?" opens a modal listing keyboard shortcuts. Mounted once in the shell. */
export function KeyboardShortcuts() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key === "?" && !isTypingTarget(e.target)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[58] flex items-center justify-center bg-slate-900/40 px-4 backdrop-blur-sm motion-safe:animate-[fadeIn_120ms_ease-out]"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-label="Keyboard shortcuts"
        className="w-full max-w-md overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Keyboard className="h-4 w-4 text-brand-500" />
            <h2 className="text-sm font-semibold text-foreground">Keyboard shortcuts</h2>
          </div>
          <button onClick={() => setOpen(false)} className="rounded p-1 text-muted hover:bg-slate-100" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <ul className="divide-y divide-border">
          {SHORTCUTS.map((s) => (
            <li key={s.desc} className="flex items-center justify-between px-5 py-2.5">
              <span className="text-sm text-foreground/90">{s.desc}</span>
              <span className="flex items-center gap-1">
                {s.keys.map((k) => (
                  <kbd
                    key={k}
                    className="rounded border border-border bg-slate-50 px-1.5 py-0.5 font-mono text-xs text-muted"
                  >
                    {k}
                  </kbd>
                ))}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
