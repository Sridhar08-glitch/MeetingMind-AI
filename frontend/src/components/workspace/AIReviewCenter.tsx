"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { SuggestionCard } from "@/components/workspace/SuggestionCard";
import { workspaceApi } from "@/lib/api/workspace";

export function AIReviewCenter({ meetingId }: { meetingId: string }) {
  const queryClient = useQueryClient();
  const { data: suggestions, isLoading } = useQuery({
    queryKey: ["workspace", "suggestions", meetingId],
    queryFn: () => workspaceApi.suggestions({ meeting: meetingId, status: "pending" }),
    refetchInterval: 4000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["workspace"] });
  const approve = useMutation({ mutationFn: (id: string) => workspaceApi.approve(id), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: (id: string) => workspaceApi.reject(id), onSuccess: invalidate });
  const busy = approve.isPending || reject.isPending;

  const pending = suggestions ?? [];

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheck className="h-4 w-4 text-brand-600" /> AI Review Center
        </CardTitle>
        {pending.length > 0 && (
          <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
            {pending.length} pending
          </span>
        )}
      </CardHeader>
      <CardBody className="space-y-3">
        {isLoading ? (
          <p className="py-4 text-center text-sm text-muted">Loading suggestions…</p>
        ) : pending.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">
            No pending AI suggestions. Approved items appear on the board, decision log and risk register.
          </p>
        ) : (
          <>
            <p className="text-xs text-muted">
              AI extracted these from the meeting. Approve to add them to your workspace, or reject.
            </p>
            {pending.map((s) => (
              <SuggestionCard
                key={s.id}
                suggestion={s}
                busy={busy}
                onApprove={() => approve.mutate(s.id)}
                onReject={() => reject.mutate(s.id)}
              />
            ))}
          </>
        )}
      </CardBody>
    </Card>
  );
}
