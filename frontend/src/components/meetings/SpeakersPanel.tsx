"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Sparkles, UserPlus, Users, X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { getApiErrorMessage } from "@/lib/api/client";
import { meetingsApi } from "@/lib/api/meetings";
import { peopleApi, TIER_META } from "@/lib/api/people";
import { formatDuration } from "@/lib/utils";
import { meetingKeys } from "@/hooks/useMeetings";
import { toast } from "@/store/toast";
import type { Speaker, SpeakerEdit } from "@/lib/types";

/** Editable speaker cards with AI suggestions, analytics, and merge (Phase 15). */
export function SpeakersPanel({ meetingId, speakers }: { meetingId: string; speakers: Speaker[] }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: meetingKeys.transcript(meetingId) });
    queryClient.invalidateQueries({ queryKey: meetingKeys.detail(meetingId) });
    queryClient.invalidateQueries({ queryKey: ["voice-people"] });
  };

  const edit = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: SpeakerEdit }) =>
      meetingsApi.editSpeaker(meetingId, id, changes),
    onSuccess: () => { setEditing(null); invalidate(); },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not update speaker.")),
  });
  const accept = useMutation({
    mutationFn: (id: string) => meetingsApi.acceptSpeakerSuggestion(meetingId, id),
    onSuccess: () => { invalidate(); toast.success("Speaker name confirmed."); },
  });
  const merge = useMutation({
    mutationFn: ({ targetId, fromId }: { targetId: string; fromId: string }) =>
      meetingsApi.mergeSpeakers(meetingId, targetId, fromId),
    onSuccess: () => { invalidate(); toast.success("Speakers merged."); },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not merge speakers.")),
  });

  const totalTalk = speakers.reduce((s, sp) => s + sp.talk_time_seconds, 0) || 1;

  return (
    <div className="rounded-xl border border-border bg-slate-50/60 p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <Users className="h-4 w-4 text-brand-500" />
        <p className="text-sm font-semibold text-foreground">
          Speakers <span className="text-muted">({speakers.length})</span>
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {speakers.map((sp) => (
          <SpeakerCard
            key={sp.id}
            speaker={sp}
            sharePct={Math.round((sp.talk_time_seconds / totalTalk) * 100)}
            others={speakers.filter((o) => o.id !== sp.id)}
            isEditing={editing === sp.id}
            onEdit={() => setEditing(sp.id)}
            onCancel={() => setEditing(null)}
            onSave={(changes) => edit.mutate({ id: sp.id, changes })}
            onAccept={() => accept.mutate(sp.id)}
            onMerge={(fromId) => merge.mutate({ targetId: sp.id, fromId })}
            onIdentified={invalidate}
            saving={edit.isPending}
          />
        ))}
      </div>
    </div>
  );
}

