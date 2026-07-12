"use client";

import { useState, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  Activity, Bot, CheckCircle2, GitBranch, Gauge, History, LayoutGrid,
  Network, ShieldCheck, Sparkles, Wrench,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner, EmptyState, SkeletonGrid, SkeletonList, ErrorState } from "@/components/ui/Feedback";
import { Markdown } from "@/components/ui/Markdown";
import { AgentGraph } from "@/components/agents/AgentGraph";
import {
  agentsApi, type AgentRun, type CollaborationRun, type PlannerRun, type Policy,
} from "@/lib/api/agents";
import { cn } from "@/lib/utils";

type Tab = "market" | "run" | "planner" | "collab" | "history" | "approvals" | "tools" | "metrics";

const TABS: { id: Tab; label: string; icon: typeof Bot }[] = [
  { id: "market", label: "Marketplace", icon: LayoutGrid },
  { id: "run", label: "Run Agent", icon: Sparkles },
  { id: "planner", label: "Planner", icon: Network },
  { id: "collab", label: "Collaboration", icon: GitBranch },
  { id: "history", label: "History", icon: History },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "metrics", label: "Metrics", icon: Gauge },
];

export default function AgentCenterPage() {
  const params = useSearchParams();
  const initial = (params.get("tab") as Tab) || "market";
  const [tab, setTab] = useState<Tab>(TABS.some((t) => t.id === initial) ? initial : "market");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
          <Bot className="h-6 w-6 text-brand-500" /> AI Agent Center
        </h1>
        <p className="mt-1 text-sm text-muted">
          A local AI operations console — run specialized agents, orchestrate the planner, and coordinate collaborative workflows.
        </p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)}
            className={cn("flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === id ? "border-brand-500 text-brand-600" : "border-transparent text-muted hover:text-foreground")}>
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "market" && <Marketplace />}
      {tab === "run" && <RunAgent />}
      {tab === "planner" && <PlannerConsole />}
      {tab === "collab" && <CollaborationConsole />}
      {tab === "history" && <RunHistory />}
      {tab === "approvals" && <Approvals />}
      {tab === "tools" && <Tools />}
      {tab === "metrics" && <Metrics />}
    </div>
  );
}

// ---- Explainability strip (reused) ----------------------------------------

function Explain({ items }: { items: [string, ReactNode][] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-3 text-xs text-muted">
      {items.filter(([, v]) => v !== null && v !== undefined && v !== "").map(([k, v]) => (
        <span key={k}><span className="text-foreground">{k}:</span> {v}</span>
      ))}
    </div>
  );
}

