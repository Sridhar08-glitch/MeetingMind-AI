"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  meetingsApi,
  type MeetingListParams,
  type MeetingUpdatePayload,
  type UploadPayload,
} from "@/lib/api/meetings";
import type { MeetingDetail, ProcessingStatus } from "@/lib/types";
import { toast } from "@/store/toast";
import { usePreferencesStore } from "@/store/preferences";

export const meetingKeys = {
  all: ["meetings"] as const,
  list: (params: MeetingListParams) => ["meetings", "list", params] as const,
  detail: (id: string) => ["meetings", "detail", id] as const,
  transcript: (id: string) => ["meetings", "transcript", id] as const,
  ai: (id: string) => ["meetings", "ai", id] as const,
  stats: ["meetings", "dashboard-stats"] as const,
};

/** Processing states still "in flight" — the UI should keep polling for updates. */
const IN_PROGRESS: ReadonlySet<ProcessingStatus> = new Set<ProcessingStatus>([
  "queued",
  "running",
  "retrying",
]);

export function isInProgress(status: ProcessingStatus | null | undefined): boolean {
  return status != null && IN_PROGRESS.has(status);
}

export function useMeetings(params: MeetingListParams) {
  return useQuery({
    queryKey: meetingKeys.list(params),
    queryFn: () => meetingsApi.list(params),
  });
}

export function useMeeting(id: string) {
  return useQuery({
    queryKey: meetingKeys.detail(id),
    queryFn: () => meetingsApi.retrieve(id),
    enabled: Boolean(id),
    // While the meeting is still processing, refetch every 3s so the detail
    // page updates itself without a manual refresh.
    refetchInterval: (query) =>
      isInProgress((query.state.data as MeetingDetail | undefined)?.processing_status) ? 3000 : false,
  });
}

export function useTranscript(id: string, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: meetingKeys.transcript(id),
    queryFn: () => meetingsApi.transcript(id),
    enabled: Boolean(id),
    refetchInterval: poll ? 3000 : false,
  });
}

export function useAIAnalysis(id: string, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: meetingKeys.ai(id),
    queryFn: () => meetingsApi.ai(id),
    enabled: Boolean(id),
    refetchInterval: poll ? 3000 : false,
  });
}

export function useDashboardStats() {
  return useQuery({
    queryKey: meetingKeys.stats,
    queryFn: () => meetingsApi.dashboardStats(),
  });
}

export function useUploadMeeting(onProgress?: (percent: number) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UploadPayload) => meetingsApi.upload(payload, onProgress),
    onSuccess: (meeting) => {
      queryClient.invalidateQueries({ queryKey: meetingKeys.all });
      queryClient.setQueryData(meetingKeys.detail(meeting.id), meeting);
    },
  });
}

export function useUpdateMeeting(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MeetingUpdatePayload) => meetingsApi.update(id, payload),
    onSuccess: (meeting) => {
      queryClient.setQueryData(meetingKeys.detail(id), meeting);
      queryClient.invalidateQueries({ queryKey: meetingKeys.list({}) });
    },
  });
}

export function useDeleteMeeting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => meetingsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: meetingKeys.all });
    },
  });
}

export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => meetingsApi.toggleFavorite(id),
    onSuccess: (isFavorite, id) => {
      queryClient.invalidateQueries({ queryKey: meetingKeys.all });
      queryClient.invalidateQueries({ queryKey: meetingKeys.detail(id) });
      toast.success(isFavorite ? "Added to favorites" : "Removed from favorites");
    },
  });
}

/**
 * App-wide watcher that raises a toast when a meeting finishes processing.
 * Mounted once in the dashboard layout. Polls fast only while something is in
 * flight, and never toasts for meetings it saw for the first time (so mounting
 * doesn't replay history).
 */
export function useProcessingToasts() {
  const seen = useRef<Map<string, ProcessingStatus> | null>(null);
  const { data } = useQuery({
    queryKey: ["processing-watch"],
    queryFn: () => meetingsApi.list({ ordering: "-created_at", page_size: 15 }),
    refetchInterval: (query) => {
      const items = query.state.data?.results ?? [];
      return items.some((m) => isInProgress(m.processing_status)) ? 4000 : 20000;
    },
  });

  useEffect(() => {
    const items = data?.results;
    if (!items) return;
    // First snapshot: record statuses without toasting.
    if (seen.current === null) {
      seen.current = new Map(items.map((m) => [m.id, m.processing_status]));
      return;
    }
    for (const m of items) {
      const prev = seen.current.get(m.id);
      if (prev && prev !== m.processing_status && isInProgress(prev)) {
        const notify = usePreferencesStore.getState().notifyOnComplete;
        if (notify && m.processing_status === "completed") {
          // Rich notification: pull the word + action-item counts for context.
          Promise.all([
            meetingsApi.transcript(m.id).catch(() => null),
            meetingsApi.ai(m.id).catch(() => null),
          ]).then(([tx, ai]) => {
            const bits = ["Transcript ready"];
            const words = tx?.transcript?.word_count;
            if (words != null) bits.push(`${words} words`);
            const actions = ai?.action_items?.length;
            if (actions != null) bits.push(`${actions} action item${actions === 1 ? "" : "s"}`);
            toast.success(`✅ ${m.title}`, bits.join(" · "), {
              id: `done-${m.id}`,
              href: `/meetings/${m.id}`,
            });
          });
        } else if (notify && m.processing_status === "failed") {
          toast.error("Processing failed", m.title, { id: `fail-${m.id}`, href: `/meetings/${m.id}` });
        }
      }
      seen.current.set(m.id, m.processing_status);
    }
  }, [data]);
}
