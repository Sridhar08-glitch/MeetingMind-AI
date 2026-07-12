"use client";

import { useEffect } from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface ContextMenuItem {
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  danger?: boolean;
}

export interface ContextMenuState {
  x: number;
  y: number;
  items: ContextMenuItem[];
}

/** A right-click menu positioned at (x, y). Render it when state is non-null. */
export function ContextMenu({ x, y, items, onClose }: ContextMenuState & { onClose: () => void }) {
  useEffect(() => {
    const close = () => onClose();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
    };
  }, [onClose]);

  // Keep the menu inside the viewport.
  const left = Math.min(x, (typeof window !== "undefined" ? window.innerWidth : 9999) - 200);
  const top = Math.min(y, (typeof window !== "undefined" ? window.innerHeight : 9999) - items.length * 36 - 16);

  return (
    <div
      role="menu"
      style={{ top, left }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}
      className="fixed z-[60] min-w-44 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-xl motion-safe:animate-[popIn_120ms_ease-out]"
    >
      {items.map((it, i) => (
        <button
          key={i}
          role="menuitem"
          onClick={() => {
            it.onClick();
            onClose();
          }}
          className={cn(
            "flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm",
            it.danger ? "text-danger hover:bg-danger-bg" : "text-foreground hover:bg-slate-50",
          )}
        >
          {it.icon && <it.icon className="h-4 w-4 shrink-0" />}
          {it.label}
        </button>
      ))}
    </div>
  );
}
