import { api } from "./client";
import type { ApiSuccess } from "@/lib/types";

// ---- Types -----------------------------------------------------------------

export interface SearchResult {
  entity_type: string;
  entity_id: string;
  title: string;
  snippet: string;
  meeting_id: string | null;
  meeting_title: string | null;
  project_id: string | null;
  speaker: string;
  timestamp: number | null;
  occurred_at: string;
  confidence: number;
}

export interface KnowledgeFreshness {
  items_indexed: number;
  meetings_indexed: number;
  projects_included: number;
  last_updated: string | null;
}

export interface ChatSource {
  meeting_id: string | null;
  meeting_title: string | null;
  project_id: string | null;
  entity_type: string;
  speaker: string;
  timestamp: number | null;
  quote: string;
  confidence: number;
}

export interface ChatAnswer {
  answer: string;
  found: boolean;
  sources: ChatSource[];
  knowledge_freshness: KnowledgeFreshness;
  prompt_version?: string;
  provider?: string;
  model?: string;
}

export interface Insights {
  meetings_analyzed: number;
  top_topics: { label: string; count: number; meetings: number; meeting_ids: string[] }[];
  top_technologies: { label: string; count: number; meetings: number }[];
  frequent_people: { label: string; count: number }[];
  frequent_customers: { label: string; count: number }[];
  recurring_risks: { topic: string; count: number; severity: string; risk_ids: string[] }[];
  overdue_tasks: { count: number; task_ids: string[] };
  blocked_tasks: { count: number; task_ids: string[] };
  project_health: {
    project_id: string; name: string; status: string; tasks: number;
    completed: number; completion_rate: number; open_risks: number; meetings: number;
  }[];
}

export interface Recommendation {
  priority: "high" | "medium" | "low";
  title: string;
  detail: string;
  evidence: Record<string, unknown>;
}

export interface ExecutiveBrief {
  period: string;
  brief: string;
  generated_at: string;
  provider: string;
  model: string;
  data: Record<string, unknown>;
}

export interface SearchFilters {
  project?: string;
  meeting?: string;
  entity_type?: string;
  speaker?: string;
  language?: string;
  date_from?: string;
  date_to?: string;
}

// ---- Client ----------------------------------------------------------------

export const knowledgeApi = {
  async search(q: string, filters: SearchFilters = {}, k = 20): Promise<{ query: string; count: number; results: SearchResult[] }> {
    const { data } = await api.get<ApiSuccess<{ query: string; count: number; results: SearchResult[] }>>(
      "/knowledge/search/",
      { params: { q, k, ...filters } },
    );
    return data.data;
  },

  async chat(question: string, opts: { project_id?: string; filters?: SearchFilters; k?: number } = {}): Promise<ChatAnswer> {
    const { data } = await api.post<ApiSuccess<ChatAnswer>>("/knowledge/chat/", { question, ...opts });
    return data.data;
  },

  async stats(): Promise<KnowledgeFreshness> {
    const { data } = await api.get<ApiSuccess<KnowledgeFreshness>>("/knowledge/stats/");
    return data.data;
  },

  async insights(): Promise<Insights> {
    const { data } = await api.get<ApiSuccess<Insights>>("/knowledge/insights/");
    return data.data;
  },

  async recommendations(): Promise<Recommendation[]> {
    const { data } = await api.get<ApiSuccess<{ recommendations: Recommendation[] }>>("/knowledge/recommendations/");
    return data.data.recommendations;
  },

  async brief(period: "daily" | "weekly" | "monthly" = "weekly"): Promise<ExecutiveBrief> {
    const { data } = await api.get<ApiSuccess<ExecutiveBrief>>("/knowledge/brief/", { params: { period } });
    return data.data;
  },

  async reindex(): Promise<KnowledgeFreshness & { meetings_indexed: number }> {
    const { data } = await api.post<ApiSuccess<KnowledgeFreshness & { meetings_indexed: number }>>("/knowledge/reindex/", {});
    return data.data;
  },
};
