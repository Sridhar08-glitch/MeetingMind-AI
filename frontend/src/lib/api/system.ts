import { api } from "./client";

export interface SystemInfo {
  ai_provider: string;
  ai_model: string;
  embedding_provider: string;
  stt_provider: string;
  whisper_model: string;
  whisper_device: string;
  async_processing: boolean;
  storage_backend: string;
  max_upload_mb: number | null;
}

export const systemApi = {
  async info(): Promise<SystemInfo> {
    const { data } = await api.get<SystemInfo>("/system/info/");
    return data;
  },
};
