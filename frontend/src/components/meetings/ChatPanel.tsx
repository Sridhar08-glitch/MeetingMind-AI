"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquarePlus, Pencil, Quote, Send, Sparkles, Trash2 } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { getApiErrorMessage } from "@/lib/api/client";
import { chatApi } from "@/lib/api/chat";
import { cn, formatTimestamp } from "@/lib/utils";
import type { MessageCitation } from "@/lib/types";

function jumpToSegment(index: number) {
  const el = document.getElementById(`segment-${index}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("bg-warning-bg");
    setTimeout(() => el.classList.remove("bg-warning-bg"), 1600);
  }
}

export function ChatPanel({ meetingId }: { meetingId: string }) {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const conversations = useQuery({
    queryKey: ["chat", "list", meetingId],
    queryFn: () => chatApi.list(meetingId),
  });
  const suggested = useQuery({ queryKey: ["chat", "suggested"], queryFn: () => chatApi.suggested() });
  const conversation = useQuery({
    queryKey: ["chat", "detail", activeId],
    queryFn: () => chatApi.get(activeId!),
    enabled: Boolean(activeId),
  });

  const refetchAll = () => {
    queryClient.invalidateQueries({ queryKey: ["chat", "list", meetingId] });
    if (activeId) queryClient.invalidateQueries({ queryKey: ["chat", "detail", activeId] });
  };

  const createConv = useMutation({
    mutationFn: () => chatApi.create(meetingId),
    onSuccess: (c) => { setActiveId(c.id); refetchAll(); },
  });
  const ask = useMutation({
    // Take the conversation id explicitly — on the first question `activeId` state
    // is still null (setActiveId hasn't re-rendered yet), so reading it here would
    // POST to /conversations/null/ask/ → 404 "not found" on the first message.
    mutationFn: ({ id, question }: { id: string; question: string }) => chatApi.ask(id, question),
    onSuccess: () => refetchAll(),
  });
  const removeConv = useMutation({
    mutationFn: (id: string) => chatApi.remove(id),
    onSuccess: () => { setActiveId(null); refetchAll(); },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation.data?.messages.length, ask.isPending]);

  const send = async (question: string) => {
    const q = question.trim();
    if (!q) return;
    setDraft("");
    let id = activeId;
    if (!id) {
      const c = await createConv.mutateAsync();
      id = c.id;
    }
    ask.mutate({ id, question: q });
  };

  const messages = conversation.data?.messages ?? [];

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <MessageSquarePlus className="h-4 w-4 text-brand-600" /> Chat with this meeting
        </CardTitle>
        <Button size="sm" variant="outline" onClick={() => createConv.mutate()}>
          <MessageSquarePlus className="h-3.5 w-3.5" /> New chat
        </Button>
      </CardHeader>

      <div className="grid md:grid-cols-[200px_1fr]">
        {/* Conversation sidebar */}
        <div className="border-b border-border p-2 md:border-b-0 md:border-r">
          {conversations.data && conversations.data.length > 0 ? (
            <ul className="space-y-1">
              {conversations.data.map((c) => (
                <li key={c.id} className={cn(
                  "group flex items-center justify-between rounded-lg px-2 py-1.5 text-sm",
                  c.id === activeId ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50",
                )}>
                  <button className="min-w-0 flex-1 truncate text-left" onClick={() => setActiveId(c.id)}>
                    {c.title}
                  </button>
                  <span className="flex shrink-0 gap-0.5 opacity-0 group-hover:opacity-100">
                    <button
                      onClick={async () => {
                        const t = window.prompt("Rename conversation", c.title);
                        if (t) { await chatApi.rename(c.id, t); refetchAll(); }
                      }}
                      className="rounded p-1 text-muted hover:text-foreground" aria-label="Rename"
                    ><Pencil className="h-3 w-3" /></button>
                    <button onClick={() => removeConv.mutate(c.id)}
                      className="rounded p-1 text-muted hover:text-danger" aria-label="Delete"
                    ><Trash2 className="h-3 w-3" /></button>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2 py-4 text-xs text-muted">No conversations yet.</p>
          )}
        </div>

        {/* Messages */}
        <CardBody className="flex min-h-[320px] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto scrollbar-thin pr-1" style={{ maxHeight: 440 }}>
            {messages.length === 0 ? (
              <div className="py-6 text-center">
                <Sparkles className="mx-auto mb-2 h-6 w-6 text-brand-300" />
                <p className="text-sm text-muted">Ask anything about this meeting — answers are grounded in the transcript.</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {(suggested.data ?? []).map((q) => (
                    <button key={q} onClick={() => send(q)}
                      className="rounded-full border border-border px-3 py-1 text-xs text-foreground/80 hover:border-brand-300 hover:bg-brand-50">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                  <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2 text-sm",
                    m.role === "user" ? "bg-brand-600 text-white" : "bg-slate-100 text-foreground")}>
                    <p className="whitespace-pre-wrap">{m.content}</p>
                    {m.role === "assistant" && m.citations.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5 border-t border-slate-200 pt-2">
                        <Quote className="h-3 w-3 text-muted" />
                        {m.citations.map((c: MessageCitation) => (
                          <button key={c.id} onClick={() => jumpToSegment(c.index)}
                            title={c.snippet}
                            className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs text-brand-600 hover:bg-brand-50">
                            {formatTimestamp(c.start_time)}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            {ask.isPending && (
              <div className="flex justify-start">
                <div className="inline-flex items-center gap-2 rounded-2xl bg-slate-100 px-3.5 py-2 text-sm text-muted">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
                </div>
              </div>
            )}
            {ask.isError && <p className="text-sm text-danger">{getApiErrorMessage(ask.error)}</p>}
            <div ref={endRef} />
          </div>

          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => { e.preventDefault(); send(draft); }}
          >
            <Input
              placeholder="Ask about this meeting…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={ask.isPending}
            />
            <Button type="submit" disabled={ask.isPending || !draft.trim()} isLoading={ask.isPending}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </CardBody>
      </div>
    </Card>
  );
}
