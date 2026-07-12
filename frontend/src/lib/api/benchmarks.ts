import { api } from "./client";
import type { ApiSuccess } from "@/lib/types";

// ---- Types -----------------------------------------------------------------

export type DatasetKind = "public" | "user";

export interface BenchmarkDataset {
  id: string;
  kind: DatasetKind;
  name: string;
  slug: string;
  description: string;
  recording_count: number;
  created_at: string;
}

export type RecordingFormat =
  | "podcast"
  | "panel"
  | "interview"
  | "roundtable"
  | "webinar"
  | "meeting"
  | "other";

export type GroundTruthType = "user_verified" | "public_approximate" | "unknown";

export type RecordingStatus =
  | "pending"
  | "importing"
  | "processing"
  | "ready"
  | "failed"
  | "skipped";

export interface BenchmarkRecording {
  id: string;
  dataset: string;
  name: string;
  format: RecordingFormat;
  language: string;
  source_url: string;
  source_kind: string;
  ground_truth_type: GroundTruthType;
  expected_speaker_count: number | null;
  known_participants: string[];
  meeting_type: string;
  notes: string;
  reference_segments: unknown[];
  meeting_id: string | null;
  status: RecordingStatus;
  status_detail: string;
  ground_truth_is_exact: boolean;
  created_at: string;
}

export type OverlapHandling = "longest" | "ignore" | "split";

export interface BenchmarkConfig {
  id: string;
  name: string;
  diarization_provider: string;
  cluster_threshold: number;
  merge_threshold: number | null;
  min_speech_duration: number;
  min_segment_length: number;
  max_speakers: number;
  overlap_handling: OverlapHandling;
  is_default: boolean;
  created_at: string;
}

export interface BenchmarkRun {
  id: string;
  dataset: string;
  label: string;
  status: string;
  engine_version: string;
  diarization_engine: string;
  stt_provider: string;
  embedding_model: string;
  git_commit: string;
  config: Record<string, unknown> | null;
  recordings_total: number;
  recordings_scored: number;
  configs_count: number;
  speaker_count_accuracy: number | null;
  avg_speaker_count_error: number | null;
  total_over_merged: number;
  total_over_split: number;
  avg_embedding_confidence: number | null;
  avg_processing_ms: number | null;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  result_count: number;
  created_at: string;
}

export interface BenchmarkResult {
  id: string;
  run: string;
  recording: string;
  recording_name: string;
  config_label: string;
  config: Record<string, unknown> | null;
  expected_speaker_count: number | null;
  detected_speaker_count: number | null;
  correctly_clustered: number | null;
  over_merged: number;
  over_split: number;
  avg_embedding_confidence: number | null;
  avg_speech_duration: number | null;
  processing_time_ms: number | null;
  diarization_engine: string;
  stt_provider: string;
  embedding_model: string;
  knowledge_version: number | null;
  ground_truth_type: GroundTruthType;
  der: number | null;
  cluster_purity: number | null;
  ok: boolean;
  detail: string;
  created_at: string;
}

export interface BenchmarkRunDetail extends BenchmarkRun {
  results: BenchmarkResult[];
}

export interface CompareRow {
  config_label: string;
  config: Record<string, unknown> | null;
  recordings: number;
  speaker_count_accuracy: number | null;
  total_over_merged: number;
  total_over_split: number;
  avg_embedding_confidence: number | null;
  avg_processing_ms: number | null;
}

export interface CompareResult {
  run: BenchmarkRun;
  comparison: CompareRow[];
}

// ---- Payloads --------------------------------------------------------------

export interface DatasetCreatePayload {
  kind: DatasetKind;
  name: string;
  description?: string;
}

export interface RecordingCreatePayload {
  dataset: string;
  name: string;
  format: RecordingFormat;
  language?: string;
  source_url?: string;
  expected_speaker_count?: number | null;
  known_participants?: string[];
  meeting_type?: string;
  notes?: string;
  reference_segments?: unknown[];
}

