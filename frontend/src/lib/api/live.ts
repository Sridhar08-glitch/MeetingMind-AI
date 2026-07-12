import { api } from "./client";
import { authTokens } from "@/store/auth";

/** Provider-reported language capabilities (never hardcoded on the client). */
export interface LanguageCapabilities {
  detect: boolean;
  transcription: Record<string, string>;
  transcript_targets: Record<string, string>;
  ai_output: Record<string, string>;
}

export interface LiveLanguageConfig {
  meeting_language: string; // "" = auto-detect
  transcript_language: string; // "original" or a target code
  ai_language: string; // "" = same as transcript
}

export const liveApi = {
  /** Languages the active STT/translation/LLM providers support. */
  async languages(): Promise<LanguageCapabilities> {
    const { data } = await api.get<LanguageCapabilities>("/languages/");
    return data;
  },
};

/** Build the authenticated WebSocket URL for the live consumer. */
export function liveSocketUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
  // Derive host from the API base (strip the trailing /api) and swap scheme.
  const httpOrigin = base.replace(/\/api\/?$/, "");
  const wsOrigin = httpOrigin.replace(/^http/, "ws");
  const token = authTokens.getAccess() ?? "";
  return `${wsOrigin}/ws/meetings/live/?token=${encodeURIComponent(token)}`;
}
