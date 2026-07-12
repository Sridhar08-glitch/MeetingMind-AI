import { api } from "./client";
import type { ApiSuccess } from "@/lib/types";
import type { SearchResult } from "./knowledge";

// ---- Types -----------------------------------------------------------------

export interface HealthDim {
  score: number;
  status: "excellent" | "good" | "warning" | "critical";
  formula: string;
  evidence: Record<string, unknown>;
}

export interface WorkspaceHealth {
  overall: HealthDim;
  dimensions: Record<string, HealthDim>;
  knowledge_version: number;
}

export interface ScorePart {
  score: number;
  explanation: string;
}

export interface WorkspaceScore {
  score: number;
  out_of: number;
  status: string;
  breakdown: Record<string, ScorePart>;
}

export interface ExecRecommendation {
  id: string;
  key: string;
  priority: string;
  recommendation: string;
  reason: string;
  confidence: number;
  impact: Record<string, number>;
  related_projects: { id: string; name: string }[];
  consensus: Record<string, unknown> | null;
  status: string;
  knowledge_version: number;
  consensus_version: number;
}

export interface ExecAlert {
  id: string;
  type: string;
  severity: "info" | "warning" | "critical";
  status: string;
  title: string;
  detail: string;
  evidence: Record<string, unknown>;
  knowledge_version: number;
  last_seen_at: string;
}

export interface ExecPrediction {
  metric: string;
  current_value: number;
  expected_value: number;
  horizon_days: number;
  confidence: number;
  message: string;
}

export interface ProjectHealthRow {
  project_id: string;
  name: string | null;
  overall: number;
  status: string;
}

export interface ExecDashboard {
  cache_key: string;
  snapshot_version: number;
  knowledge_version: number;
  consensus_version: number;
  generated_at: string;
  processing_ms: number;
  stale: boolean;
  health: WorkspaceHealth;
  score: WorkspaceScore;
  analytics: ExecAnalytics;
  organization_insights: Record<string, unknown>;
  knowledge_freshness: Record<string, unknown>;
  project_health: ProjectHealthRow[];
  recommendations: ExecRecommendation[];
  alerts: ExecAlert[];
  predictions: ExecPrediction[];
}

export interface LeaderboardEntry {
  name?: string;
  label?: string;
  count: number;
  meetings?: number;
}

export interface ExecAnalytics {
  growth: Record<string, { period?: string; at?: string; count?: number; value?: number }[]>;
  trends: Record<string, { at: string; value: number }[]>;
  ai_usage: { retrievals: number; by_kind: { kind: string; n: number }[] };
  ai_accuracy: Record<string, number | null>;
  leaderboards: Record<string, LeaderboardEntry[]>;
}

export interface Explanation {
  scope: string;
  metric: string;
  value: number | null;
  formula: string;
  evidence: Record<string, unknown>;
  confidence: number | null;
  knowledge_version: number;
  snapshot_version: number;
  generated_at: string;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  ref?: string | null;
}
export interface GraphEdge {
  source: string;
  target: string;
  type?: string;
}
export interface KGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  counts?: Record<string, number>;
}

export interface KnowledgeVersionRow {
  version: number;
  indexed_at: string;
  trigger: string;
  reason: string;
  embedding_version: string | null;
  meetings: number;
  projects: number;
  tasks: number;
  decisions: number;
  risks: number;
  items: number;
}

export interface TopicTimeline {
  topic: string;
  periods: { period: string; count: number }[];
  milestones: {
    at: string;
    event: string;
    entity_type: string;
    entity_id: string;
    version: number;
    knowledge_version: number;
    title: string;
  }[];
  total_mentions: number;
}

export interface TimeTravelStats {
  as_of: string;
  knowledge_version: number;
  items: number;
  meetings: number;
  by_entity_type: Record<string, number>;
}

export interface NLResult {
  query: string;
  interpreted: Record<string, unknown>;
  filters: Record<string, unknown>;
  search_text: string;
  count: number;
  results: SearchResult[];
}

