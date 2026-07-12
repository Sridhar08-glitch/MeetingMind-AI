"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { demoApi } from "@/lib/api/demo";

/** Reset the demo workspace, then refetch everything so the UI shows fresh data. */
export function useResetDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => demoApi.reset(),
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}