export interface FromMeetingPayload {
  meeting: string;
  dataset?: string;
  name?: string;
  expected_speaker_count?: number | null;
  known_participants?: string[];
  meeting_type?: string;
  reference_segments?: unknown[];
}

export interface ConfigPayload {
  name: string;
  diarization_provider: string;
  cluster_threshold: number;
  merge_threshold?: number | null;
  min_speech_duration: number;
  min_segment_length: number;
  max_speakers: number;
  overlap_handling: OverlapHandling;
  is_default: boolean;
}

export interface RunPayload {
  dataset: string;
  config_ids?: string[];
  configs?: Record<string, unknown>[];
  label?: string;
}

export interface RecordingListParams {
  dataset?: string;
  format?: RecordingFormat;
  status?: RecordingStatus;
  ground_truth_type?: GroundTruthType;
}

// ---- Client ----------------------------------------------------------------

function unwrap<T>(p: Promise<{ data: ApiSuccess<T> }>): Promise<T> {
  return p.then((r) => r.data.data);
}

export const benchmarksApi = {
  datasets: {
    list: () => unwrap<BenchmarkDataset[]>(api.get("/benchmarks/datasets/")),
    create: (payload: DatasetCreatePayload) =>
      unwrap<BenchmarkDataset>(api.post("/benchmarks/datasets/", payload)),
    update: (id: string, payload: Partial<DatasetCreatePayload>) =>
      unwrap<BenchmarkDataset>(api.patch(`/benchmarks/datasets/${id}/`, payload)),
    remove: (id: string) => api.delete(`/benchmarks/datasets/${id}/`),
    seedPublic: (limit?: number) =>
      unwrap<{ created: number; datasets: BenchmarkDataset[] }>(
        api.post("/benchmarks/datasets/seed-public/", limit != null ? { limit } : {}),
      ),
  },

  recordings: {
    list: (params: RecordingListParams = {}) =>
      unwrap<BenchmarkRecording[]>(api.get("/benchmarks/recordings/", { params })),
    create: (payload: RecordingCreatePayload) =>
      unwrap<BenchmarkRecording>(api.post("/benchmarks/recordings/", payload)),
    update: (id: string, payload: Partial<RecordingCreatePayload>) =>
      unwrap<BenchmarkRecording>(api.patch(`/benchmarks/recordings/${id}/`, payload)),
    remove: (id: string) => api.delete(`/benchmarks/recordings/${id}/`),
    import: (id: string, requestedMedia?: "audio" | "video") =>
      unwrap<BenchmarkRecording>(
        api.post(
          `/benchmarks/recordings/${id}/import/`,
          requestedMedia ? { requested_media: requestedMedia } : {},
        ),
      ),
    fromMeeting: (payload: FromMeetingPayload) =>
      unwrap<BenchmarkRecording>(api.post("/benchmarks/recordings/from-meeting/", payload)),
  },

  configs: {
    list: () => unwrap<BenchmarkConfig[]>(api.get("/benchmarks/configs/")),
    create: (payload: ConfigPayload) =>
      unwrap<BenchmarkConfig>(api.post("/benchmarks/configs/", payload)),
    update: (id: string, payload: Partial<ConfigPayload>) =>
      unwrap<BenchmarkConfig>(api.patch(`/benchmarks/configs/${id}/`, payload)),
    remove: (id: string) => api.delete(`/benchmarks/configs/${id}/`),
  },

  runs: {
    list: () => unwrap<BenchmarkRun[]>(api.get("/benchmarks/runs/")),
    detail: (id: string) => unwrap<BenchmarkRunDetail>(api.get(`/benchmarks/runs/${id}/`)),
    run: (payload: RunPayload) =>
      unwrap<BenchmarkRunDetail>(api.post("/benchmarks/runs/run/", payload)),
    compare: (id: string) =>
      unwrap<CompareResult>(api.get(`/benchmarks/runs/${id}/compare/`)),
  },
};
