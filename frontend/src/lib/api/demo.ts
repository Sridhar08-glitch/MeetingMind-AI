import { api } from "./client";

/** Public demo account credentials (safe to expose — it's a shared demo login). */
export const DEMO_EMAIL = "demo@meetingmind.ai";
export const DEMO_PASSWORD = "DemoPass123!";

export interface DemoInfo {
  enabled: boolean;
  email: string;
  password: string;
  workspace: string;
}

/** A bundled demo recording the user can upload to try the real pipeline. */
export interface DemoSample {
  title: string;
  project: string;
  mtype: string;
  media: "audio" | "video";
  filename: string;
  content_type: string;
  size_bytes: number;
  duration_seconds: number;
  download_url: string;
}

export const demoApi = {
  /** Whether demo mode is available + the demo credentials. */
  async info(): Promise<DemoInfo> {
    const { data } = await api.get<DemoInfo>("/demo/info/");
    return data;
  },
  /** Reset the demo workspace back to its original seeded state. */
  async reset(): Promise<void> {
    await api.post("/demo/reset/", {});
  },
  /** List the bundled sample recordings available to upload. */
  async samples(): Promise<DemoSample[]> {
    const { data } = await api.get<{ count: number; samples: DemoSample[] }>("/demo/samples/");
    return data.samples;
  },
  /** Download one sample recording as a File, ready to feed into the upload flow. */
  async sampleFile(sample: DemoSample): Promise<File> {
    const { data } = await api.get<Blob>(`/demo/samples/${sample.filename}/`, {
      responseType: "blob",
    });
    return new File([data], sample.filename, { type: sample.content_type });
  },
};
