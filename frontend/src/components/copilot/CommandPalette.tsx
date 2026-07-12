"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity, BarChart3, Bot, BrainCircuit, CheckSquare, Download, FileText, Gauge, GitBranch, LayoutDashboard,
  LayoutGrid, Lightbulb, type LucideIcon, MessageSquareText, Mic, Network, Play, Radio, Search, Settings,
  ShieldCheck, Sparkles, Sprout, TriangleAlert, UploadCloud, Users,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  run: (router: ReturnType<typeof useRouter>) => void;
}

const COMMANDS: Command[] = [
  { id: "copilot", label: "Open Copilot", hint: "Ask anything", icon: Sparkles, run: (r) => r.push("/copilot") },
  { id: "dashboard", label: "Jump to Dashboard", icon: LayoutDashboard, run: (r) => r.push("/dashboard") },
  { id: "agents", label: "Open Agent Center", icon: Bot, run: (r) => r.push("/agents") },
  { id: "run-agent", label: "Run an Agent", icon: Sparkles, run: (r) => r.push("/agents?tab=run") },
  { id: "planner", label: "Open Planner", icon: Network, run: (r) => r.push("/agents?tab=planner") },
  { id: "collab", label: "Start a Collaboration Workflow", icon: GitBranch, run: (r) => r.push("/agents?tab=collab") },
  { id: "approvals", label: "Open Approval Center", icon: ShieldCheck, run: (r) => r.push("/agents?tab=approvals") },
  { id: "exec", label: "Open Executive Dashboard", icon: BarChart3, run: (r) => r.push("/executive") },
  { id: "benchmarks", label: "Open Benchmark Center", icon: Gauge, run: (r) => r.push("/benchmarks") },
  { id: "run-benchmark", label: "Run a Benchmark", icon: Play, run: (r) => r.push("/benchmarks?tab=run") },
  { id: "seed-suite", label: "Seed Public Suite", hint: "Benchmarks", icon: Sprout, run: (r) => r.push("/benchmarks?tab=datasets&seed=1") },
  { id: "brief", label: "Generate Executive Brief", icon: FileText, run: (r) => r.push("/executive?view=brief") },
  { id: "recs", label: "Show Recommendations", icon: Lightbulb, run: (r) => r.push("/executive?view=recommendations") },
  { id: "alerts", label: "Show Alerts", icon: TriangleAlert, run: (r) => r.push("/executive?view=alerts") },
  { id: "graph", label: "Open Knowledge Graph", icon: Network, run: (r) => r.push("/knowledge/graph") },
  { id: "knowledge", label: "Open Knowledge Hub", icon: BrainCircuit, run: (r) => r.push("/knowledge") },
  { id: "workspace", label: "Open Workspace", icon: LayoutGrid, run: (r) => r.push("/workspace") },
  { id: "create-task", label: "Create a Task", hint: "Workspace", icon: CheckSquare, run: (r) => r.push("/workspace?new=task") },
  { id: "people", label: "Open People", hint: "Manage voice identities", icon: Users, run: (r) => r.push("/people") },
  { id: "meetings", label: "Open Meetings", icon: Mic, run: (r) => r.push("/meetings") },
  { id: "live", label: "Start Live Meeting", hint: "Record live", icon: Radio, run: (r) => r.push("/meetings/live") },
  { id: "upload", label: "Upload a Meeting", icon: UploadCloud, run: (r) => r.push("/meetings/upload") },
  { id: "exports", label: "Open Export Center", icon: Download, run: (r) => r.push("/exports") },
  { id: "jobs", label: "Open Jobs", icon: Activity, run: (r) => r.push("/jobs") },
  { id: "settings", label: "Open Settings", icon: Settings, run: (r) => r.push("/settings") },
];

/** VS Code-style Ctrl/Cmd+K command palette, mounted once in the app shell. */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => {
          const next = !v;
          if (next) { setQuery(""); setActive(0); }
          return next;
        });
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Focus the input once the dialog is shown (ref only — no state updates here).
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  const trimmed = query.trim();
  const filtered = useMemo(() => {
    if (!trimmed) return COMMANDS;
    const q = trimmed.toLowerCase();
    return COMMANDS.filter((c) => c.label.toLowerCase().includes(q) || c.hint?.toLowerCase().includes(q));
  }, [trimmed]);

  // "Ask AI" is always offered as the last option when the user typed a phrase.
  const askOption = trimmed.length > 2;
  const total = filtered.length + (askOption ? 1 : 0);

  const runIndex = (i: number) => {
    if (askOption && i === filtered.length) {
      router.push(`/copilot?q=${encodeURIComponent(trimmed)}`);
    } else {
      filtered[i]?.run(router);
    }
    setOpen(false);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 px-4 pt-[12vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="h-4 w-4 text-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, total - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              else if (e.key === "Enter") { e.preventDefault(); runIndex(active); }
            }}
            placeholder="Type a command or ask AI…"
            className="h-12 w-full bg-transparent text-sm text-foreground placeholder:text-muted focus:outline-none"
          />
          <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-[10px] text-muted sm:inline">esc</kbd>
        </div>

        <ul className="max-h-80 overflow-y-auto py-1">
          {filtered.map((c, i) => (
            <li key={c.id}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => runIndex(i)}
                className={cn(
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm",
                  active === i ? "bg-brand-50 text-brand-700" : "text-foreground hover:bg-slate-50",
                )}
              >
                <c.icon className="h-4 w-4 shrink-0 text-muted" />
                <span className="flex-1">{c.label}</span>
                {c.hint && <span className="text-xs text-muted">{c.hint}</span>}
              </button>
            </li>
          ))}
          {askOption && (
            <li>
              <button
                onMouseEnter={() => setActive(filtered.length)}
                onClick={() => runIndex(filtered.length)}
                className={cn(
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm",
                  active === filtered.length ? "bg-brand-50 text-brand-700" : "text-foreground hover:bg-slate-50",
                )}
              >
                <MessageSquareText className="h-4 w-4 shrink-0 text-brand-500" />
                <span className="flex-1">Ask AI: <span className="font-medium">{trimmed}</span></span>
                <span className="text-xs text-muted">Copilot</span>
              </button>
            </li>
          )}
          {total === 0 && <li className="px-4 py-6 text-center text-sm text-muted">No matching commands.</li>}
        </ul>
      </div>
    </div>
  );
}
