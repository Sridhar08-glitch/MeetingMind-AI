import {
  Activity, BarChart3, Bot, BrainCircuit, Download, Gauge, LayoutDashboard, LayoutGrid, Mic, Network,
  Radio, Settings, Sparkles, UploadCloud, Users, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Single source of truth for primary navigation (desktop sidebar + mobile drawer). */
export const NAV_ITEMS: NavItem[] = [
  { href: "/copilot", label: "Copilot", icon: Sparkles },
  { href: "/agents", label: "Agent Center", icon: Bot },
  { href: "/executive", label: "Executive", icon: BarChart3 },
  { href: "/benchmarks", label: "Benchmarks", icon: Gauge },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/meetings", label: "Meetings", icon: Mic },
  { href: "/meetings/live", label: "Live Meeting", icon: Radio },
  { href: "/meetings/upload", label: "Upload", icon: UploadCloud },
  { href: "/workspace", label: "Workspace", icon: LayoutGrid },
  { href: "/people", label: "People", icon: Users },
  { href: "/knowledge", label: "Knowledge Hub", icon: BrainCircuit },
  { href: "/knowledge/graph", label: "Knowledge Graph", icon: Network },
  { href: "/exports", label: "Export Center", icon: Download },
  { href: "/jobs", label: "Jobs", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

/** The active item is the longest href that prefixes the current path. */
export function activeHref(pathname: string): string | undefined {
  return NAV_ITEMS
    .filter(({ href }) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;
}
