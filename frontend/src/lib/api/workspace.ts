import { api } from "./client";
import type {
  AISuggestion,
  ApiSuccess,
  KanbanColumn,
  Paginated,
  TaskStatus,
  WorkDecision,
  WorkProject,
  WorkRisk,
  WorkTask,
  WorkspaceAnalytics,
} from "@/lib/types";

export interface ActivityEntry {
  id: string;
  verb: string;
  entity_type: string;
  entity_id: string | null;
  summary: string;
  meeting: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export const workspaceApi = {
  async analytics(): Promise<WorkspaceAnalytics> {
    const { data } = await api.get<ApiSuccess<WorkspaceAnalytics>>("/workspace/analytics/");
    return data.data;
  },

  async activity(limit = 8): Promise<ActivityEntry[]> {
    const { data } = await api.get<Paginated<ActivityEntry>>("/workspace/activity/", {
      params: { page_size: limit },
    });
    return data.results;
  },

  async board(): Promise<KanbanColumn[]> {
    const { data } = await api.get<ApiSuccess<KanbanColumn[]>>("/workspace/tasks/board/");
    return data.data;
  },

  async moveTask(id: string, status: TaskStatus, order = 0): Promise<WorkTask> {
    const { data } = await api.post<ApiSuccess<WorkTask>>(`/workspace/tasks/${id}/move/`, { status, order });
    return data.data;
  },

  async suggestions(params: { meeting?: string; status?: string } = {}): Promise<AISuggestion[]> {
    const { data } = await api.get<Paginated<AISuggestion>>("/workspace/suggestions/", {
      params: { ...params, page_size: 100 },
    });
    return data.results;
  },

  async approve(id: string, opts: { edited?: Record<string, unknown>; on_duplicate?: string } = {}): Promise<void> {
    await api.post(`/workspace/suggestions/${id}/approve/`, opts);
  },

  async reject(id: string, reviewer_notes = ""): Promise<void> {
    await api.post(`/workspace/suggestions/${id}/reject/`, { reviewer_notes });
  },

  async bulk(ids: string[], action: "approve" | "reject" | "archive"): Promise<void> {
    await api.post("/workspace/suggestions/bulk/", { ids, action });
  },

  async suggestionStats(): Promise<{ pending: number; needs_review: number; approved: number; rejected: number; average_confidence: number; approval_rate: number; rejection_rate: number }> {
    const { data } = await api.get<ApiSuccess<{ pending: number; needs_review: number; approved: number; rejected: number; average_confidence: number; approval_rate: number; rejection_rate: number }>>("/workspace/suggestions/stats/");
    return data.data;
  },

  async taskRelated(id: string): Promise<Record<string, unknown>> {
    const { data } = await api.get<ApiSuccess<Record<string, unknown>>>(`/workspace/tasks/${id}/related/`);
    return data.data;
  },

  async taskComments(id: string): Promise<{ id: string; body: string; author: string | null; created_at: string }[]> {
    const { data } = await api.get<ApiSuccess<{ id: string; body: string; author: string | null; created_at: string }[]>>(`/workspace/tasks/${id}/comments/`);
    return data.data;
  },

  async addComment(id: string, body: string): Promise<void> {
    await api.post(`/workspace/tasks/${id}/comments/`, { body });
  },

  async taskActivity(id: string): Promise<{ id: string; verb: string; summary: string; created_at: string }[]> {
    const { data } = await api.get<ApiSuccess<{ id: string; verb: string; summary: string; created_at: string }[]>>(`/workspace/tasks/${id}/activity/`);
    return data.data;
  },

  async decisions(): Promise<WorkDecision[]> {
    const { data } = await api.get<Paginated<WorkDecision>>("/workspace/decisions/", { params: { page_size: 100 } });
    return data.results;
  },

  async risks(): Promise<WorkRisk[]> {
    const { data } = await api.get<Paginated<WorkRisk>>("/workspace/risks/", { params: { page_size: 100 } });
    return data.results;
  },

  async projects(): Promise<WorkProject[]> {
    const { data } = await api.get<Paginated<WorkProject>>("/workspace/projects/", { params: { page_size: 100 } });
    return data.results;
  },

  async generateReport(reportType: string, meeting?: string): Promise<{ content: string; title: string }> {
    const { data } = await api.post<ApiSuccess<{ content: string; title: string }>>(
      "/workspace/reports/generate/", { report_type: reportType, meeting },
    );
    return data.data;
  },
};
