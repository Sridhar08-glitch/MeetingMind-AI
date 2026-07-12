import { api } from "./client";
import type {
  ApiSuccess,
  BackgroundJob,
  HealthReport,
  JobDetail,
  JobLog,
  JobMetrics,
  Paginated,
} from "@/lib/types";

export interface JobListParams {
  page?: number;
  status?: string;
  pipeline?: string;
  job_type?: string;
  priority?: number;
  meeting?: string;
  ordering?: string;
}

export const jobsApi = {
  async list(params: JobListParams = {}): Promise<Paginated<BackgroundJob>> {
    const { data } = await api.get<Paginated<BackgroundJob>>("/jobs/", { params });
    return data;
  },

  async retrieve(id: string): Promise<JobDetail> {
    const { data } = await api.get<JobDetail>(`/jobs/${id}/`);
    return data;
  },

  async logs(id: string): Promise<JobLog[]> {
    const { data } = await api.get<ApiSuccess<JobLog[]>>(`/jobs/${id}/logs/`);
    return data.data;
  },

  async metrics(): Promise<JobMetrics> {
    const { data } = await api.get<ApiSuccess<JobMetrics>>("/jobs/metrics/");
    return data.data;
  },

  async health(): Promise<HealthReport> {
    // Health lives at the API root, not under /jobs.
    const { data } = await api.get<HealthReport>("/health/");
    return data;
  },

  async control(id: string, action: "retry" | "cancel" | "pause" | "resume" | "requeue"): Promise<BackgroundJob> {
    const { data } = await api.post<ApiSuccess<BackgroundJob>>(`/jobs/${id}/${action}/`, {});
    return data.data;
  },
};
