"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, MessageSquare, Clock, X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { workspaceApi } from "@/lib/api/workspace";
import { formatDateTime } from "@/lib/utils";
import type { WorkTask } from "@/lib/types";

export function TaskDrawer({ task, onClose }: { task: WorkTask; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const related = useQuery({ queryKey: ["task", task.id, "related"], queryFn: () => workspaceApi.taskRelated(task.id) });
  const comments = useQuery({ queryKey: ["task", task.id, "comments"], queryFn: () => workspaceApi.taskComments(task.id) });
  const activity = useQuery({ queryKey: ["task", task.id, "activity"], queryFn: () => workspaceApi.taskActivity(task.id) });
  const addComment = useMutation({
    mutationFn: (body: string) => workspaceApi.addComment(task.id, body),
    onSuccess: () => {
      setComment("");
      queryClient.invalidateQueries({ queryKey: ["task", task.id] });
    },
  });

  type Related = {
    source_meeting?: { id: string; title: string };
    source_segment?: { text: string };
    decisions?: { id: string; decision: string }[];
    risks?: { id: string; risk: string }[];
  };
  const r = (related.data ?? {}) as Related;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-md overflow-y-auto bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-foreground">{task.title}</h2>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 capitalize">{task.status.replace("_", " ")}</span>
              <span className="capitalize">{task.priority}</span>
              {task.assignee && <span>· {task.assignee}</span>}
              {task.created_by_ai && <span className="text-brand-500">· AI</span>}
            </div>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-slate-100"><X className="h-4 w-4" /></button>
        </div>

        {task.description && <p className="mb-4 text-sm text-foreground/90">{task.description}</p>}

        {/* Explainability: why AI created it */}
        {task.created_by_ai && task.source_quote && (
          <div className="mb-4 rounded-lg bg-slate-50 p-3 text-xs text-muted">
            <p className="mb-1 font-semibold uppercase tracking-wide">Why AI created this</p>
            <p>{task.source_reason}</p>
            <p className="mt-1">Evidence: {task.source_speaker && <b>{task.source_speaker} </b>}“{task.source_quote.slice(0, 140)}”</p>
          </div>
        )}

        {/* Checklist */}
        {task.checklist?.length > 0 && (
          <Section title="Checklist">
            <ul className="space-y-1 text-sm">
              {task.checklist.map((c, i) => (
                <li key={i} className="flex items-center gap-2">
                  <input type="checkbox" defaultChecked={c.done} readOnly /> <span>{c.text}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Related items */}
        <Section title="Related" icon={<Link2 className="h-3.5 w-3.5" />}>
          <div className="space-y-1 text-sm text-foreground/90">
            {r.source_meeting && <p>Meeting: {r.source_meeting.title}</p>}
            {r.source_segment && <p className="text-xs text-muted">Transcript: “{String(r.source_segment.text).slice(0, 80)}”</p>}
            {(r.decisions ?? []).map((d) => <p key={d.id} className="text-xs">Decision: {d.decision?.slice(0, 60)}</p>)}
            {(r.risks ?? []).map((x) => <p key={x.id} className="text-xs">Risk: {x.risk?.slice(0, 60)}</p>)}
            {!r.source_meeting && <p className="text-xs text-muted">No linked meeting.</p>}
          </div>
        </Section>

        {/* Comments */}
        <Section title="Comments" icon={<MessageSquare className="h-3.5 w-3.5" />}>
          <div className="space-y-2">
            {(comments.data ?? []).map((c) => (
              <div key={c.id} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <p className="text-foreground/90">{c.body}</p>
                <p className="text-xs text-muted">{c.author} · {formatDateTime(c.created_at)}</p>
              </div>
            ))}
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (comment.trim()) addComment.mutate(comment); }}>
              <Input placeholder="Add a comment…" value={comment} onChange={(e) => setComment(e.target.value)} />
              <Button type="submit" size="sm" isLoading={addComment.isPending}>Post</Button>
            </form>
          </div>
        </Section>

        {/* Activity */}
        <Section title="Activity" icon={<Clock className="h-3.5 w-3.5" />}>
          <ol className="space-y-1 text-xs text-muted">
            {(activity.data ?? []).map((a) => (
              <li key={a.id}>{a.summary} · {formatDateTime(a.created_at)}</li>
            ))}
            {(activity.data ?? []).length === 0 && <li>No activity yet.</li>}
          </ol>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand-600">
        {icon} {title}
      </p>
      {children}
    </div>
  );
}
