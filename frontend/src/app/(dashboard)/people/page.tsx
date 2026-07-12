"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Clock, GitMerge, Mic } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState, ErrorState, SkeletonGrid } from "@/components/ui/Feedback";
import { getApiErrorMessage } from "@/lib/api/client";
import { peopleApi } from "@/lib/api/people";
import { cn, formatDuration, formatRelative } from "@/lib/utils";
import { toast } from "@/store/toast";
import type { VoicePerson, VoicePersonUpdate } from "@/lib/types";

const peopleKeys = {
  all: ["voice-people"] as const,
  list: () => ["voice-people", "list"] as const,
  events: (id: string) => ["voice-people", "events", id] as const,
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function PeoplePage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: peopleKeys.list(),
    queryFn: () => peopleApi.list(),
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const people = data ?? [];
  const selected = people.find((p) => p.id === selectedId) ?? null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">People</h1>
        <p className="mt-1 text-sm text-muted">
          Cross-meeting voice identities. Confirm a speaker in a meeting&apos;s transcript to build one.
        </p>
      </div>

      {isLoading ? (
        <SkeletonGrid count={6} label="Loading people" />
      ) : isError ? (
        <ErrorState
          title="Couldn't load people"
          description={getApiErrorMessage(error, "Something went wrong fetching voice identities.")}
          onRetry={() => refetch()}
        />
      ) : people.length === 0 ? (
        <EmptyState
          title="No voice identities yet"
          description="Identities are created by confirming a speaker in a meeting's transcript. Open a meeting, identify a speaker, and they'll appear here — recognized across every future meeting."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {people.map((p) => (
            <PersonCard key={p.id} person={p} onOpen={() => setSelectedId(p.id)} />
          ))}
        </div>
      )}

      {selected && (
        <PersonDrawer
          key={selected.id}
          person={selected}
          others={people.filter((p) => p.id !== selected.id)}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}

function PersonCard({ person, onOpen }: { person: VoicePerson; onOpen: () => void }) {
  const meta = [person.role, person.department].filter(Boolean).join(" · ");
  return (
    <Card
      className="cursor-pointer p-4 transition-colors hover:border-brand-300"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="flex items-center gap-3">
        <Avatar person={person} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="min-w-0 truncate text-sm font-semibold text-foreground">{person.display_name}</p>
            {person.confirmed && (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-success-bg px-1.5 py-0.5 text-[10px] font-medium text-success">
                <BadgeCheck className="h-3 w-3" /> Confirmed
              </span>
            )}
          </div>
          {meta && <p className="truncate text-xs text-muted">{meta}</p>}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <Stat value={person.meeting_count} label="meetings" />
        <Stat value={person.speaker_count} label="speakers" />
        <Stat value={Math.round(person.total_talk_time / 60)} label="min talk" />
      </div>

      <p className="mt-2 text-xs text-muted">
        {person.last_seen ? `Last seen ${formatRelative(person.last_seen)}` : "Not seen yet"}
      </p>
    </Card>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="rounded-lg bg-slate-50 py-1.5">
      <p className="text-sm font-bold text-foreground">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
    </div>
  );
}

function Avatar({ person, size = "md" }: { person: VoicePerson; size?: "md" | "lg" }) {
  const dim = size === "lg" ? "h-14 w-14 text-lg" : "h-10 w-10 text-sm";
  if (person.avatar) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={person.avatar} alt="" className={cn("shrink-0 rounded-full object-cover", dim)} />;
  }
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-700",
        dim,
      )}
      aria-hidden
    >
      {initials(person.display_name)}
    </span>
  );
}