function ScoreBadge({ label, value, tone = "brand" }: { label: string; value: number | string; tone?: string }) {
  const color = tone === "green" ? "text-success" : tone === "warn" ? "text-warning" : "text-brand-600";
  return (
    <div className="rounded-lg border border-border px-3 py-1.5 text-center">
      <p className={cn("text-lg font-bold", color)}>{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
    </div>
  );
}

// ---- Marketplace + health + reputation ------------------------------------

function Marketplace() {
  const agents = useQuery({ queryKey: ["agents", "list"], queryFn: () => agentsApi.list() });
  const health = useQuery({ queryKey: ["agents", "health"], queryFn: () => agentsApi.health() });
  if (agents.isLoading) return <SkeletonGrid count={6} />;
  if (agents.isError) return <ErrorState title="Couldn't load agents" onRetry={() => agents.refetch()} />;
  const healthBy = new Map((health.data ?? []).map((h) => [h.agent, h]));
  const leaderboard = [...(health.data ?? [])].filter((h) => h.runs > 0)
    .sort((a, b) => (b.avg_quality ?? 0) - (a.avg_quality ?? 0)).slice(0, 5);

  return (
    <div className="space-y-6">
      {leaderboard.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4" /> Reputation leaderboard</CardTitle></CardHeader>
          <CardBody className="space-y-1.5">
            {leaderboard.map((h, i) => (
              <div key={h.agent} className="flex items-center justify-between text-sm">
                <span className="text-foreground">{i + 1}. {h.title}</span>
                <span className="text-xs text-muted">quality {h.avg_quality} · {Math.round((h.success_rate ?? 0) * 100)}% success · {h.runs} runs</span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {agents.data?.agents.map((a) => {
          const h = healthBy.get(a.name);
          return (
            <Card key={a.name}>
              <CardBody className="space-y-2">
                <div className="flex items-center gap-2">
                  <Bot className="h-5 w-5 text-brand-500" />
                  <span className="font-semibold text-foreground">{a.title}</span>
                </div>
                <p className="text-xs text-muted">{a.description}</p>
                <div className="flex flex-wrap gap-1">
                  {a.tools.map((t) => (
                    <span key={t} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-foreground">{t}</span>
                  ))}
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-border pt-2 text-xs text-muted">
                  <span>{h?.runs ?? 0} runs</span>
                  {h?.success_rate != null && <span>{Math.round(h.success_rate * 100)}% success</span>}
                  {h?.avg_quality != null && <span>quality {h.avg_quality}</span>}
                  {h?.avg_confidence != null && <span>conf {h.avg_confidence}</span>}
                  {h?.avg_latency_ms != null && <span>{(h.avg_latency_ms / 1000).toFixed(1)}s</span>}
                </div>
              </CardBody>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

// ---- Run a single agent ----------------------------------------------------

function RunAgent() {
  const agents = useQuery({ queryKey: ["agents", "list"], queryFn: () => agentsApi.list() });
  const [agent, setAgent] = useState("knowledge_agent");
  const [prompt, setPrompt] = useState("");
  const [sandbox, setSandbox] = useState(false);
  const [result, setResult] = useState<AgentRun | null>(null);
  const run = useMutation({
    mutationFn: () => agentsApi.run(agent, prompt.trim(), { sandbox }),
    onSuccess: setResult,
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <select value={agent} onChange={(e) => setAgent(e.target.value)}
              className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground">
              {agents.data?.agents.map((a) => <option key={a.name} value={a.name}>{a.title}</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-sm text-muted">
              <input type="checkbox" checked={sandbox} onChange={(e) => setSandbox(e.target.checked)} /> Sandbox
            </label>
          </div>
          <div className="flex gap-2">
            <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Ask this agent…" />
            <Button onClick={() => prompt.trim() && run.mutate()} isLoading={run.isPending}>Run</Button>
          </div>
        </CardBody>
      </Card>
      {run.isPending && <Spinner />}
      {result && <AgentRunResult run={result} />}
    </div>
  );
}

function AgentRunResult({ run }: { run: AgentRun }) {
  const r = run.result;
  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>{run.agent.replace(/_/g, " ")}{run.sandbox && <span className="ml-2 rounded bg-warning/15 px-1.5 py-0.5 text-xs text-warning">sandbox</span>}</CardTitle>
        <div className="flex gap-2">
          <ScoreBadge label="Confidence" value={Math.round(run.confidence)} tone="green" />
          <ScoreBadge label="Quality" value={Math.round(run.quality_score)} />
        </div>
      </CardHeader>
      <CardBody className="space-y-3">
        <Markdown>{run.answer}</Markdown>
        {run.reasoning && <p className="text-xs italic text-muted">Reasoning: {run.reasoning}</p>}
        {r && r.recommendations.length > 0 && (
          <Section title="Recommendations" items={r.recommendations} />
        )}
        {r && r.next_actions.length > 0 && <Section title="Next actions" items={r.next_actions} />}
        {run.steps && run.steps.length > 0 && <StepTrace steps={run.steps} />}
        <Explain items={[
          ["Tools", run.tools_used.join(", ")],
          ["Knowledge v", run.knowledge_version],
          ["Consensus v", run.consensus_version],
          ["Model", `${run.provider} ${run.model}`],
          ["Grounding", run.grounding_score],
          ["Latency", `${(run.duration_ms / 1000).toFixed(1)}s`],
          ["Fallback", run.fallback_used ? "yes" : "no"],
        ]} />
      </CardBody>
    </Card>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{title}</p>
      <ul className="list-inside list-disc space-y-0.5 text-sm text-foreground">
        {items.slice(0, 8).map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </div>
  );
}

function StepTrace({ steps }: { steps: { type: string; name: string; ok: boolean; duration_ms: number }[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {steps.map((s, i) => (
        <span key={i} className={cn("rounded px-2 py-0.5 text-[11px]",
          s.ok ? "bg-success-bg text-success" : "bg-danger-bg text-danger")}>
          {s.type}:{s.name.replace(/_/g, " ")} {s.duration_ms ? `${s.duration_ms}ms` : ""}
        </span>
      ))}
    </div>
  );
}

// ---- Planner console -------------------------------------------------------

const POLICIES: Policy[] = ["fast", "balanced", "highest_quality", "lowest_latency", "research"];

function PlannerConsole() {
  const [prompt, setPrompt] = useState("");
  const [policy, setPolicy] = useState<Policy>("balanced");
  const [result, setResult] = useState<PlannerRun | null>(null);
  const run = useMutation({ mutationFn: () => agentsApi.planner.run(prompt.trim(), policy), onSuccess: setResult });

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap gap-1">
            {POLICIES.map((p) => (
              <Button key={p} size="sm" variant={policy === p ? "primary" : "outline"} onClick={() => setPolicy(p)}>
                {p.replace(/_/g, " ")}
              </Button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Ask the planner — it selects and orchestrates agents…" />
            <Button onClick={() => prompt.trim() && run.mutate()} isLoading={run.isPending}>Plan</Button>
          </div>
        </CardBody>
      </Card>
      {run.isPending && <Spinner />}
      {result && <PlannerResult plan={result} />}
    </div>
  );
}

function PlannerResult({ plan }: { plan: PlannerRun }) {
  const obs = plan.observability ?? {};
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Planner result · {plan.execution_mode}</CardTitle>
          <div className="flex gap-2">
            <ScoreBadge label="Confidence" value={Math.round(plan.confidence)} tone="green" />
            <ScoreBadge label="Quality" value={Math.round(plan.planner_quality)} />
          </div>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-xs text-muted">Intent: {plan.intent}</p>
          <div className="flex flex-wrap gap-1">
            {plan.selected_agents.map((a) => (
              <span key={a} className="rounded-full bg-brand-50 px-2 py-0.5 text-xs text-brand-700">{a.replace(/_agent$/, "")}</span>
            ))}
          </div>
          <Markdown>{plan.answer}</Markdown>
          <Explain items={[
            ["Knowledge v", plan.knowledge_version], ["Consensus v", plan.consensus_version],
            ["Parallel eff.", `${plan.parallel_efficiency}×`], ["Agents", plan.agent_count],
            ["Total", `${(plan.total_ms / 1000).toFixed(1)}s`],
            ["Tool calls", obs.tool_calls as number], ["LLM calls", obs.llm_calls as number],
          ]} />
        </CardBody>
      </Card>
      {plan.execution_graph && (
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Network className="h-4 w-4" /> Execution graph</CardTitle></CardHeader>
          <CardBody><AgentGraph graph={plan.execution_graph} /></CardBody></Card>
      )}
    </div>
  );
}

// ---- Collaboration console -------------------------------------------------

function CollaborationConsole() {
  const templates = useQuery({ queryKey: ["collab", "templates"], queryFn: () => agentsApi.collab.templates() });
  const [template, setTemplate] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<CollaborationRun | null>(null);
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: () => agentsApi.collab.run(prompt.trim() || template, template ? { template } : { policy: "review_required" }),
    onSuccess: (c) => { setResult(c); qc.invalidateQueries({ queryKey: ["agents", "approvals"] }); },
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {templates.data?.map((t) => (
              <button key={t.name} onClick={() => setTemplate(template === t.name ? "" : t.name)}
                className={cn("rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                  template === t.name ? "border-brand-400 bg-brand-50 text-brand-700" : "border-border text-foreground hover:bg-slate-50")}
                title={t.description}>
                {t.title}{t.human_required && " ⚑"}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input value={prompt} onChange={(e) => setPrompt(e.target.value)}
              placeholder={template ? `Run the "${template}" workflow…` : "Describe the task (review-required collaboration)…"} />
            <Button onClick={() => (prompt.trim() || template) && run.mutate()} isLoading={run.isPending}>Collaborate</Button>
          </div>
        </CardBody>
      </Card>
      {run.isPending && <Spinner />}
      {result && <CollabResult collab={result} />}
    </div>
  );
}

function CollabResult({ collab }: { collab: CollaborationRun }) {
  const qc = useQueryClient();
  const approve = useMutation({
    mutationFn: () => agentsApi.collab.approve(collab.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
  const [approved, setApproved] = useState(false);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="capitalize">{collab.workflow.replace(/_/g, " ")}</CardTitle>
          <div className="flex items-center gap-2">
            {collab.status === "pending_approval" && !approved && (
              <Button size="sm" onClick={() => approve.mutate(undefined, { onSuccess: () => setApproved(true) })} isLoading={approve.isPending}>
                <CheckCircle2 className="mr-1 h-4 w-4" /> Approve
              </Button>
            )}
            <ScoreBadge label="Quality" value={Math.round(collab.collaboration_quality)} />
          </div>
        </CardHeader>
        <CardBody className="space-y-3">
          {collab.status === "pending_approval" && !approved && (
            <p className="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">This workflow requires human approval before it is finalized.</p>
          )}
          <Markdown>{collab.answer}</Markdown>
          {collab.steps && (
            <div className="space-y-1.5">
              {collab.steps.map((s) => (
                <div key={s.order} className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
                  <span className="w-20 text-xs font-medium uppercase text-muted">{s.stage}</span>
                  <span className="flex-1 text-foreground">{s.agent.replace(/_agent$/, "") || "engine"}</span>
                  {s.approved != null && <span className={s.approved ? "text-success" : "text-danger"}>{s.approved ? "approved" : "rejected"}</span>}
                  {s.vote && <span className={s.vote === "yes" ? "text-success" : "text-danger"}>vote: {s.vote}</span>}
                  {s.confidence > 0 && <span className="text-xs text-muted">{Math.round(s.confidence)}%</span>}
                </div>
              ))}
            </div>
          )}
          <Explain items={[
            ["Agreement", collab.agreement_rate != null ? `${Math.round(collab.agreement_rate * 100)}%` : null],
            ["Review success", collab.review_success_rate != null ? `${Math.round(collab.review_success_rate * 100)}%` : null],
            ["Debates", collab.debate_count], ["Tool reuse", `${collab.tool_reuse_pct}%`],
            ["Knowledge v", collab.knowledge_version], ["Total", `${(collab.total_ms / 1000).toFixed(1)}s`],
          ]} />
        </CardBody>
      </Card>
      {collab.collaboration_graph && (
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><GitBranch className="h-4 w-4" /> Collaboration graph</CardTitle></CardHeader>
          <CardBody><AgentGraph graph={collab.collaboration_graph} /></CardBody></Card>
      )}
    </div>
  );
}

// ---- History ---------------------------------------------------------------

function RunHistory() {
  const agentRuns = useQuery({ queryKey: ["agents", "runs"], queryFn: () => agentsApi.runs() });
  const planRuns = useQuery({ queryKey: ["planner", "runs"], queryFn: () => agentsApi.planner.runs() });
  const collabRuns = useQuery({ queryKey: ["collab", "runs"], queryFn: () => agentsApi.collab.runs() });
  if (agentRuns.isLoading) return <SkeletonList rows={6} />;
  if (agentRuns.isError) return <ErrorState title="Couldn't load run history" onRetry={() => agentRuns.refetch()} />;

  const rows = [
    ...(agentRuns.data ?? []).map((r) => ({ kind: "agent", label: r.agent, request: r.request, status: r.status, quality: r.quality_score, at: r.created_at })),
    ...(planRuns.data ?? []).map((r) => ({ kind: "planner", label: r.execution_mode, request: r.request, status: r.status, quality: r.planner_quality, at: r.created_at })),
    ...(collabRuns.data ?? []).map((r) => ({ kind: "collab", label: r.workflow, request: r.request, status: r.status, quality: r.collaboration_quality, at: r.created_at })),
  ].sort((a, b) => +new Date(b.at) - +new Date(a.at)).slice(0, 40);

  if (rows.length === 0) return <EmptyState title="No runs yet" description="Run an agent, planner or collaboration to see history here." />;
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <Card key={i} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-sm">
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-muted">{r.kind}</span>
          <span className="font-medium text-foreground">{r.label.replace(/_/g, " ")}</span>
          <span className="flex-1 truncate text-muted">{r.request}</span>
          <span className={cn("text-xs", r.status === "succeeded" ? "text-success" : r.status === "pending_approval" ? "text-warning" : "text-danger")}>{r.status}</span>
          <span className="text-xs text-muted">Q{Math.round(r.quality)}</span>
          <span className="text-xs text-muted">{new Date(r.at).toLocaleString()}</span>
        </Card>
      ))}
    </div>
  );
}

// ---- Approvals -------------------------------------------------------------

function Approvals() {
  const qc = useQueryClient();
  const planRuns = useQuery({ queryKey: ["planner", "runs"], queryFn: () => agentsApi.planner.runs() });
  const collabRuns = useQuery({ queryKey: ["collab", "runs"], queryFn: () => agentsApi.collab.runs() });
  const approvePlan = useMutation({ mutationFn: (id: string) => agentsApi.planner.approve(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["planner"] }) });
  const approveCollab = useMutation({ mutationFn: (id: string) => agentsApi.collab.approve(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["collab"] }) });

  const pendingPlans = (planRuns.data ?? []).filter((r) => r.status === "pending_approval");
  const pendingCollabs = (collabRuns.data ?? []).filter((r) => r.status === "pending_approval");
  if (planRuns.isLoading) return <SkeletonList rows={3} />;
  if (pendingPlans.length + pendingCollabs.length === 0)
    return <EmptyState title="No pending approvals" description="Workflows requiring human sign-off will appear here." />;
  return (
    <div className="space-y-3">
      {pendingCollabs.map((c) => (
        <Card key={c.id} className="border-l-4 border-l-warning px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-foreground capitalize">{c.workflow.replace(/_/g, " ")}</p>
              <p className="text-xs text-muted">{c.request}</p>
            </div>
            <Button size="sm" onClick={() => approveCollab.mutate(c.id)} isLoading={approveCollab.isPending}>Approve</Button>
          </div>
        </Card>
      ))}
      {pendingPlans.map((p) => (
        <Card key={p.id} className="border-l-4 border-l-warning px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div><p className="text-sm font-semibold text-foreground">Planner workflow</p><p className="text-xs text-muted">{p.request}</p></div>
            <Button size="sm" onClick={() => approvePlan.mutate(p.id)} isLoading={approvePlan.isPending}>Approve</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ---- Tools -----------------------------------------------------------------

function Tools() {
  const agents = useQuery({ queryKey: ["agents", "list"], queryFn: () => agentsApi.list() });
  if (agents.isLoading) return <SkeletonGrid count={6} cols={2} />;
  const usedBy = new Map<string, string[]>();
  agents.data?.agents.forEach((a) => a.tools.forEach((t) => usedBy.set(t, [...(usedBy.get(t) ?? []), a.name])));
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {agents.data?.tools.map((t) => (
        <Card key={t.name}>
          <CardBody className="space-y-1">
            <div className="flex items-center gap-2"><Wrench className="h-4 w-4 text-muted" /><span className="font-medium text-foreground">{t.name}</span></div>
            <p className="text-xs text-muted">{t.description}</p>
            <p className="text-xs text-muted">Capability: {t.capability} · used by {usedBy.get(t.name)?.length ?? 0} agent(s)</p>
          </CardBody>
        </Card>
      ))}
    </div>
  );
}

// ---- Metrics ---------------------------------------------------------------

function Metrics() {
  const planner = useQuery({ queryKey: ["planner", "metrics"], queryFn: () => agentsApi.planner.metrics() });
  const collab = useQuery({ queryKey: ["collab", "metrics"], queryFn: () => agentsApi.collab.metrics() });
  const fmt = (v: unknown) => (v == null ? "—" : typeof v === "number" ? (v > 1000 ? `${(v / 1000).toFixed(1)}s` : v) : String(v));
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Network className="h-4 w-4" /> Planner metrics</CardTitle></CardHeader>
        <CardBody className="space-y-1.5 text-sm">
          {planner.data && Object.entries(planner.data).filter(([k]) => k !== "policies").map(([k, v]) => (
            <div key={k} className="flex justify-between"><span className="capitalize text-muted">{k.replace(/_/g, " ")}</span><span className="text-foreground">{fmt(v)}</span></div>
          ))}
        </CardBody>
      </Card>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><GitBranch className="h-4 w-4" /> Collaboration metrics</CardTitle></CardHeader>
        <CardBody className="space-y-1.5 text-sm">
          {collab.data && Object.entries(collab.data).filter(([k]) => k !== "templates").map(([k, v]) => (
            <div key={k} className="flex justify-between"><span className="capitalize text-muted">{k.replace(/_/g, " ")}</span><span className="text-foreground">{fmt(v)}</span></div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}
