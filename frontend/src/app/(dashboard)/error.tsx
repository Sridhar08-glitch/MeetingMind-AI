"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/Button";

/** Route-level error boundary for the authenticated app. */
export default function DashboardError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surface for the console audit; no external reporting (local-only).
    console.error("Dashboard route error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-bg text-danger">
        <AlertTriangle className="h-6 w-6" />
      </div>
      <h2 className="mt-4 text-lg font-semibold text-foreground">Something went wrong</h2>
      <p className="mt-1 max-w-sm text-sm text-muted">
        This section failed to load. You can retry, or reload the page. Your data is safe.
      </p>
      {error?.digest && <p className="mt-2 text-xs text-muted">Ref: {error.digest}</p>}
      <div className="mt-5 flex gap-2">
        <Button onClick={() => reset()}>
          <RefreshCw className="mr-1.5 h-4 w-4" /> Retry
        </Button>
        <Button variant="outline" onClick={() => window.location.reload()}>Reload page</Button>
      </div>
    </div>
  );
}
