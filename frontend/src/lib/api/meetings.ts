import type { AxiosProgressEvent } from "axios";

import { api, API_BASE_URL } from "./client";
import { useAuthStore } from "@/store/auth";
import type {
  ApiSuccess,
  DashboardStats,
  DuplicateAction,
  Meeting,
  MeetingDetail,
  MeetingSource,
  MeetingStatusSnapshot,
  Paginated,
  AIAnalysis,
  AIAnalysisVersion,
  Speaker,
  SpeakerEdit,
  TranscriptFormat,
  TranscriptResponse,
  TranscriptSegment,
} from "@/lib/types";

export interface MeetingListParams {
  page?: number;
  page_size?: number;
  search?: string;
  processing_status?: string;
  source?: string;
  ordering?: string;
  is_favorite?: boolean;
}

export interface UploadPayload {
  file: File;
  title?: string;
  description?: string;
  language?: string;
  source?: MeetingSource;
  tags?: string[];
  on_duplicate?: DuplicateAction;
}

export interface MeetingUpdatePayload {
  title?: string;
  description?: string;
  language?: string;
  source?: MeetingSource;
  tags?: string[];
  is_archived?: boolean;
}

export const meetingsApi = {
  async list(params: MeetingListParams = {}): Promise<Paginated<Meeting>> {
    const { data } = await api.get<Paginated<Meeting>>("/meetings/", { params });
    return data;
  },

  async retrieve(id: string): Promise<MeetingDetail> {
    const { data } = await api.get<MeetingDetail>(`/meetings/${id}/`);
    return data;
  },

  async statusSnapshot(id: string): Promise<MeetingStatusSnapshot> {
    const { data } = await api.get<ApiSuccess<MeetingStatusSnapshot>>(`/meetings/${id}/status/`);
    return data.data;
  },

  async upload(
    payload: UploadPayload,
    onProgress?: (percent: number) => void,
  ): Promise<MeetingDetail> {
    const form = new FormData();
    form.append("file", payload.file);
    if (payload.title) form.append("title", payload.title);
    if (payload.description) form.append("description", payload.description);
    if (payload.language) form.append("language", payload.language);
    if (payload.source) form.append("source", payload.source);
    if (payload.on_duplicate) form.append("on_duplicate", payload.on_duplicate);
    (payload.tags ?? []).forEach((tag) => form.append("tags", tag));

    const { data } = await api.post<ApiSuccess<MeetingDetail>>("/meetings/upload/", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      },
    });
    return data.data;
  },

  async update(id: string, payload: MeetingUpdatePayload): Promise<MeetingDetail> {
    const { data } = await api.patch<ApiSuccess<MeetingDetail>>(`/meetings/${id}/`, payload);
    return data.data;
  },

  async reprocess(id: string): Promise<MeetingDetail> {
    const { data } = await api.post<ApiSuccess<MeetingDetail>>(`/meetings/${id}/reprocess/`, {});
    return data.data;
  },

  /** Toggle the starred/favorite flag; returns the new state. */
  async toggleFavorite(id: string): Promise<boolean> {
    const { data } = await api.post<ApiSuccess<{ id: string; is_favorite: boolean }>>(
      `/meetings/${id}/favorite/`,
      {},
    );
    return data.data.is_favorite;
  },

  /**
   * Range-capable inline stream URL for the media player. The <video>/<audio>
   * element streams directly (with seek) instead of loading the whole file into
   * memory as a blob — this is what makes large (multi-GB) recordings playable.
   * The JWT rides in the query string because media elements can't set headers.
   */
  streamUrl(id: string, version?: number): string {
    const token = useAuthStore.getState().accessToken ?? "";
    const params = new URLSearchParams();
    if (token) params.set("token", token);
    if (version) params.set("version", String(version));
    const qs = params.toString();
    return `${API_BASE_URL}/meetings/${id}/stream/${qs ? `?${qs}` : ""}`;
  },

  /** Fetch a file version as an authenticated blob (owner-only endpoint). */
  async download(id: string, version?: number): Promise<Blob> {
    const { data } = await api.get<Blob>(`/meetings/${id}/download/`, {
      responseType: "blob",
      params: version ? { version } : undefined,
    });
    return data;
  },

  // --- Transcript (Phase 6) ---------------------------------------------
  async transcript(id: string): Promise<TranscriptResponse> {
    const { data } = await api.get<ApiSuccess<TranscriptResponse>>(`/meetings/${id}/transcript/`);
    return data.data;
  },

  async editSegment(id: string, segId: string, text: string, speaker?: string): Promise<TranscriptSegment> {
    const { data } = await api.patch<ApiSuccess<TranscriptSegment>>(
      `/meetings/${id}/segments/${segId}/`, { text, ...(speaker !== undefined ? { speaker } : {}) },
    );
    return data.data;
  },

  // --- Speakers (Phase 15) ---------------------------------------------
  async speakers(id: string): Promise<Speaker[]> {
    const { data } = await api.get<ApiSuccess<{ speakers: Speaker[] }>>(`/meetings/${id}/speakers/`);
    return data.data.speakers;
  },

  async editSpeaker(id: string, speakerId: string, changes: SpeakerEdit): Promise<Speaker> {
    const { data } = await api.patch<ApiSuccess<Speaker>>(
      `/meetings/${id}/speakers/${speakerId}/`, changes,
    );
    return data.data;
  },

  async acceptSpeakerSuggestion(id: string, speakerId: string): Promise<Speaker> {
    const { data } = await api.post<ApiSuccess<Speaker>>(
      `/meetings/${id}/speakers/${speakerId}/accept-suggestion/`, {},
    );
    return data.data;
  },

  async mergeSpeakers(id: string, targetId: string, fromId: string): Promise<Speaker> {
    const { data } = await api.post<ApiSuccess<Speaker>>(
      `/meetings/${id}/speakers/${targetId}/merge/`, { from: fromId },
    );
    return data.data;
  },

  async restoreSegment(id: string, segId: string): Promise<TranscriptSegment> {
    const { data } = await api.post<ApiSuccess<TranscriptSegment>>(
      `/meetings/${id}/segments/${segId}/restore/`, {},
    );
    return data.data;
  },

  async restoreTranscript(id: string): Promise<void> {
    await api.post(`/meetings/${id}/transcript/restore/`, {});
  },

  async searchTranscript(id: string, q: string): Promise<TranscriptSegment[]> {
    const { data } = await api.get<ApiSuccess<{ segments: TranscriptSegment[] }>>(
      `/meetings/${id}/transcript/search/`, { params: { q } },
    );
    return data.data.segments;
  },

  async retranscribe(id: string, model?: string): Promise<MeetingDetail> {
    const { data } = await api.post<ApiSuccess<MeetingDetail>>(
      `/meetings/${id}/retranscribe/`, model ? { model } : {},
    );
    return data.data;
  },

  async downloadTranscript(id: string, fmt: TranscriptFormat): Promise<Blob> {
    const { data } = await api.get<Blob>(`/meetings/${id}/transcript/download/`, {
      responseType: "blob", params: { fmt },
    });
    return data;
  },

  // --- AI analysis (Phase 7) --------------------------------------------
  async ai(id: string): Promise<AIAnalysis | null> {
    const { data } = await api.get<ApiSuccess<AIAnalysis | null>>(`/meetings/${id}/ai/`);
    return data.data;
  },

  async aiHistory(id: string): Promise<AIAnalysisVersion[]> {
    const { data } = await api.get<ApiSuccess<AIAnalysisVersion[]>>(`/meetings/${id}/ai/history/`);
    return data.data;
  },

  async regenerateAI(id: string, model?: string): Promise<void> {
    await api.post(`/meetings/${id}/ai/regenerate/`, model ? { model } : {});
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/meetings/${id}/`);
  },

  async dashboardStats(): Promise<DashboardStats> {
    const { data } = await api.get<ApiSuccess<DashboardStats>>("/meetings/dashboard/stats/");
    return data.data;
  },
};
