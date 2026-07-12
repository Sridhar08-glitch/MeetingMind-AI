/** Shared API types mirroring the backend serializers. */

export interface ApiSuccess<T> {
  success: true;
  message?: string;
  data: T;
}

export interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface Paginated<T> {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  date_joined: string;
  is_staff: boolean;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginResponse extends AuthTokens {
  user: User;
}

/** Upload lifecycle of a single file (a MeetingFile version). */
export type UploadStatus =
  | "pending"
  | "uploading"
  | "uploaded"
  | "stored"
  | "verified"
  | "failed";

/** Processing lifecycle of a meeting (transcription/AI). Separate concern. */
export type ProcessingStatus =
  | "pending"
  | "queued"
  | "running"
  | "retrying"
  | "completed"
  | "failed"
  | "canceled";

export type MeetingSource =
  | "manual_upload"
  | "live"
  | "screen_recording"
  | "webcam_recording"
  | "zoom"
  | "google_meet"
  | "ms_teams"
  | "mobile_recording"
  | "voice_recorder"
  | "public_video"
  | "podcast"
  | "rss_feed"
  | "direct_url"
  | "batch_import"
  | "other";

export type MediaKind = "audio" | "video" | "";

export type DuplicateAction = "reject" | "replace" | "keep_both" | "ignore";

export interface MediaMetadata {
  container: string;
  audio_codec: string;
  video_codec: string;
  bitrate: number | null;
  sample_rate: number | null;
  channels: number | null;
  frame_rate: number | null;
  extra: Record<string, unknown>;
}

export interface ValidationCheck {
  name: string;
  passed: boolean;
  skipped: boolean;
  message: string;
}

export interface ValidationReport {
  ok: boolean;
  checks: ValidationCheck[];
}

export interface MeetingFile {
  id: string;
  version: number;
  is_current: boolean;
  original_filename: string;
  stored_filename: string;
  file_extension: string;
  content_type: string;
  media_kind: MediaKind;
  size_bytes: number | null;
  checksum_sha256: string;
  upload_status: UploadStatus;
  validation_report: ValidationReport | Record<string, never>;
  uploaded_at: string | null;
  media_metadata: MediaMetadata | null;
  download_url: string | null;
  thumbnail_url: string | null;
}

export interface Meeting {
  id: string;
  title: string;
  description: string;
  language: string;
  source: MeetingSource;
  processing_status: ProcessingStatus;
  upload_status: UploadStatus | null;
  is_archived: boolean;
  is_favorite: boolean;
  duration_seconds: number | null;
  current_file: MeetingFile | null;
  tags: string[];
  source_url?: string;
  source_metadata?: SourceMetadata;
  created_at: string;
  updated_at: string;
}

/** Provenance for media imported from an external source (Phase 14). */
export interface SourceMetadata {
  source_type?: string;
  platform?: string;
  platform_id?: string;
  original_url?: string;
  author?: string;
  title?: string;
  thumbnail?: string;
  published_at?: string;
  license?: string;
  duration?: number | null;
  podcast?: string;
  episode?: string;
  episode_guid?: string;
  imported_at?: string;
  importer_version?: string;
  [key: string]: unknown;
}

export interface MeetingEvent {
  id: string;
  event_type: string;
  event_type_display: string;
  source: string;
  actor: string | null;
  message: string;
  details: Record<string, unknown>;
  duration_ms: number | null;
  created_at: string;
}

export interface TranscriptSegment {
  id: string;
  index: number;
  start_time: number;
  end_time: number;
  speaker: string;
  speaker_id?: string | null;
  text: string;
  translated_text?: string;
  confidence: number | null;
  word_count: number | null;
  is_edited: boolean;
  edited_at: string | null;
}

/** A first-class meeting speaker (Phase 15) — editable identity + analytics. */
export interface Speaker {
  id: string;
  label: string;
  display_name: string;
  name: string;
  confirmed: boolean;
  color: string;
  role: string;
  department: string;
  email: string;
  avatar: string;
  aliases: string[];
  suggested_name: string;
  suggested_confidence: number | null;
  recognition_confidence: number | null;
  talk_time_seconds: number;
  segment_count: number;
  word_count: number;
  avg_confidence: number | null;
  /** Cross-meeting voice identity this speaker is linked to (Phase 15b). */
  voice_person_id: string | null;
  voice_person_name: string | null;
}

// --- Voice people (cross-meeting identities, Phase 15b) --------------------
export interface VoicePerson {
  id: string;
  workspace: string | null;
  display_name: string;
  aliases: string[];
  avatar: string;
  email: string;
  department: string;
  role: string;
  confirmed: boolean;
  confidence: number | null;
  embedding_dimensions: number;
  meeting_count: number;
  speaker_count: number;
  total_talk_time: number;
  total_word_count: number;
  avg_embedding_quality: number | null;
  last_seen: string | null;
  created_at: string;
  updated_at: string;
}

export interface VoicePersonEvent {
  id: string;
  event_type: string;
  speaker_id: string | null;
  meeting_id: string | null;
  confidence: number | null;
  tier: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export type VoiceMatchTier = "auto_highlight" | "highly_likely" | "possible" | "none";

export interface VoiceCandidate {
  voice_person: VoicePerson;
  score: number;
  tier: VoiceMatchTier;
}

export interface VoicePersonUpdate {
  display_name?: string;
  aliases?: string[];
  avatar?: string;
  email?: string;
  department?: string;
  role?: string;
}

/** One speaker's ranked identity candidates (from the suggest endpoint). */
export interface VoiceSuggestion {
  speaker_id: string;
  speaker_label: string;
  candidates: VoiceCandidate[];
}

export interface SpeakerEdit {
  display_name?: string;
  role?: string;
  department?: string;
  email?: string;
  color?: string;
  avatar?: string;
  aliases?: string[];
  confirmed?: boolean;
}

export interface Transcript {
  id: string;
  clean_text: string;
  raw_text: string;
  word_count: number;
  char_count: number;
  detected_language: string;
  language_confidence: number | null;
  avg_confidence: number | null;
  translated_text?: string;
  target_language?: string;
  translation_provider?: string;
  translation_confidence?: number | null;
  translation_ms?: number | null;
  model_used: string;
  provider: string;
  processing_ms: number | null;
  audio_duration_seconds: number | null;
  transcription_speed: number | null;
  is_edited: boolean;
  edited_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptResponse {
  transcript: Transcript | null;
  segments: TranscriptSegment[];
  speakers?: Speaker[];
}

export type TranscriptFormat = "txt" | "md" | "json" | "srt" | "vtt";

// --- AI analysis (Phase 7) -------------------------------------------------
export interface ActionItem {
  task: string;
  owner: string;
  priority: string;
  due_date: string;
  status: string;
}
export interface Decision {
  decision: string;
  reason: string;
  participants: string[];
}
export interface Risk {
  risk: string;
  severity: string;
  mitigation: string;
}
export interface FollowUp {
  item: string;
  owner: string;
}
export interface Deadline {
  item: string;
  date: string;
}
export interface Keywords {
  topics: string[];
  technologies: string[];
  people: string[];
  companies: string[];
  phrases: string[];
}

export interface AIAnalysis {
  id: string;
  version: number;
  is_current: boolean;
  executive_summary: string;
  detailed_summary: string;
  bullet_summary: string[];
  meeting_minutes: string;
  action_items: ActionItem[];
  decisions: Decision[];
  risks: Risk[];
  follow_ups: FollowUp[];
  deadlines: Deadline[];
  keywords: Keywords;
  model_used: string;
  provider: string;
  prompt_version: string;
  inference_ms: number | null;
  chunks: number;
  temperature: number | null;
  created_at: string;
}

// --- Chat (Phase 8) --------------------------------------------------------
export interface MessageCitation {
  id: string;
  index: number;
  start_time: number;
  end_time: number;
  snippet: string;
  segment: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  found: boolean;
  provider: string;
  model_used: string;
  inference_ms: number | null;
  citations: MessageCitation[];
  created_at: string;
}

export interface ChatConversation {
  id: string;
  meeting: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatConversationDetail extends ChatConversation {
  messages: ChatMessage[];
}

export interface AIAnalysisVersion {
  id: string;
  version: number;
  is_current: boolean;
  model_used: string;
  provider: string;
  prompt_version: string;
  inference_ms: number | null;
  created_at: string;
}

export interface AIOutput {
  id: string;
  kind: string;
  raw_output: Record<string, unknown>;
  edited_output: Record<string, unknown> | null;
  current_output: Record<string, unknown>;
  metadata: Record<string, unknown>;
  updated_at: string;
}

export interface ProcessingLogEntry {
  id: string;
  stage: string;
  status: string;
  message: string;
  duration_ms: number | null;
  created_at: string;
}

export interface MeetingDetail extends Meeting {
  files: MeetingFile[];
  segments: TranscriptSegment[];
  ai_outputs: AIOutput[];
  logs: ProcessingLogEntry[];
  events: MeetingEvent[];
  // Attached by the upload endpoint only.
  validation_report?: ValidationReport;
  upload_session_id?: string;
}

/** Lightweight payload returned by the status-polling endpoint. */
export interface MeetingStatusSnapshot {
  id: string;
  processing_status: ProcessingStatus;
  processing_status_display: string;
  upload_status: UploadStatus | null;
  duration_seconds: number | null;
  updated_at: string;
  events: MeetingEvent[];
}

export interface DashboardStats {
  total_meetings: number;
  completed_meetings: number;
  processing_meetings: number;
  failed_meetings: number;
  active_jobs: number;
  total_hours_processed: number;
  average_duration_minutes: number;
  status_breakdown: Record<string, number>;
}

// --- Background jobs (Phase 5) ---------------------------------------------
export type JobStatus =
  | "queued"
  | "waiting"
  | "running"
  | "retrying"
  | "paused"
  | "cancellation_requested"
  | "canceled"
  | "succeeded"
  | "failed"
  | "expired";

export interface JobLog {
  id: string;
  stage: string;
  level: "debug" | "info" | "warning" | "error";
  message: string;
  progress: number | null;
  duration_ms: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface BackgroundJob {
  id: string;
  job_type: string;
  job_type_display: string;
  pipeline: string;
  status: JobStatus;
  status_display: string;
  priority: number;
  priority_display: string;
  progress: number;
  current_stage: string;
  queue_name: string;
  worker_id: string;
  retry_count: number;
  max_retries: number;
  error_message: string;
  duration_ms: number | null;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobDetail extends BackgroundJob {
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  metadata: Record<string, unknown>;
  stack_trace: string;
  logs: JobLog[];
}

export interface PipelineMetric {
  pipeline: string;
  total: number;
  succeeded: number;
  failed: number;
  avg_runtime_ms: number;
  success_rate: number;
}

export interface JobMetrics {
  total_jobs: number;
  queued_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  cancelled_jobs: number;
  active_jobs: number;
  success_rate: number;
  failure_rate: number;
  retry_rate: number;
  average_runtime_ms: number;
  longest_runtime_ms: number;
  status_breakdown: Record<string, number>;
  pipelines: PipelineMetric[];
}

export interface HealthComponent {
  status: "ok" | "degraded" | "down";
  [key: string]: unknown;
}

export interface HealthReport {
  status: "ok" | "degraded" | "down";
  service: string;
  components: Record<string, HealthComponent>;
}

// --- Workspace (Phase 9) ---------------------------------------------------
export type TaskStatus =
  | "backlog" | "todo" | "in_progress" | "blocked" | "review" | "completed" | "cancelled";

export interface Explain {
  confidence: string;
  confidence_score: number | null;
  source_segment_index: number | null;
  source_start_time: number | null;
  source_speaker: string;
  source_quote: string;
  source_reason: string;
  suggestion: string | null;
}

export interface WorkTask extends Explain {
  id: string;
  project: string | null;
  meeting: string | null;
  title: string;
  description: string;
  assignee: string;
  priority: string;
  status: TaskStatus;
  category: string;
  tags: string[];
  labels: string[];
  watchers: string[];
  checklist: { id: string; text: string; done: boolean }[];
  due_date: string | null;
  order: number;
  created_by_ai: boolean;
  created_at: string;
}

export interface WorkDecision extends Explain {
  id: string;
  decision: string;
  reason: string;
  participants: string[];
  status: string;
  meeting: string | null;
  created_at: string;
}

export interface WorkRisk extends Explain {
  id: string;
  risk: string;
  severity: string;
  mitigation: string;
  status: string;
  meeting: string | null;
  created_at: string;
}

export interface AISuggestion {
  id: string;
  meeting: string;
  suggestion_type: "task" | "issue" | "decision" | "risk" | "follow_up";
  status: "pending" | "approved" | "rejected";
  title: string;
  generated_json: Record<string, unknown>;
  confidence: "high" | "medium" | "low";
  confidence_score: number;
  reason: string;
  source_segment_index: number | null;
  source_start_time: number | null;
  source_speaker: string;
  quote: string;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string;
}

export interface WorkProject {
  id: string;
  workspace: string | null;
  name: string;
  description: string;
  status: string;
}

export interface WorkspaceAnalytics {
  open_tasks: number;
  completed_tasks: number;
  blocked_tasks: number;
  overdue_tasks: number;
  task_completion_rate: number;
  total_tasks: number;
  task_status_breakdown: Record<string, number>;
  open_issues: number;
  open_risks: number;
  decision_count: number;
  meeting_count: number;
  tasks_per_meeting: number;
  upcoming_deadlines: number;
  most_discussed_topics: { topic: string; count: number }[];
}

export interface KanbanColumn {
  status: TaskStatus;
  tasks: WorkTask[];
}

// --- Universal media import (Phase 14) --------------------------------------
export type MediaImportStatus =
  | "pending"
  | "analyzing"
  | "downloading"
  | "downloaded"
  | "validating"
  | "importing"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled"
  | "blocked";

export interface EpisodeInfo {
  episode_id: string;
  title: string;
  guid: string;
  url: string;
  duration: number | null;
  published_at: string;
}

/** Metadata gathered by the import "analyze" step (no download yet). */
export interface MediaSourceInfo {
  source_type: string;
  webpage_url: string;
  platform: string;
  platform_id: string;
  title: string;
  author: string;
  duration: number | null;
  thumbnail_url: string;
  published_at: string;
  license: string;
  media_kind: MediaKind;
  is_playlist: boolean;
  episodes: EpisodeInfo[];
}

export interface AnalyzeResult {
  url: string;
  ok: boolean;
  info?: MediaSourceInfo;
  error?: string;
  code?: string;
}

export interface MediaImportSession {
  id: string;
  status: MediaImportStatus;
  progress: number;
  bytes_downloaded: number;
  total_bytes: number | null;
  source_type: string;
  provider_id: string;
  source_url: string;
  platform: string;
  platform_id: string;
  title: string;
  author: string;
  thumbnail_url: string;
  published_at: string;
  license: string;
  duration_seconds: number | null;
  media_kind: MediaKind;
  requested_media: "audio" | "video";
  episode_id: string;
  playlist: string;
  meeting_language: string;
  transcript_language: string;
  ai_language: string;
  on_duplicate: DuplicateAction;
  meeting_id: string | null;
  duplicate_meeting_id: string | null;
  is_active: boolean;
  error_code: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface MediaSourceCapabilities {
  import_available: boolean;
  enabled: boolean;
  video_download: boolean;
  providers: {
    id: string;
    label: string;
    source_type: string;
    supports_resume: boolean;
  }[];
  max_duration_seconds: number | null;
}
