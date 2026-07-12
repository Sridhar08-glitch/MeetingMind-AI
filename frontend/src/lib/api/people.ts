import { api } from "./client";
import type {
  ApiSuccess,
  Paginated,
  VoiceCandidate,
  VoiceMatchTier,
  VoicePerson,
  VoicePersonEvent,
  VoicePersonUpdate,
  VoiceSuggestion,
} from "@/lib/types";

/**
 * Presentation for a match tier. Matching is SUGGESTION-ONLY — these labels never
 * imply the link is applied. The UI always shows the confidence % alongside and
 * requires an explicit Confirm click.
 */
export const TIER_META: Record<VoiceMatchTier, { label: string; className: string }> = {
  auto_highlight: { label: "Almost certain", className: "bg-success-bg text-success" },
  highly_likely: { label: "Highly likely", className: "bg-success-bg text-success" },
  possible: { label: "Possible", className: "bg-warning-bg text-warning" },
  none: { label: "Unlikely", className: "bg-slate-100 text-slate-600" },
};

export interface VoicePeopleListParams {
  confirmed?: boolean;
  workspace?: string;
}

/**
 * Cross-meeting voice identities (Phase 15b). Owner-scoped.
 *
 * Convention note (matches workspace.ts): DRF list/retrieve endpoints return the
 * RAW paginated `{count,results}` / raw object, while custom ACTIONS return the
 * `{success,data}` envelope.
 */
export const peopleApi = {
  // --- list / retrieve (RAW) --------------------------------------------
  async list(params: VoicePeopleListParams = {}): Promise<VoicePerson[]> {
    const { data } = await api.get<Paginated<VoicePerson>>("/workspace/voice-people/", {
      params: { ...params, page_size: 200 },
    });
    return data.results;
  },

  async retrieve(id: string): Promise<VoicePerson> {
    const { data } = await api.get<VoicePerson>(`/workspace/voice-people/${id}/`);
    return data;
  },

  async update(id: string, payload: VoicePersonUpdate): Promise<VoicePerson> {
    const { data } = await api.patch<VoicePerson>(`/workspace/voice-people/${id}/`, payload);
    return data;
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/workspace/voice-people/${id}/`);
  },

  // --- actions (ENVELOPE) -----------------------------------------------
  async candidates(speakerId: string): Promise<VoiceCandidate[]> {
    const { data } = await api.get<ApiSuccess<{ speaker_id: string; candidates: VoiceCandidate[] }>>(
      "/workspace/voice-people/candidates/",
      { params: { speaker: speakerId } },
    );
    return data.data.candidates;
  },

  async suggest(meetingId: string): Promise<VoiceSuggestion[]> {
    const { data } = await api.get<ApiSuccess<{ suggestions: VoiceSuggestion[] }>>(
      "/workspace/voice-people/suggest/",
      { params: { meeting: meetingId } },
    );
    return data.data.suggestions;
  },

  /** Create a brand-new identity from a speaker and link them. */
  async fromSpeaker(speakerId: string, displayName: string): Promise<VoicePerson> {
    const { data } = await api.post<ApiSuccess<VoicePerson>>("/workspace/voice-people/from-speaker/", {
      speaker: speakerId,
      display_name: displayName,
    });
    return data.data;
  },

  async link(
    id: string,
    speakerId: string,
    opts: { confidence?: number; tier?: string } = {},
  ): Promise<VoicePerson> {
    const { data } = await api.post<ApiSuccess<VoicePerson>>(`/workspace/voice-people/${id}/link/`, {
      speaker: speakerId,
      ...opts,
    });
    return data.data;
  },

  async unlink(speakerId: string): Promise<void> {
    await api.post("/workspace/voice-people/unlink/", { speaker: speakerId });
  },

  async confirm(id: string): Promise<VoicePerson> {
    const { data } = await api.post<ApiSuccess<VoicePerson>>(`/workspace/voice-people/${id}/confirm/`, {});
    return data.data;
  },

  async merge(id: string, sourceId: string): Promise<VoicePerson> {
    const { data } = await api.post<ApiSuccess<VoicePerson>>(`/workspace/voice-people/${id}/merge/`, {
      source: sourceId,
    });
    return data.data;
  },

  async split(id: string, speakerIds: string[], name: string): Promise<VoicePerson> {
    const { data } = await api.post<ApiSuccess<VoicePerson>>(`/workspace/voice-people/${id}/split/`, {
      speaker_ids: speakerIds,
      name,
    });
    return data.data;
  },

  async events(id: string): Promise<VoicePersonEvent[]> {
    const { data } = await api.get<ApiSuccess<VoicePersonEvent[]>>(`/workspace/voice-people/${id}/events/`);
    return data.data;
  },
};
