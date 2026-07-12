"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Gavel, LayoutGrid, ListChecks } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { SkeletonList } from "@/components/ui/Feedback";
import { SuggestionCard } from "@/components/workspace/SuggestionCard";
import { TaskDrawer } from "@/components/workspace/TaskDrawer";
import { workspaceApi } from "@/lib/api/workspace";
import { cn } from "@/lib/utils";
import type { TaskStatus, WorkTask } from "@/lib/types";

const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "backlog", label: "Backlog" },
  { status: "todo", label: "To Do" },
  { status: "in_progress", label: "In Progress" },
  { status: "blocked", label: "Blocked" },
  { status: "review", label: "Review" },
  { status: "completed", label: "Completed" },
];

const PRIORITY: Record<string, string> = {
  critical: "border-l-danger", high: "border-l-warning", medium: "border-l-brand-400", low: "border-l-slate-300",
};

type Tab = "board" | "approvals" | "decisions" | "risks";

export default function WorkspacePage() {
  const [tab, setTab] = useState<Tab>("board");
  const analytics = useQuery({ queryKey: ["workspace", "analytics"], queryFn: () => workspaceApi.analytics() });

  const a = analytics.data;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Workspace</h1>
        <p className="mt-1 text-sm text-muted">Your AI-powered tasks, decisions, risks and reviews.</p>
      </div>

      {/* Analytics cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Open tasks" value={a?.open_tasks ?? 0} />
        <Stat label="Completed" value={a?.completed_tasks ?? 0} tone="success" />
        <Stat label="Blocked" value={a?.blocked_tasks ?? 0} tone="warning" />
        <Stat label="Overdue" value={a?.overdue_tasks ?? 0} tone="danger" />
        <Stat label="Completion rate" value={a ? `${a.task_completion_rate}%` : "—"} />
        <Stat label="Open risks" value={a?.open_risks ?? 0} tone="warning" />
        <Stat label="Open issues" value={a?.open_issues ?? 0} tone="danger" />
        <Stat label="Decisions" value={a?.decision_count ?? 0} tone="info" />
      </div>

      {a && a.most_discussed_topics.length > 0 && (
        <Card className="flex flex-wrap items-center gap-2 px-5 py-3">
          <span className="text-sm font-medium text-foreground">Most discussed:</span>
          {a.most_discussed_topics.slice(0, 8).map((t) => (
            <span key={t.topic} className="rounded-full bg-brand-50 px-2 py-0.5 text-xs text-brand-700">
              {t.topic} · {t.count}
            </span>
          ))}
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {([["board", "Board", LayoutGrid], ["approvals", "AI Approvals", ListChecks],
           ["decisions", "Decisions", Gavel], ["risks", "Risks", AlertTriangle]] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              "inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
              tab === id ? "border-brand-600 text-brand-700" : "border-transparent text-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "board" && <KanbanBoard />}
      {tab === "approvals" && <ApprovalQueue />}
      {tab === "decisions" && <DecisionsList />}
      {tab === "risks" && <RisksList />}
    </div>
  );
}

function KanbanBoard() {
  const queryClient = useQueryClient();
  const { data: board, isLoading } = useQuery({ queryKey: ["workspace", "board"], queryFn: () => workspaceApi.board() });
  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: TaskStatus }) => workspaceApi.moveTask(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspace", "board"] }),
  });
  const [dragId, setDragId] = useState<string | null>(null);
  const [openTask, setOpenTask] = useState<WorkTask | null>(null);

  if (isLoading) return <SkeletonList rows={6} />;
  const byStatus = Object.fromEntries((board ?? []).map((c) => [c.status, c.tasks]));

  return (
    <>
    {openTask && <TaskDrawer task={openTask} onClose={() => setOpenTask(null)} />}
    <div className="flex gap-3 overflow-x-auto pb-2">
      {COLUMNS.map((col) => (
        <div
          key={col.status}
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => { if (dragId) move.mutate({ id: dragId, status: col.status }); setDragId(null); }}
          className="flex w-64 shrink-0 flex-col rounded-xl border border-border bg-slate-50/60"
        >
          <div className="flex items-center justify-between px-3 py-2 text-sm font-semibold text-foreground">
            {col.label}
            <span className="rounded-full bg-surface px-1.5 text-xs text-muted">{(byStatus[col.status] ?? []).length}</span>
          </div>
          <div className="flex-1 space-y-2 p-2">
            {(byStatus[col.status] ?? []).map((t: WorkTask) => (
              <div
                key={t.id}
                draggable
                onDragStart={() => setDragId(t.id)}
                onClick={() => setOpenTask(t)}
                className={cn("cursor-pointer rounded-lg border border-l-4 border-border bg-surface p-2.5 text-sm shadow-sm hover:border-brand-300", PRIORITY[t.priority] ?? "border-l-slate-300")}
              >
                <p className="font-medium text-foreground">{t.title}</p>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  {t.assignee && <span className="rounded bg-slate-100 px-1.5">{t.assignee}</span>}
                  <span className="capitalize">{t.priority}</span>
                  {t.created_by_ai && <span className="text-brand-500">AI</span>}
                </div>
              </div>
            ))}
            {(byStatus[col.status] ?? []).length === 0 && <p className="px-1 py-3 text-center text-xs text-muted">—</p>}
          </div>
        </div>
      ))}
    </div>
    </>
  );
}

function ApprovalQueue() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const { data, isLoading } = useQuery({
    queryKey: ["workspace", "suggestions", "all-open"],
    queryFn: () => workspaceApi.suggestions(),
  });
  const stats = useQuery({ queryKey: ["workspace", "sug-stats"], queryFn: () => workspaceApi.suggestionStats() });
  const invalidate = () => { setSelected(new Set()); queryClient.invalidateQueries({ queryKey: ["workspace"] }); };
  const approve = useMutation({ mutationFn: (id: string) => workspaceApi.approve(id), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: (id: string) => workspaceApi.reject(id), onSuccess: invalidate });
  const bulk = useMutation({
    mutationFn: (action: "approve" | "reject" | "archive") => workspaceApi.bulk([...selected], action),
    onSuccess: invalidate,
  });

  if (isLoading) return <SkeletonList rows={6} />;
  const open = (data ?? []).filter((s) => ["pending", "needs_review", "edited"].includes(s.status));
  const toggle = (id: string) =>
    setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <div className="space-y-4">
      {/* Approval dashboard */}
      {stats.data && (
        <Card className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-3 text-sm">
          <span className="font-medium text-foreground">AI approval dashboard</span>
          <span className="text-muted">Pending: <b className="text-foreground">{stats.data.pending}</b></span>
          <span className="text-muted">Needs review: <b className="text-warning">{stats.data.needs_review}</b></span>
          <span className="text-muted">Avg confidence: <b className="text-foreground">{stats.data.average_confidence}%</b></span>
          <span className="text-muted">Approval rate: <b className="text-success">{stats.data.approval_rate}%</b></span>
          <span className="text-muted">Rejection rate: <b className="text-danger">{stats.data.rejection_rate}%</b></span>
        </Card>
      )}

      {selected.size > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-brand-100 bg-brand-50 px-4 py-2 text-sm">
          <span className="font-medium text-brand-700">{selected.size} selected</span>
          <Button size="sm" onClick={() => bulk.mutate("approve")} isLoading={bulk.isPending}>Approve selected</Button>
          <Button size="sm" variant="outline" onClick={() => bulk.mutate("reject")}>Reject selected</Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
        </div>
      )}

      {open.length === 0 ? (
        <Card className="px-5 py-12 text-center text-sm text-muted">No pending AI suggestions to review.</Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {open.map((s) => (
            <div key={s.id} className="flex gap-2">
              <input type="checkbox" className="mt-3" checked={selected.has(s.id)} onChange={() => toggle(s.id)} />
              <div className="flex-1">
                <SuggestionCard suggestion={s}
                  onApprove={() => approve.mutate(s.id)} onReject={() => reject.mutate(s.id)}
                  busy={approve.isPending || reject.isPending} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DecisionsList() {
  const { data, isLoading } = useQuery({ queryKey: ["workspace", "decisions"], queryFn: () => workspaceApi.decisions() });
  if (isLoading) return <SkeletonList rows={6} />;
  const rows = data ?? [];
  if (rows.length === 0) return <Card className="px-5 py-12 text-center text-sm text-muted">No decisions yet.</Card>;
  return (
    <div className="space-y-2">
      {rows.map((d) => (
        <Card key={d.id} className="px-4 py-3">
          <p className="text-sm font-medium text-foreground">{d.decision}</p>
          {d.reason && <p className="text-xs text-muted">Why: {d.reason}</p>}
          {d.participants?.length > 0 && <p className="text-xs text-muted">{d.participants.join(", ")}</p>}
        </Card>
      ))}
    </div>
  );
}

function RisksList() {
  const { data, isLoading } = useQuery({ queryKey: ["workspace", "risks"], queryFn: () => workspaceApi.risks() });
  if (isLoading) return <SkeletonList rows={6} />;
  const rows = data ?? [];
  if (rows.length === 0) return <Card className="px-5 py-12 text-center text-sm text-muted">No risks yet.</Card>;
  const sev: Record<string, string> = { critical: "bg-danger-bg text-danger", high: "bg-danger-bg text-danger", medium: "bg-warning-bg text-warning", low: "bg-slate-100 text-slate-600" };
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <Card key={r.id} className="flex items-start gap-3 px-4 py-3">
          <span className={cn("rounded px-1.5 py-0.5 text-xs capitalize", sev[r.severity] ?? "bg-slate-100")}>{r.severity}</span>
          <div>
            <p className="text-sm font-medium text-foreground">{r.risk}</p>
            {r.mitigation && <p className="text-xs text-muted">Mitigation: {r.mitigation}</p>}
          </div>
        </Card>
      ))}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: "success" | "warning" | "danger" | "info" }) {
  const toneMap = { success: "text-success", warning: "text-warning", danger: "text-danger", info: "text-info" };
  return (
    <Card className="px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={cn("mt-0.5 text-xl font-bold", tone ? toneMap[tone] : "text-foreground")}>{value}</p>
    </Card>
  );
}
