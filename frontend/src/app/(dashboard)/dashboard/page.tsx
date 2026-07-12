"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  Brain,
  CheckCircle2,
  Clock,
  LayoutGrid,
  Loader2,
  Mic,
  Pin,
  PinOff,
  Sparkles,
  TriangleAlert,
  UploadCloud,
} from "lucide-react";

import { Card, CardBody } from "@/components/ui/Card";
import { ProcessingBadge } from "@/components/ui/Badge";
import { SkeletonGrid, ErrorState, EmptyState } from "@/components/ui/Feedback";
import { getApiErrorMessage } from "@/lib/api/client";
import { agentsApi } from "@/lib/api/agents";
import { workspaceApi } from "@/lib/api/workspace";
import { meetingsApi } from "@/lib/api/meetings";
import { formatRelative } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { useDashboardStore } from "@/store/dashboard";
import { useDashboardStats } from "@/hooks/useMeetings";

const numberFmt = new Intl.NumberFormat();

const QUICK_ACTIONS = [
  { href: "/meetings/upload", label: "Upload", icon: UploadCloud, tint: "text-brand-600 bg-brand-50" },
  { href: "/knowledge", label: "Ask Knowledge", icon: Brain, tint: "text-info bg-info-bg" },
  { href: "/workspace", label: "Workspace", icon: LayoutGrid, tint: "text-success bg-success-bg" },
  { href: "/agents", label: "Run an agent", icon: Bot, tint: "text-warning bg-warning-bg" },
];

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading, isError, error, refetch } = useDashboardStats();
  const pinned = useDashboardStore((s) => s.pinned);
  const togglePin = useDashboardStore((s) => s.toggle);

  const recentUploads = useQuery({
    queryKey: ["dashboard-recent-uploads"],
    queryFn: () => meetingsApi.list({ ordering: "-created_at", page_size: 5 }),
  });
  const recentAI = useQuery({
    queryKey: ["dashboard-recent-ai"],
    queryFn: () => agentsApi.runs(),
  });
  const activity = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: () => workspaceApi.activity(8),
  });

  if (isLoading) return <SkeletonGrid count={6} />;
  if (isError || !data) {
    return <ErrorState title="Couldn't load your dashboard"
      description={getApiErrorMessage(error, "Could not load your dashboard.")} onRetry={() => refetch()} />;
  }

  const cards = [
    { label: "Total meetings", value: numberFmt.format(data.total_meetings), icon: Mic, tint: "text-brand-600 bg-brand-50" },
    { label: "Completed", value: numberFmt.format(data.completed_meetings), icon: CheckCircle2, tint: "text-success bg-success-bg" },
    { label: "Processing", value: numberFmt.format(data.processing_meetings), icon: Loader2, tint: "text-warning bg-warning-bg" },
    { label: "Failed jobs", value: numberFmt.format(data.failed_meetings), icon: TriangleAlert, tint: "text-danger bg-danger-bg" },
    { label: "Active jobs", value: numberFmt.format(data.active_jobs), icon: Activity, tint: "text-info bg-info-bg" },
    { label: "Hours processed", value: `${data.total_hours_processed}h`, icon: Clock, tint: "text-brand-600 bg-brand-50" },
  ];

  // Pinnable content widgets, rendered pinned-first.
  const widgets: { id: string; title: string; node: ReactNode }[] = [
    {
      id: "quick-actions",
      title: "Quick actions",
      node: (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {QUICK_ACTIONS.map((a) => (
            <Link
              key={a.href}
              href={a.href}
              className="flex flex-col items-center gap-2 rounded-xl border border-border bg-surface p-4 text-center transition-colors hover:border-brand-300 hover:bg-brand-50"
            >
              <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${a.tint}`}>
                <a.icon className="h-5 w-5" />
              </span>
              <span className="text-sm font-medium text-foreground">{a.label}</span>
            </Link>
          ))}
        </div>
      ),
    },
    {
      id: "recent-uploads",
      title: "Recent uploads",
      node: (
        <QueryList
          isLoading={recentUploads.isLoading}
          empty={(recentUploads.data?.results.length ?? 0) === 0}
          emptyText="No meetings uploaded yet."
        >
          {recentUploads.data?.results.map((m) => (
            <Link
              key={m.id}
              href={`/meetings/${m.id}`}
              className="flex items-center justify-between gap-3 rounded-lg px-2 py-2 hover:bg-slate-50"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-foreground">{m.title}</span>
                <span className="text-xs text-muted">{formatRelative(m.created_at)}</span>
              </span>
              <ProcessingBadge status={m.processing_status} />
            </Link>
          ))}
        </QueryList>
      ),
    },
    {
      id: "recent-ai",
      title: "Recent AI actions",
      node: (
        <QueryList
          isLoading={recentAI.isLoading}
          empty={(recentAI.data?.length ?? 0) === 0}
          emptyText="No AI activity yet."
        >
          {recentAI.data?.slice(0, 6).map((r) => (
            <div key={r.id} className="flex items-start gap-3 rounded-lg px-2 py-2">
              <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-foreground">{r.request}</span>
                <span className="text-xs text-muted">
                  {r.agent.replace(/_/g, " ")} · {formatRelative(r.created_at)}
                </span>
              </span>
            </div>
          ))}
        </QueryList>
      ),
    },
    {
      id: "activity",
      title: "Activity overview",
      node: (
        <QueryList
          isLoading={activity.isLoading}
          empty={(activity.data?.length ?? 0) === 0}
          emptyText="No recent activity."
        >
          {activity.data?.map((a) => (
            <div key={a.id} className="flex items-start gap-3 rounded-lg px-2 py-2">
              <Activity className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-foreground">{a.summary}</span>
                <span className="text-xs text-muted">{formatRelative(a.created_at)}</span>
              </span>
            </div>
          ))}
        </QueryList>
      ),
    },
  ];

  const orderedWidgets = [
    ...pinned.map((id) => widgets.find((w) => w.id === id)).filter((w): w is (typeof widgets)[number] => Boolean(w)),
    ...widgets.filter((w) => !pinned.includes(w.id)),
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Welcome back{user?.first_name ? `, ${user.first_name}` : ""}
          </h1>
          <p className="mt-1 text-sm text-muted">Here&apos;s an overview of your meeting activity.</p>
        </div>
        <Link
          href="/meetings"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-700"
        >
          <Mic className="h-4 w-4" />
          View meetings
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(({ label, value, icon: Icon, tint }) => (
          <Card key={label}>
            <CardBody className="flex items-center gap-4">
              <span className={`flex h-12 w-12 items-center justify-center rounded-xl ${tint}`}>
                <Icon className="h-6 w-6" />
              </span>
              <div>
                <p className="text-sm text-muted">{label}</p>
                <p className="text-2xl font-bold text-foreground">{value}</p>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {orderedWidgets.map((w) => {
          const isPinned = pinned.includes(w.id);
          return (
            <Card key={w.id} className={w.id === "quick-actions" ? "lg:col-span-2" : undefined}>
              <CardBody>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-foreground">{w.title}</h2>
                  <button
                    onClick={() => togglePin(w.id)}
                    aria-pressed={isPinned}
                    aria-label={isPinned ? `Unpin ${w.title}` : `Pin ${w.title}`}
                    className={isPinned ? "text-brand-600" : "text-muted hover:text-foreground"}
                    title={isPinned ? "Unpin" : "Pin to top"}
                  >
                    {isPinned ? <Pin className="h-4 w-4 fill-brand-600" /> : <PinOff className="h-4 w-4" />}
                  </button>
                </div>
                {w.node}
              </CardBody>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function QueryList({
  isLoading,
  empty,
  emptyText,
  children,
}: {
  isLoading: boolean;
  empty: boolean;
  emptyText: string;
  children: ReactNode;
}) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-9 animate-pulse rounded-lg bg-slate-100" />
        ))}
      </div>
    );
  }
  if (empty) {
    return <EmptyState title={emptyText} />;
  }
  return <div className="space-y-1">{children}</div>;
}
