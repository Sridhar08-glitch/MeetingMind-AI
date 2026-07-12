"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { jobsApi, type JobListParams } from "@/lib/api/jobs";
import type { JobDetail, JobStatus } from "@/lib/types";

export const jobKeys = {
  all: ["jobs"] as const,
  list: (params: JobListParams) => ["jobs", "list", params] as const,
  detail: (id: string) => ["jobs", "detail", id] as const,
  metrics: ["jobs", "metrics"] as const,
  health: ["jobs", "health"] as const,
};

const ACTIVE: ReadonlySet<JobStatus> = new Set<JobStatus>([
  "queued",
  "waiting",
  "running",
  "retrying",
  "cancellation_requested",
]);

export function isJobActive(status: JobStatus | undefined): boolean {
  return status !== undefined && ACTIVE.has(status);
}

export function useJobs(params: JobListParams) {
  return useQuery({
    queryKey: jobKeys.list(params),
    queryFn: () => jobsApi.list(params),
    refetchInterval: 4000, // live dashboard
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: jobKeys.detail(id),
    queryFn: () => jobsApi.retrieve(id),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      isJobActive((query.state.data as JobDetail | undefined)?.status) ? 2500 : false,
  });
}

export function useJobMetrics() {
  return useQuery({
    queryKey: jobKeys.metrics,
    queryFn: () => jobsApi.metrics(),
    refetchInterval: 5000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: jobKeys.health,
    queryFn: () => jobsApi.health(),
    refetchInterval: 10000,
  });
}

export function useJobControl(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: "retry" | "cancel" | "pause" | "resume" | "requeue") =>
      jobsApi.control(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: jobKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}
