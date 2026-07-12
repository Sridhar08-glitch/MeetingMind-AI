"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";

import { useRecentsStore } from "@/store/recents";

const SEGMENT_LABELS: Record<string, string> = {
  copilot: "Copilot",
  dashboard: "Dashboard",
  meetings: "Meetings",
  live: "Live",
  upload: "Upload",
  workspace: "Workspace",
  knowledge: "Knowledge Hub",
  graph: "Graph",
  exports: "Export Center",
  executive: "Executive",
  agents: "Agent Center",
  jobs: "Jobs",
  settings: "Settings",
};

function isIdLike(seg: string): boolean {
  return /^[0-9a-fA-F-]{16,}$/.test(seg) || seg.length > 20;
}

/** Path-derived breadcrumb trail shown in the topbar. */
export function Breadcrumbs() {
  const pathname = usePathname();
  const recents = useRecentsStore((s) => s.items);
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return null;

  const crumbs = segments.map((seg, i) => {
    const href = "/" + segments.slice(0, i + 1).join("/");
    let label = SEGMENT_LABELS[seg];
    if (!label && isIdLike(seg)) {
      // Prefer a friendly name we already know (e.g. a recently-opened meeting).
      label = recents.find((r) => r.id === seg)?.title ?? "Details";
    }
    if (!label) label = seg.charAt(0).toUpperCase() + seg.slice(1);
    return { href, label, isLast: i === segments.length - 1 };
  });

  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm">
      <Link href="/copilot" className="shrink-0 text-muted hover:text-foreground">
        Home
      </Link>
      {crumbs.map((c) => (
        <span key={c.href} className="flex min-w-0 items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted/60" aria-hidden />
          {c.isLast ? (
            <span className="truncate font-medium text-foreground" aria-current="page">
              {c.label}
            </span>
          ) : (
            <Link href={c.href} className="truncate text-muted hover:text-foreground">
              {c.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
