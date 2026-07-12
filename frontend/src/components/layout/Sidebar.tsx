"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit } from "lucide-react";

import { cn } from "@/lib/utils";
import { NAV_ITEMS, activeHref } from "./nav";

export function Sidebar() {
  const pathname = usePathname();
  const active = activeHref(pathname);

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-surface lg:flex">
      <div className="flex h-16 items-center gap-2 border-b border-border px-6">
        <BrainCircuit className="h-6 w-6 text-brand-600" />
        <span className="text-lg font-semibold text-foreground">MeetingMind</span>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Primary">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={href === active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              href === active
                ? "bg-brand-50 text-brand-700"
                : "text-muted hover:bg-slate-50 hover:text-foreground",
            )}
          >
            <Icon className="h-5 w-5" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