function PersonDrawer({
  person,
  others,
  onClose,
}: {
  person: VoicePerson;
  others: VoicePerson[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<VoicePersonUpdate>({
    display_name: person.display_name,
    role: person.role,
    department: person.department,
    email: person.email,
    avatar: person.avatar,
    aliases: person.aliases,
  });
  const [aliasText, setAliasText] = useState(person.aliases.join(", "));
  const [mergeId, setMergeId] = useState("");

  const events = useQuery({
    queryKey: peopleKeys.events(person.id),
    queryFn: () => peopleApi.events(person.id),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: peopleKeys.all });

  const save = useMutation({
    mutationFn: () =>
      peopleApi.update(person.id, {
        ...form,
        aliases: aliasText.split(",").map((a) => a.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      invalidate();
      toast.success("Identity updated.");
    },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not update this identity.")),
  });

  const confirm = useMutation({
    mutationFn: () => peopleApi.confirm(person.id),
    onSuccess: () => {
      invalidate();
      toast.success("Identity confirmed.");
    },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not confirm this identity.")),
  });

  const merge = useMutation({
    mutationFn: (sourceId: string) => peopleApi.merge(person.id, sourceId),
    onSuccess: () => {
      setMergeId("");
      invalidate();
      toast.success("Identities merged.");
    },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not merge identities.")),
  });

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <Avatar person={person} size="lg" />
            <div>
              <h2 className="text-lg font-bold text-foreground">{person.display_name}</h2>
              <p className="text-xs text-muted">
                {person.meeting_count} meetings · {person.speaker_count} linked speakers
              </p>
            </div>
          </div>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-slate-100" aria-label="Close">
            ✕
          </button>
        </div>

        {/* Confirm banner */}
        {!person.confirmed && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning-bg bg-warning-bg/50 px-3 py-2 text-sm text-warning">
            <span className="flex-1">This identity is unconfirmed.</span>
            <Button size="sm" variant="secondary" onClick={() => confirm.mutate()} isLoading={confirm.isPending}>
              <BadgeCheck className="h-3.5 w-3.5" /> Confirm
            </Button>
          </div>
        )}

        {/* Editable fields */}
        <Section title="Identity">
          <div className="space-y-2">
            <Field label="Display name">
              <Input
                value={form.display_name ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Role">
                <Input value={form.role ?? ""} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} />
              </Field>
              <Field label="Department">
                <Input
                  value={form.department ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, department: e.target.value }))}
                />
              </Field>
            </div>
            <Field label="Email">
              <Input
                type="email"
                value={form.email ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
            </Field>
            <Field label="Avatar URL">
              <Input value={form.avatar ?? ""} onChange={(e) => setForm((f) => ({ ...f, avatar: e.target.value }))} />
            </Field>
            <Field label="Aliases (comma separated)">
              <Input value={aliasText} onChange={(e) => setAliasText(e.target.value)} />
            </Field>
            <Button size="sm" onClick={() => save.mutate()} isLoading={save.isPending}>
              Save changes
            </Button>
          </div>
        </Section>

        {/* Aggregate presence (API exposes counts, not the full speaker list) */}
        <Section title="Presence" icon={<Mic className="h-3.5 w-3.5" />}>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <Aggregate label="Meetings" value={String(person.meeting_count)} />
            <Aggregate label="Linked speakers" value={String(person.speaker_count)} />
            <Aggregate label="Talk time" value={formatDuration(person.total_talk_time)} />
            <Aggregate label="Words spoken" value={person.total_word_count.toLocaleString()} />
            {person.confidence != null && (
              <Aggregate label="Match confidence" value={`${Math.round(person.confidence)}%`} />
            )}
            {person.avg_embedding_quality != null && (
              <Aggregate label="Voice quality" value={`${Math.round(person.avg_embedding_quality * 100)}%`} />
            )}
          </div>
        </Section>

        {/* Merge (split is surfaced from the meeting SpeakersPanel instead) */}
        <Section title="Merge" icon={<GitMerge className="h-3.5 w-3.5" />}>
          {others.length === 0 ? (
            <p className="text-xs text-muted">No other identities to merge in.</p>
          ) : (
            <div className="flex gap-2">
              <select
                value={mergeId}
                onChange={(e) => setMergeId(e.target.value)}
                className="flex-1 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-foreground"
              >
                <option value="">Merge another identity into this one…</option>
                {others.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.display_name}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                disabled={!mergeId}
                onClick={() => mergeId && merge.mutate(mergeId)}
                isLoading={merge.isPending}
              >
                Merge
              </Button>
            </div>
          )}
        </Section>

        {/* Audit timeline */}
        <Section title="Timeline" icon={<Clock className="h-3.5 w-3.5" />}>
          {events.isLoading ? (
            <p className="text-xs text-muted">Loading…</p>
          ) : (events.data ?? []).length === 0 ? (
            <p className="text-xs text-muted">No events yet.</p>
          ) : (
            <ol className="space-y-2">
              {(events.data ?? []).map((ev) => (
                <li key={ev.id} className="flex items-start gap-2 text-xs">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" aria-hidden />
                  <div className="min-w-0">
                    <p className="text-foreground/90">
                      <span className="font-medium capitalize">{ev.event_type.replace(/_/g, " ")}</span>
                      {ev.confidence != null && <span className="text-muted"> · {Math.round(ev.confidence)}%</span>}
                      {ev.tier && ev.tier !== "none" && (
                        <span className="text-muted"> · {ev.tier.replace(/_/g, " ")}</span>
                      )}
                    </p>
                    <p className="text-muted">{formatRelative(ev.created_at)}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-0.5 block text-[11px] text-muted">{label}</span>
      {children}
    </label>
  );
}

function Aggregate({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <p className="text-xs text-muted">{label}</p>
      <p className="font-medium text-foreground">{value}</p>
    </div>
  );
}