function SpeakerCard({
  speaker, sharePct, others, isEditing, onEdit, onCancel, onSave, onAccept, onMerge, onIdentified, saving,
}: {
  speaker: Speaker;
  sharePct: number;
  others: Speaker[];
  isEditing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (changes: SpeakerEdit) => void;
  onAccept: () => void;
  onMerge: (fromId: string) => void;
  onIdentified: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<SpeakerEdit>({
    display_name: speaker.display_name,
    role: speaker.role,
    department: speaker.department,
    email: speaker.email,
  });
  const [identifying, setIdentifying] = useState(false);
  const showSuggestion = !speaker.confirmed && speaker.suggested_name;

  return (
    <div className="rounded-lg border border-border bg-surface p-2.5">
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-3 w-3 shrink-0 rounded-full"
          style={{ backgroundColor: speaker.color || "#64748b" }}
        />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
          {speaker.name}
          {speaker.confirmed && <Check className="ml-1 inline h-3 w-3 text-success" />}
        </span>
        {!isEditing && (
          <button
            onClick={onEdit}
            className="rounded-md p-1 text-muted hover:bg-slate-100 hover:text-foreground"
            aria-label="Edit speaker"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Analytics */}
      <p className="mt-1 text-xs text-muted">
        {formatDuration(Math.round(speaker.talk_time_seconds))} · {sharePct}% talk · {speaker.segment_count} lines ·{" "}
        {speaker.word_count} words
      </p>

      {/* Cross-meeting voice identity */}
      <IdentityRow
        speaker={speaker}
        open={identifying}
        onOpen={() => setIdentifying(true)}
        onClose={() => setIdentifying(false)}
        onChanged={() => { setIdentifying(false); onIdentified(); }}
      />

      {/* AI suggestion (never auto-applied) */}
      {showSuggestion && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-brand-200 bg-brand-50 px-2 py-1.5">
          <Sparkles className="h-3.5 w-3.5 text-brand-600" />
          <span className="text-xs text-brand-700">
            Suggested: <strong>{speaker.suggested_name}</strong>
            {speaker.suggested_confidence != null && ` (${Math.round(speaker.suggested_confidence)}%)`}
          </span>
          <div className="ml-auto flex gap-1">
            <Button size="sm" variant="secondary" onClick={onAccept}>Confirm</Button>
          </div>
        </div>
      )}

      {/* Edit form */}
      {isEditing && (
        <div className="mt-2 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <input
              value={form.display_name ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="Name"
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
              autoFocus
            />
            <input
              value={form.role ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
              placeholder="Role"
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
            />
            <input
              value={form.department ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, department: e.target.value }))}
              placeholder="Department"
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
            />
            <input
              value={form.email ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              placeholder="Email"
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
            />
          </div>
          {others.length > 0 && (
            <select
              onChange={(e) => e.target.value && onMerge(e.target.value)}
              defaultValue=""
              className="w-full rounded-md border border-border bg-surface px-2 py-1 text-xs text-muted"
            >
              <option value="">Merge another speaker into this one…</option>
              {others.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          )}
          <div className="flex gap-2">
            <Button size="sm" onClick={() => onSave({ ...form, confirmed: true })} isLoading={saving}>
              <Check className="h-3.5 w-3.5" /> Save
            </Button>
            <Button size="sm" variant="outline" onClick={onCancel}>
              <X className="h-3.5 w-3.5" /> Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Cross-meeting identity affordance for a speaker card.
 * - Linked  → chip "Identity: {name}" + Unlink.
 * - Unlinked → "Identify" button that fetches ranked candidates on demand.
 *
 * Matching is SUGGESTION-ONLY: candidates are shown with their confidence % and a
 * tier label, and nothing is linked until the user explicitly clicks Confirm.
 */
function IdentityRow({
  speaker, open, onOpen, onClose, onChanged,
}: {
  speaker: Speaker;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  onChanged: () => void;
}) {
  const unlink = useMutation({
    mutationFn: () => peopleApi.unlink(speaker.id),
    onSuccess: () => { onChanged(); toast.success("Identity unlinked."); },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not unlink identity.")),
  });

  if (speaker.voice_person_id && speaker.voice_person_name) {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-brand-100 bg-brand-50/60 px-2 py-1.5">
        <span className="text-xs text-brand-700">
          Identity: <strong>{speaker.voice_person_name}</strong>
        </span>
        <button
          onClick={() => unlink.mutate()}
          disabled={unlink.isPending}
          className="ml-auto text-xs text-muted underline-offset-2 hover:text-danger hover:underline disabled:opacity-50"
        >
          Unlink
        </button>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="mt-2">
        <Button size="sm" variant="outline" onClick={onOpen}>
          <UserPlus className="h-3.5 w-3.5" /> Identify
        </Button>
      </div>
    );
  }

  return <IdentifyPanel speaker={speaker} onClose={onClose} onChanged={onChanged} />;
}

function IdentifyPanel({
  speaker, onClose, onChanged,
}: {
  speaker: Speaker;
  onClose: () => void;
  onChanged: () => void;
}) {
  // Fetched lazily — this panel only mounts after the user clicks "Identify",
  // so there is no synchronous setState-in-effect (React-19 rule).
  const candidates = useQuery({
    queryKey: ["voice-people", "candidates", speaker.id],
    queryFn: () => peopleApi.candidates(speaker.id),
  });

  const link = useMutation({
    mutationFn: ({ personId, confidence, tier }: { personId: string; confidence: number; tier: string }) =>
      peopleApi.link(personId, speaker.id, { confidence, tier }),
    onSuccess: () => { onChanged(); toast.success("Speaker linked to identity."); },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not link this identity.")),
  });

  const create = useMutation({
    mutationFn: (name: string) => peopleApi.fromSpeaker(speaker.id, name),
    onSuccess: () => { onChanged(); toast.success("New identity created."); },
    onError: (e) => toast.error(getApiErrorMessage(e, "Could not create identity.")),
  });

  const promptCreate = () => {
    const name = window.prompt("Name for the new voice identity:", speaker.name || speaker.display_name || "");
    if (name && name.trim()) create.mutate(name.trim());
  };

  const list = candidates.data ?? [];
  const busy = link.isPending || create.isPending;

  return (
    <div className="mt-2 space-y-2 rounded-md border border-border bg-slate-50 p-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">Identify this speaker</span>
        <button onClick={onClose} className="rounded p-0.5 text-muted hover:bg-slate-200" aria-label="Close">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {candidates.isLoading ? (
        <p className="text-xs text-muted">Finding matches…</p>
      ) : candidates.isError ? (
        <p className="text-xs text-danger">Could not load suggestions.</p>
      ) : list.length === 0 ? (
        <p className="text-xs text-muted">No matching identities found.</p>
      ) : (
        <ul className="space-y-1.5">
          {list.map((c) => {
            const meta = TIER_META[c.tier] ?? TIER_META.none;
            return (
              <li
                key={c.voice_person.id}
                className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5"
              >
                <span className="text-xs text-foreground">
                  Looks like <strong>{c.voice_person.display_name}</strong>
                </span>
                <span className="text-xs text-muted">{Math.round(c.score)}%</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.className}`}>
                  {meta.label}
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  className="ml-auto"
                  disabled={busy}
                  onClick={() =>
                    link.mutate({ personId: c.voice_person.id, confidence: c.score, tier: c.tier })
                  }
                >
                  Confirm
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      <Button size="sm" variant="outline" onClick={promptCreate} disabled={busy}>
        <UserPlus className="h-3.5 w-3.5" /> Create new identity…
      </Button>
      <p className="text-[10px] text-muted">
        Suggestions only — nothing is linked until you confirm.
      </p>
    </div>
  );
}
