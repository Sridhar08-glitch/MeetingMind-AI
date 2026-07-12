import { api } from "./client";
import type {
  AnalyzeResult,
  ApiSuccess,
  DuplicateAction,
  MediaImportSession,
  MediaSourceCapabilities,
} from "@/lib/types";

export interface ImportPayload {
  url?: string;
  urls?: string[];
  episode_id?: string;
  requested_media?: "audio" | "video";
  title?: string;
  meeting_language?: string;
  transcript_language?: string;
  ai_language?: string;
  on_duplicate?: DuplicateAction;
}

export const mediaApi = {
  /** Which import providers are available (URL import hidden if none). */
  async sources(): Promise<MediaSourceCapabilities> {
    const { data } = await api.get<MediaSourceCapabilities>("/media/sources/");
    return data;
  },

  /** Preview metadata for one or many URLs (no download). */
  async analyze(urls: string[]): Promise<AnalyzeResult[]> {
    const { data } = await api.post<ApiSuccess<{ results: AnalyzeResult[] }>>(
      "/meetings/import/analyze/",
      urls.length === 1 ? { url: urls[0] } : { urls },
    );
    return data.data.results;
  },

  /** Start one or many imports; returns a session per URL. */
  async import(payload: ImportPayload): Promise<MediaImportSession[]> {
    const { data } = await api.post<ApiSuccess<{ imports: MediaImportSession[] }>>(
      "/meetings/import/",
      payload,
    );
    return data.data.imports;
  },

  /** The caller's import sessions (optionally only active ones). */
  async list(active = false): Promise<MediaImportSession[]> {
    const { data } = await api.get<ApiSuccess<MediaImportSession[]>>("/meetings/import/", {
      params: active ? { active: 1 } : undefined,
    });
    return data.data;
  },

  /** Poll a single import session. */
  async get(id: string): Promise<MediaImportSession> {
    const { data } = await api.get<ApiSuccess<MediaImportSession>>(`/meetings/import/${id}/`);
    return data.data;
  },

  /** Cancel an in-flight import. */
  async cancel(id: string): Promise<MediaImportSession> {
    const { data } = await api.post<ApiSuccess<MediaImportSession>>(
      `/meetings/import/${id}/cancel/`,
      {},
    );
    return data.data;
  },
};
