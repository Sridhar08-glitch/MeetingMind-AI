"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

/** Human titles for the static routes. Dynamic routes (e.g. a meeting) set their
 *  own title via `usePageTitle`, so we deliberately skip them here. */
const TITLES: Record<string, string> = {
  "/copilot": "Copilot",
  "/dashboard": "Dashboard",
  "/meetings": "Meetings",
  "/meetings/live": "Live meeting",
  "/meetings/upload": "Upload",
  "/workspace": "Workspace",
  "/knowledge": "Knowledge Hub",
  "/knowledge/graph": "Knowledge Graph",
  "/exports": "Export Center",
  "/executive": "Executive",
  "/agents": "Agent Center",
  "/jobs": "Jobs",
  "/settings": "Settings",
};

/** Keeps <title> in sync with the current static route. Mounted once in the shell. */
export function DocumentTitle() {
  const pathname = usePathname();
  useEffect(() => {
    const title = TITLES[pathname];
    if (title) document.title = `${title} · MeetingMind AI`;
  }, [pathname]);
  return null;
}