export interface ExecutiveReport {
  period: string;
  since: string;
  generated_at: string;
  executive_summary: string;
  top_achievements: { id: string; title: string }[];
  blocked_projects: { name: string }[];
  critical_risks: { id: string; risk: string; severity: string }[];
  important_decisions: { id: string; decision: string }[];
  upcoming_deadlines: { id: string; title: string; due_date: string }[];
  ai_recommendations: ExecRecommendation[];
  knowledge_changes: { version_changes: number; events: number };
  decision_changes: { topic: string; current_position: string; trend: string }[];
  trend_changes: { health_delta: number | null };
}

// ---- Client ----------------------------------------------------------------

function unwrap<T>(p: Promise<{ data: ApiSuccess<T> }>): Promise<T> {
  return p.then((r) => r.data.data);
}

export const executiveApi = {
  dashboard: (refresh = false) =>
    unwrap<ExecDashboard>(api.get("/knowledge/executive/dashboard/", { params: refresh ? { refresh: 1 } : {} })),
  refresh: () => unwrap<{ snapshot_version: number }>(api.post("/knowledge/executive/refresh/", {})),
  health: () => unwrap<WorkspaceHealth>(api.get("/knowledge/executive/health/")),
  score: () => unwrap<WorkspaceScore>(api.get("/knowledge/executive/score/")),
  analytics: () => unwrap<ExecAnalytics>(api.get("/knowledge/executive/analytics/")),
  insights: () => unwrap<Record<string, unknown>>(api.get("/knowledge/executive/insights/")),
  recommendations: () =>
    unwrap<{ recommendations: ExecRecommendation[] }>(api.get("/knowledge/executive/recommendations/")).then((d) => d.recommendations),
  setRecommendationStatus: (id: string, status: string) =>
    api.post(`/knowledge/executive/recommendations/${id}/status/`, { status }),
  alerts: (status?: string) =>
    unwrap<{ alerts: ExecAlert[] }>(api.get("/knowledge/executive/alerts/", { params: status ? { status } : {} })).then((d) => d.alerts),
  setAlertStatus: (id: string, status: string) =>
    api.post(`/knowledge/executive/alerts/${id}/status/`, { status }),
  history: () => unwrap<Record<string, Record<string, number> | null>>(api.get("/knowledge/executive/history/")),
  whatChanged: (since?: string) =>
    unwrap<Record<string, unknown>>(api.get("/knowledge/executive/what-changed/", { params: since ? { since } : {} })),
  predictions: () =>
    unwrap<{ predictions: ExecPrediction[]; detail: Record<string, unknown> }>(api.get("/knowledge/executive/predictions/")),
  trends: (granularity = "daily", metric?: string) =>
    unwrap<{ granularity: string; points: { metric: string; period_start: string; value: number }[] }>(
      api.get("/knowledge/executive/trends/", { params: { granularity, ...(metric ? { metric } : {}) } }),
    ),
  explain: (metric: string, scope = "organization") =>
    unwrap<Explanation>(api.get("/knowledge/executive/explain/", { params: { metric, scope } })),
  brief: (period: "today" | "week" | "month" = "week") =>
    unwrap<ExecutiveReport>(api.get("/knowledge/executive/brief/", { params: { period } })),

  // Graph + NL search
  peopleGraph: (project?: string) =>
    unwrap<KGraph>(api.get("/knowledge/people-graph/", { params: project ? { project } : {} })),
  knowledgeGraph: (params: { project?: string; meeting?: string } = {}) =>
    unwrap<KGraph>(api.get("/knowledge/graph/", { params })),
  nlQuery: (q: string) => unwrap<NLResult>(api.post("/knowledge/nl-query/", { q })),

  // Temporal (11A)
  versions: () =>
    unwrap<{ count: number; versions: KnowledgeVersionRow[] }>(api.get("/knowledge/versions/")).then((d) => d.versions),
  timeline: (topic: string) => unwrap<TopicTimeline>(api.get("/knowledge/timeline/", { params: { topic } })),
  timeTravel: (asOf: string) => unwrap<TimeTravelStats>(api.get("/knowledge/timetravel/", { params: { as_of: asOf } })),
};
