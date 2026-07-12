import { api } from "./client";
import type { ApiSuccess } from "@/lib/types";

// ---- Types -----------------------------------------------------------------

export interface AgentProfile {
  name: string;
  title: string;
  role: string;
  description: string;
  capabilities: string[];
  tools: string[];
}

export interface ToolInfo {
  name: string;
  description: string;
  capability: string;
}

export interface AgentHealth {
  agent: string;
  title: string;
  runs: number;
  success_rate: number | null;
  failure_rate: number | null;
  avg_latency_ms: number | null;
  avg_confidence: number | null;
  avg_quality: number | null;
  tool_failures: number;
  validation_failures: number;
  fallbacks: number;
  last_run: string | null;
}

export interface MatrixRow {
  agent: string;
  title: string;
  [area: string]: string | boolean;
}

export interface RunStep {
  order: number;
  type: string;
  name: string;
  ok: boolean;
  duration_ms: number;
  detail: Record<string, unknown>;
}

export interface AgentResult {
  answer: string;
  reasoning: string;
  confidence: number;
  found: boolean;
  key_points: string[];
  recommendations: string[];
  next_actions: string[];
  evidence: Record<string, unknown>[];
  sources: Record<string, unknown>[];
  related_meetings: { meeting_id: string; title: string }[];
  related_decisions: Record<string, unknown>[];
  related_tasks: Record<string, unknown>[];
  related_risks: Record<string, unknown>[];
  knowledge_version: number;
  consensus_version: number;
  tools_used: string[];
  grounding_score: number;
  evidence_score: number;
  completeness_score: number;
  quality_score: number;
}

export interface AgentRun {
  id: string;
  agent: string;
  request: string;
  status: string;
  answer: string;
  reasoning: string;
  confidence: number;
  found: boolean;
  knowledge_version: number;
  consensus_version: number;
  tools_used: string[];
  quality_score: number;
  grounding_score: number;
  evidence_score: number;
  completeness_score: number;
  fallback_used: boolean;
  retry_count: number;
  provider: string;
  model: string;
  prompt_version: string;
  inference_ms: number;
  tool_latency_ms: number;
  duration_ms: number;
  validation_ok: boolean;
  created_at: string;
  sandbox?: boolean;
  result?: AgentResult;
  steps?: RunStep[];
  telemetry?: Record<string, unknown>;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  [k: string]: unknown;
}
export interface GraphEdge {
  source: string;
  target: string;
  type?: string;
}
export interface AgentGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface PlannerRun {
  id: string;
  request: string;
  policy: string;
  execution_mode: string;
  status: string;
  intent: string;
  selected_agents: string[];
  answer: string;
  reasoning: string;
  confidence: number;
  found: boolean;
  knowledge_version: number;
  consensus_version: number;
  planner_quality: number;
  requires_approval: boolean;
  approved: boolean;
  agent_count: number;
  total_ms: number;
  parallel_efficiency: number;
  created_at: string;
  result?: Record<string, unknown>;
  scores?: Record<string, number>;
  observability?: Record<string, number>;
  steps?: { order: number; phase: string; name: string; ok: boolean; duration_ms: number; detail: Record<string, unknown> }[];
  execution_graph?: AgentGraph;
}

export interface WorkflowTemplate {
  name: string;
  title: string;
  description: string;
  policy: string;
  human_required: boolean;
  stages: { type: string; agents: string[]; role: string }[];
}

export interface CollabStep {
  order: number;
  stage: string;
  agent: string;
  role: string;
  output: string;
  approved: boolean | null;
  vote: string;
  review: Record<string, unknown>;
  confidence: number;
  quality: number;
  latency_ms: number;
}

export interface CollaborationRun {
  id: string;
  workflow: string;
  request: string;
  policy: string;
  status: string;
  answer: string;
  reasoning: string;
  confidence: number;
  found: boolean;
  knowledge_version: number;
  consensus_version: number;
  collaboration_quality: number;
  agreement_rate: number | null;
  review_success_rate: number | null;
  debate_count: number;
  tool_reuse_pct: number;
  stages_count: number;
  agent_count: number;
  human_required: boolean;
  approved: boolean;
  total_ms: number;
  created_at: string;
  result?: Record<string, unknown>;
  steps?: CollabStep[];
  collaboration_graph?: AgentGraph;
}

// ---- Client ----------------------------------------------------------------

function unwrap<T>(p: Promise<{ data: ApiSuccess<T> }>): Promise<T> {
  return p.then((r) => r.data.data);
}

export type Policy = "fast" | "balanced" | "highest_quality" | "lowest_latency" | "research";
export type CollabPolicy = "sequential" | "parallel" | "review_required" | "debate_required" | "consensus_required";

export const agentsApi = {
  list: () => unwrap<{ agents: AgentProfile[]; tools: ToolInfo[] }>(api.get("/agents/")),
  matrix: () => unwrap<{ matrix: MatrixRow[] }>(api.get("/agents/matrix/")).then((d) => d.matrix),
  health: () => unwrap<{ health: AgentHealth[] }>(api.get("/agents/health/")).then((d) => d.health),
  run: (agent: string, request: string, opts: { params?: Record<string, unknown>; sandbox?: boolean } = {}) =>
    unwrap<AgentRun>(api.post("/agents/run/", { agent, request, ...opts })),
  runs: (agent?: string) =>
    unwrap<{ runs: AgentRun[] }>(api.get("/agents/runs/", { params: agent ? { agent } : {} })).then((d) => d.runs),
  runDetail: (id: string) => unwrap<AgentRun>(api.get(`/agents/runs/${id}/`)),

  planner: {
    run: (request: string, policy: Policy = "balanced", params?: Record<string, unknown>) =>
      unwrap<PlannerRun>(api.post("/agents/planner/run/", { request, policy, params })),
    runs: () => unwrap<{ runs: PlannerRun[] }>(api.get("/agents/planner/runs/")).then((d) => d.runs),
    runDetail: (id: string) => unwrap<PlannerRun>(api.get(`/agents/planner/runs/${id}/`)),
    approve: (id: string) => unwrap<PlannerRun>(api.post(`/agents/planner/runs/${id}/approve/`, {})),
    graph: (id: string) => unwrap<AgentGraph>(api.get(`/agents/planner/runs/${id}/graph/`)),
    metrics: () => unwrap<Record<string, unknown>>(api.get("/agents/planner/metrics/")),
  },

  collab: {
    templates: () => unwrap<{ templates: WorkflowTemplate[] }>(api.get("/agents/collaboration/templates/")).then((d) => d.templates),
    run: (request: string, opts: { template?: string; agents?: string[]; policy?: CollabPolicy } = {}) =>
      unwrap<CollaborationRun>(api.post("/agents/collaboration/run/", { request, ...opts })),
    runs: () => unwrap<{ runs: CollaborationRun[] }>(api.get("/agents/collaboration/runs/")).then((d) => d.runs),
    runDetail: (id: string) => unwrap<CollaborationRun>(api.get(`/agents/collaboration/runs/${id}/`)),
    approve: (id: string) => unwrap<CollaborationRun>(api.post(`/agents/collaboration/runs/${id}/approve/`, {})),
    graph: (id: string) => unwrap<AgentGraph>(api.get(`/agents/collaboration/runs/${id}/graph/`)),
    metrics: () => unwrap<Record<string, unknown>>(api.get("/agents/collaboration/metrics/")),
  },
};
