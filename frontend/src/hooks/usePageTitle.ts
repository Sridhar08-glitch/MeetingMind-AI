"use client";

import { useEffect } from "react";

/** Set the document title for a page (dynamic routes use this to include names). */
export function usePageTitle(title: string | undefined | null) {
  useEffect(() => {
    if (!title) return;
    document.title = `${title} · MeetingMind AI`;
  }, [title]);
}
