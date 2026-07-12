"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  BarChart3, Database, Gauge, History, Import, Info, Play, Plus, Sliders, Sprout, Trash2,
} from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Spinner, EmptyState, SkeletonGrid, SkeletonList, ErrorState } from "@/components/ui/Feedback";
import {
  benchmarksApi,
  type BenchmarkConfig,
  type BenchmarkDataset,
  type BenchmarkRecording,
  type BenchmarkResult,
  type BenchmarkRun,
  type BenchmarkRunDetail,
  type ConfigPayload,
  type GroundTruthType,
  type OverlapHandling,
  type RecordingFormat,
} from "@/lib/api/benchmarks";
import { meetingsApi } from "@/lib/api/meetings";
import { toast } from "@/store/toast";
import { getApiErrorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Tab = "datasets" | "run" | "configs" | "history";

const TABS: { id: Tab; label: string; icon: typeof Gauge }[] = [
  { id: "datasets", label: "Datasets", icon: Database },
  { id: "run", label: "Run", icon: Play },
  { id: "configs", label: "Configs", icon: Sliders },
  { id: "history", label: "History", icon: History },
];

const FORMATS: RecordingFormat[] = [
  "podcast", "panel", "interview", "roundtable", "webinar", "meeting", "other",
];

const GROUND_TRUTH_FOOTNOTE =
  "Public/podcast ground truth is approximate unless manually verified.";

export default function BenchmarkCenterPage() {
  const params = useSearchParams();
  const initial = (params.get("tab") as Tab) || "datasets";
  const [tab, setTab] = useState<Tab>(TABS.some((t) => t.id === initial) ? initial : "datasets");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
          <Gauge className="h-6 w-6 text-brand-500" /> Benchmark Center
        </h1>
        <p className="mt-1 text-sm text-muted">
          A local speaker-diarization evaluation framework — build ground-truth datasets, tune diarization
          configs, run benchmarks, and compare results honestly.
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

      {tab === "datasets" && <DatasetsTab />}
      {tab === "run" && <RunTab />}
      {tab === "configs" && <ConfigsTab />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}

// ---- Shared honest-reporting helpers ---------------------------------------

/** Persistent banner explaining ground-truth confidence tiers. */
function GroundTruthBanner() {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-info/30 bg-info-bg/50 px-3 py-2.5 text-sm text-info" role="note">
      <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>
        <span className="font-medium">Honest reporting:</span> public / podcast datasets have{" "}
        <span className="font-medium">approximate</span> ground truth and are labeled as such. Your own
        recordings with known participants are the <span className="font-medium">highest-confidence</span>{" "}
        ground truth. Expected speaker counts that aren&apos;t manually verified are shown as
        &ldquo;~N (approx)&rdquo;.
      </span>
    </div>
  );
}

function GroundTruthBadge({ type }: { type: GroundTruthType }) {
  const map: Record<GroundTruthType, { label: string; cls: string }> = {
    user_verified: { label: "Verified", cls: "bg-success-bg text-success" },
    public_approximate: { label: "Approximate", cls: "bg-warning/15 text-warning" },
    unknown: { label: "Unknown", cls: "bg-slate-100 text-muted" },
  };
  const { label, cls } = map[type];
  return <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", cls)}>{label}</span>;
}

/** Renders an expected speaker count without ever passing off an approximate count as exact. */
function ExpectedCount({ value, groundTruth }: { value: number | null; groundTruth: GroundTruthType }) {
  if (value == null) return <span className="text-muted">—</span>;
  if (groundTruth === "user_verified") return <span>{value}</span>;
  return (
    <span className="text-warning" title={GROUND_TRUTH_FOOTNOTE}>
      ~{value} (approx)
    </span>
  );
}

function KindBadge({ kind }: { kind: BenchmarkDataset["kind"] }) {
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
      kind === "public" ? "bg-warning/15 text-warning" : "bg-brand-50 text-brand-700")}>
      {kind}
    </span>
  );
}

function FormatBadge({ format }: { format: RecordingFormat }) {
  return <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-foreground">{format}</span>;
}

function StatusBadge({ status }: { status: BenchmarkRecording["status"] }) {
  const cls =
    status === "ready" ? "text-success"
      : status === "failed" ? "text-danger"
        : status === "importing" || status === "processing" ? "text-brand-600"
          : "text-muted";
  return <span className={cn("text-xs", cls)}>{status}</span>;
}

const fmtNum = (v: number | null | undefined, digits = 2) =>
  v == null ? "—" : Number.isInteger(v) ? String(v) : v.toFixed(digits);
// speaker_count_accuracy arrives already as a percentage (0-100), not a 0-1 fraction.
const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
const fmtMs = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}ms`);

// ---- Datasets tab ----------------------------------------------------------

function DatasetsTab() {
  const params = useSearchParams();
  const qc = useQueryClient();
  const datasets = useQuery({ queryKey: ["benchmarks", "datasets"], queryFn: () => benchmarksApi.datasets.list() });
  const [selected, setSelected] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const seed = useMutation({
    mutationFn: (limit?: number) => benchmarksApi.datasets.seedPublic(limit),
    onSuccess: (d) => {
      toast.success("Public suite seeded", `${d.created} dataset(s) added.`);
      qc.invalidateQueries({ queryKey: ["benchmarks", "datasets"] });
    },
    onError: (e) => toast.error("Seed failed", getApiErrorMessage(e)),
  });

  // Deep-link: /benchmarks?tab=datasets&seed=1 auto-triggers a seed once.
  const wantSeed = params.get("seed") === "1";
  const [seedFired, setSeedFired] = useState(false);
  if (wantSeed && !seedFired && !seed.isPending) {
    setSeedFired(true);
    seed.mutate(undefined);
  }

  if (datasets.isLoading) return <SkeletonGrid count={6} />;
  if (datasets.isError) return <ErrorState title="Couldn't load datasets" onRetry={() => datasets.refetch()} />;

  const selectedDataset = datasets.data?.find((d) => d.id === selected) ?? null;

  return (
    <div className="space-y-6">
      <GroundTruthBanner />

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => seed.mutate(undefined)} isLoading={seed.isPending} variant="outline">
          <Sprout className="mr-1 h-4 w-4" /> Seed Public Suite
        </Button>
        <Button onClick={() => setShowNew((v) => !v)}>
          <Plus className="mr-1 h-4 w-4" /> New dataset
        </Button>
      </div>

      {showNew && <NewDatasetForm onDone={() => setShowNew(false)} />}

      {datasets.data && datasets.data.length === 0 ? (
        <EmptyState title="No datasets yet"
          description="Seed the public suite or create your own dataset to start benchmarking." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {datasets.data?.map((d) => (
            <Card key={d.id} className={cn("cursor-pointer transition-colors",
              selected === d.id ? "ring-2 ring-brand-400" : "hover:bg-slate-50")}
              onClick={() => setSelected(selected === d.id ? null : d.id)}>
              <CardBody className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-foreground">{d.name}</span>
                  <KindBadge kind={d.kind} />
                </div>
                {d.description && <p className="text-xs text-muted">{d.description}</p>}
                <p className="text-xs text-muted">{d.recording_count} recording(s)</p>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {selectedDataset && <DatasetRecordings dataset={selectedDataset} />}
    </div>
  );
}

function NewDatasetForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BenchmarkDataset["kind"]>("user");
  const [description, setDescription] = useState("");
  const create = useMutation({
    mutationFn: () => benchmarksApi.datasets.create({ name: name.trim(), kind, description: description.trim() || undefined }),
    onSuccess: () => {
      toast.success("Dataset created");
      qc.invalidateQueries({ queryKey: ["benchmarks", "datasets"] });
      onDone();
    },
    onError: (e) => toast.error("Couldn't create dataset", getApiErrorMessage(e)),
  });
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Dataset name" />
          <select value={kind} onChange={(e) => setKind(e.target.value as BenchmarkDataset["kind"])}
            className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground">
            <option value="user">user</option>
            <option value="public">public</option>
          </select>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" />
        </div>
        <div className="flex gap-2">
          <Button onClick={() => name.trim() && create.mutate()} isLoading={create.isPending}>Create</Button>
          <Button variant="ghost" onClick={onDone}>Cancel</Button>
        </div>
      </CardBody>
    </Card>
  );
}

function DatasetRecordings({ dataset }: { dataset: BenchmarkDataset }) {
  const qc = useQueryClient();
  const recordings = useQuery({
    queryKey: ["benchmarks", "recordings", dataset.id],
    queryFn: () => benchmarksApi.recordings.list({ dataset: dataset.id }),
    // Poll while anything is importing/processing so status updates land automatically.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "importing" || r.status === "processing") ? 4000 : false,
  });
  const [showAdd, setShowAdd] = useState(false);
  const [showFromMeeting, setShowFromMeeting] = useState(false);

  const importRec = useMutation({
    mutationFn: (id: string) => benchmarksApi.recordings.import(id),
    onSuccess: () => {
      toast.success("Import started");
      qc.invalidateQueries({ queryKey: ["benchmarks", "recordings", dataset.id] });
    },
    onError: (e) => toast.error("Import failed", getApiErrorMessage(e)),
  });

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <Database className="h-4 w-4" /> {dataset.name} <KindBadge kind={dataset.kind} />
        </CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => { setShowAdd((v) => !v); setShowFromMeeting(false); }}>
            <Plus className="mr-1 h-4 w-4" /> Add recording
          </Button>
          <Button size="sm" variant="outline" onClick={() => { setShowFromMeeting((v) => !v); setShowAdd(false); }}>
            <Import className="mr-1 h-4 w-4" /> From my meeting
          </Button>
        </div>
      </CardHeader>
      <CardBody className="space-y-4">
        {showAdd && <AddRecordingForm datasetId={dataset.id} onDone={() => setShowAdd(false)} />}
        {showFromMeeting && <FromMeetingForm datasetId={dataset.id} onDone={() => setShowFromMeeting(false)} />}

        {recordings.isLoading ? (
          <SkeletonList rows={4} />
        ) : recordings.isError ? (
          <ErrorState title="Couldn't load recordings" onRetry={() => recordings.refetch()} />
        ) : recordings.data && recordings.data.length === 0 ? (
          <EmptyState title="No recordings" description="Add a recording manually or import one from your meetings." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-muted">
                <tr className="border-b border-border">
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Format</th>
                  <th className="py-2 pr-3 font-medium">Lang</th>
                  <th className="py-2 pr-3 font-medium">Ground truth</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Expected</th>
                  <th className="py-2 pr-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {recordings.data?.map((r) => (
                  <tr key={r.id} className="border-b border-border/60">
                    <td className="py-2 pr-3 font-medium text-foreground">{r.name}</td>
                    <td className="py-2 pr-3"><FormatBadge format={r.format} /></td>
                    <td className="py-2 pr-3 text-muted">{r.language || "—"}</td>
                    <td className="py-2 pr-3"><GroundTruthBadge type={r.ground_truth_type} /></td>
                    <td className="py-2 pr-3"><StatusBadge status={r.status} /></td>
                    <td className="py-2 pr-3">
                      <ExpectedCount value={r.expected_speaker_count} groundTruth={r.ground_truth_type} />
                    </td>
                    <td className="py-2 pr-3">
                      {dataset.kind === "public" && (r.status === "pending" || r.status === "failed") && (
                        <Button size="sm" variant="outline"
                          onClick={() => importRec.mutate(r.id)}
                          isLoading={importRec.isPending && importRec.variables === r.id}>
                          <Import className="mr-1 h-3.5 w-3.5" /> Import
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted">{GROUND_TRUTH_FOOTNOTE}</p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function AddRecordingForm({ datasetId, onDone }: { datasetId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [format, setFormat] = useState<RecordingFormat>("podcast");
  const [language, setLanguage] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [expected, setExpected] = useState("");
  const [participants, setParticipants] = useState("");
  const [meetingType, setMeetingType] = useState("");
  const [notes, setNotes] = useState("");

  const create = useMutation({
    mutationFn: () => benchmarksApi.recordings.create({
      dataset: datasetId,
      name: name.trim(),
      format,
      language: language.trim() || undefined,
      source_url: sourceUrl.trim() || undefined,
      expected_speaker_count: expected.trim() ? Number(expected) : null,
      known_participants: participants.split(",").map((s) => s.trim()).filter(Boolean),
      meeting_type: meetingType.trim() || undefined,
      notes: notes.trim() || undefined,
    }),
    onSuccess: () => {
      toast.success("Recording added");
      qc.invalidateQueries({ queryKey: ["benchmarks", "recordings", datasetId] });
      qc.invalidateQueries({ queryKey: ["benchmarks", "datasets"] });
      onDone();
    },
    onError: (e) => toast.error("Couldn't add recording", getApiErrorMessage(e)),
  });

  return (
    <div className="space-y-3 rounded-lg border border-border bg-slate-50/50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">Add recording</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
        <select value={format} onChange={(e) => setFormat(e.target.value as RecordingFormat)}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground">
          {FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <Input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="Language (e.g. en)" />
        <Input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="Source URL (optional)" />
        <Input type="number" value={expected} onChange={(e) => setExpected(e.target.value)} placeholder="Expected speaker count" />
        <Input value={meetingType} onChange={(e) => setMeetingType(e.target.value)} placeholder="Meeting type (optional)" />
        <Input value={participants} onChange={(e) => setParticipants(e.target.value)} placeholder="Known participants (comma-separated)" />
        <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)" />
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => name.trim() && create.mutate()} isLoading={create.isPending}>Add</Button>
        <Button size="sm" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  );
}

function FromMeetingForm({ datasetId, onDone }: { datasetId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const meetings = useQuery({
    queryKey: ["benchmarks", "meetings-picker"],
    queryFn: () => meetingsApi.list({ page_size: 100, ordering: "-created_at" }),
  });
  const [meeting, setMeeting] = useState("");
  const [name, setName] = useState("");
  const [expected, setExpected] = useState("");
  const [participants, setParticipants] = useState("");
  const [meetingType, setMeetingType] = useState("");

  const create = useMutation({
    mutationFn: () => benchmarksApi.recordings.fromMeeting({
      meeting,
      dataset: datasetId,
      name: name.trim() || undefined,
      expected_speaker_count: expected.trim() ? Number(expected) : null,
      known_participants: participants.split(",").map((s) => s.trim()).filter(Boolean),
      meeting_type: meetingType.trim() || undefined,
    }),
    onSuccess: () => {
      toast.success("Recording created from meeting", "User recordings with known participants are the highest-confidence ground truth.");
      qc.invalidateQueries({ queryKey: ["benchmarks", "recordings", datasetId] });
      qc.invalidateQueries({ queryKey: ["benchmarks", "datasets"] });
      onDone();
    },
    onError: (e) => toast.error("Couldn't create from meeting", getApiErrorMessage(e)),
  });

  return (
    <div className="space-y-3 rounded-lg border border-border bg-slate-50/50 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">From my meeting</p>
      {meetings.isLoading ? (
        <Spinner />
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          <select value={meeting} onChange={(e) => setMeeting(e.target.value)}
            className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground">
            <option value="">Select a meeting…</option>
            {meetings.data?.results.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Recording name (optional)" />
          <Input type="number" value={expected} onChange={(e) => setExpected(e.target.value)} placeholder="Expected speaker count" />
          <Input value={meetingType} onChange={(e) => setMeetingType(e.target.value)} placeholder="Meeting type (optional)" />
          <Input value={participants} onChange={(e) => setParticipants(e.target.value)}
            placeholder="Known participants (comma-separated)" className="sm:col-span-2" />
        </div>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => meeting && create.mutate()} isLoading={create.isPending} disabled={!meeting}>Create</Button>
        <Button size="sm" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  );
}

// ---- Run tab ---------------------------------------------------------------

function RunTab() {
  const qc = useQueryClient();
  const datasets = useQuery({ queryKey: ["benchmarks", "datasets"], queryFn: () => benchmarksApi.datasets.list() });
  const configs = useQuery({ queryKey: ["benchmarks", "configs"], queryFn: () => benchmarksApi.configs.list() });
  const [dataset, setDataset] = useState("");
  const [selectedConfigs, setSelectedConfigs] = useState<string[]>([]);
  const [label, setLabel] = useState("");
  const [result, setResult] = useState<BenchmarkRunDetail | null>(null);

  const run = useMutation({
    mutationFn: () => benchmarksApi.runs.run({
      dataset,
      config_ids: selectedConfigs.length > 0 ? selectedConfigs : undefined,
      label: label.trim() || undefined,
    }),
    onSuccess: (r) => {
      setResult(r);
      toast.success("Benchmark complete");
      qc.invalidateQueries({ queryKey: ["benchmarks", "runs"] });
    },
    onError: (e) => toast.error("Benchmark failed", getApiErrorMessage(e)),
  });

  const toggleConfig = (id: string) =>
    setSelectedConfigs((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  return (
    <div className="space-y-4">
      <GroundTruthBanner />
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <select value={dataset} onChange={(e) => setDataset(e.target.value)}
              className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground">
              <option value="">Select a dataset…</option>
              {datasets.data?.map((d) => (
                <option key={d.id} value={d.id}>{d.name} ({d.recording_count})</option>
              ))}
            </select>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Run label (optional)" className="max-w-xs" />
          </div>

          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              Configs {selectedConfigs.length === 0 && <span className="normal-case text-muted">(none selected → uses default)</span>}
            </p>
            <div className="flex flex-wrap gap-2">
              {configs.data?.map((c) => (
                <label key={c.id}
                  className={cn("flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs",
                    selectedConfigs.includes(c.id) ? "border-brand-400 bg-brand-50 text-brand-700" : "border-border text-foreground hover:bg-slate-50")}>
                  <input type="checkbox" checked={selectedConfigs.includes(c.id)} onChange={() => toggleConfig(c.id)} />
                  {c.name}{c.is_default && " (default)"}
                </label>
              ))}
              {configs.data && configs.data.length === 0 && (
                <span className="text-xs text-muted">No saved configs — the default engine config will be used.</span>
              )}
            </div>
          </div>

          <Button onClick={() => dataset && run.mutate()} isLoading={run.isPending} disabled={!dataset}>
            <Play className="mr-1 h-4 w-4" /> Run benchmark
          </Button>
        </CardBody>
      </Card>

      {run.isPending && <Spinner />}
      {result && <RunResultView run={result} />}
    </div>
  );
}

/** Provenance strip + run-level aggregates shared by Run and History detail. */
function RunAggregates({ run }: { run: BenchmarkRun }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Aggregate label="Speaker-count accuracy" value={fmtPct(run.speaker_count_accuracy)} tone="green" />
        <Aggregate label="Avg speaker-count error" value={fmtNum(run.avg_speaker_count_error)} />
        <Aggregate label="Total over-merged" value={String(run.total_over_merged)} />
        <Aggregate label="Total over-split" value={String(run.total_over_split)} />
        <Aggregate label="Avg embedding conf" value={fmtNum(run.avg_embedding_confidence)} />
        <Aggregate label="Avg processing" value={fmtMs(run.avg_processing_ms)} />
        <Aggregate label="Recordings scored" value={`${run.recordings_scored}/${run.recordings_total}`} />
        <Aggregate label="Configs" value={String(run.configs_count)} />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border pt-3 text-xs text-muted">
        <span><span className="text-foreground">Engine:</span> {run.engine_version || "n/a"}</span>
        <span><span className="text-foreground">Diarization:</span> {run.diarization_engine || "n/a"}</span>
        <span><span className="text-foreground">STT:</span> {run.stt_provider || "n/a"}</span>
        <span><span className="text-foreground">Embedding:</span> {run.embedding_model || "n/a"}</span>
        <span><span className="text-foreground">Commit:</span> {run.git_commit || "n/a"}</span>
      </div>
    </>
  );
}

function Aggregate({ label, value, tone }: { label: string; value: string; tone?: "green" }) {
  return (
    <div className="rounded-lg border border-border px-3 py-2 text-center">
      <p className={cn("text-lg font-bold", tone === "green" ? "text-success" : "text-brand-600")}>{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted">{label}</p>
    </div>
  );
}

/** Full results table — every metric column. */
function ResultsTable({ results }: { results: BenchmarkResult[] }) {
  if (results.length === 0)
    return <EmptyState title="No results" description="This run produced no scored results." />;
  const cols: { key: string; label: string; render: (r: BenchmarkResult) => React.ReactNode }[] = [
    { key: "recording", label: "Recording", render: (r) => <span className="font-medium text-foreground">{r.recording_name}</span> },
    { key: "config", label: "Config", render: (r) => r.config_label || "—" },
    { key: "gt", label: "Ground truth", render: (r) => <GroundTruthBadge type={r.ground_truth_type} /> },
    { key: "expected", label: "Expected", render: (r) => <ExpectedCount value={r.expected_speaker_count} groundTruth={r.ground_truth_type} /> },
    { key: "detected", label: "Detected", render: (r) => fmtNum(r.detected_speaker_count, 0) },
    { key: "correct", label: "Correctly clustered", render: (r) => fmtNum(r.correctly_clustered, 0) },
    { key: "over_merged", label: "Over-merged", render: (r) => String(r.over_merged) },
    { key: "over_split", label: "Over-split", render: (r) => String(r.over_split) },
    { key: "emb_conf", label: "Avg emb conf", render: (r) => fmtNum(r.avg_embedding_confidence) },
    { key: "speech", label: "Avg speech dur", render: (r) => fmtNum(r.avg_speech_duration) },
    { key: "proc", label: "Processing", render: (r) => fmtMs(r.processing_time_ms) },
    { key: "der", label: "DER", render: (r) => fmtNum(r.der) },
    { key: "purity", label: "Cluster purity", render: (r) => fmtNum(r.cluster_purity) },
    { key: "diar", label: "Diarization", render: (r) => r.diarization_engine || "n/a" },
    { key: "stt", label: "STT", render: (r) => r.stt_provider || "n/a" },
    { key: "emb", label: "Embedding", render: (r) => r.embedding_model || "n/a" },
    { key: "kv", label: "Knowledge v", render: (r) => fmtNum(r.knowledge_version, 0) },
    { key: "ok", label: "OK", render: (r) => <span className={r.ok ? "text-success" : "text-danger"}>{r.ok ? "yes" : "no"}</span> },
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-muted">
          <tr className="border-b border-border">
            {cols.map((c) => <th key={c.key} className="whitespace-nowrap px-2 py-2 font-medium">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.id} className="border-b border-border/60">
              {cols.map((c) => <td key={c.key} className="whitespace-nowrap px-2 py-2 text-muted">{c.render(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted">{GROUND_TRUTH_FOOTNOTE}</p>
    </div>
  );
}

function RunResultView({ run }: { run: BenchmarkRunDetail }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Gauge className="h-4 w-4" /> Run results {run.label && `· ${run.label}`}</CardTitle></CardHeader>
        <CardBody className="space-y-4">
          <RunAggregates run={run} />
        </CardBody>
      </Card>
      <Card>
        <CardHeader><CardTitle>Per-recording results</CardTitle></CardHeader>
        <CardBody><ResultsTable results={run.results} /></CardBody>
      </Card>
    </div>
  );
}

// ---- Configs tab -----------------------------------------------------------

const OVERLAP_OPTIONS: OverlapHandling[] = ["longest", "ignore", "split"];

const DEFAULT_CONFIG: ConfigPayload = {
  name: "",
  diarization_provider: "pyannote",
  cluster_threshold: 0.7,
  merge_threshold: null,
  min_speech_duration: 0.5,
  min_segment_length: 0.5,
  max_speakers: 10,
  overlap_handling: "longest",
  is_default: false,
};

function ConfigsTab() {
  const qc = useQueryClient();
  const configs = useQuery({ queryKey: ["benchmarks", "configs"], queryFn: () => benchmarksApi.configs.list() });
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => benchmarksApi.configs.remove(id),
    onSuccess: () => {
      toast.success("Config deleted");
      qc.invalidateQueries({ queryKey: ["benchmarks", "configs"] });
    },
    onError: (e) => toast.error("Couldn't delete config", getApiErrorMessage(e)),
  });

  if (configs.isLoading) return <SkeletonList rows={4} />;
  if (configs.isError) return <ErrorState title="Couldn't load configs" onRetry={() => configs.refetch()} />;

  return (
    <div className="space-y-4">
      <div>
        <Button onClick={() => { setCreating(true); setEditing(null); }}>
          <Plus className="mr-1 h-4 w-4" /> New config
        </Button>
      </div>

      {creating && <ConfigForm initial={DEFAULT_CONFIG} onDone={() => setCreating(false)} />}

      {configs.data && configs.data.length === 0 && !creating ? (
        <EmptyState title="No configs" description="Create a tuning config to compare diarization settings." />
      ) : (
        <div className="space-y-2">
          {configs.data?.map((c) => (
            editing === c.id ? (
              <ConfigForm key={c.id} id={c.id} initial={configToPayload(c)} onDone={() => setEditing(null)} />
            ) : (
              <Card key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
                <span className="font-medium text-foreground">{c.name}</span>
                {c.is_default && <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] text-brand-700">default</span>}
                <span className="text-xs text-muted">provider {c.diarization_provider}</span>
                <span className="text-xs text-muted">cluster {c.cluster_threshold}</span>
                <span className="text-xs text-muted">merge {c.merge_threshold ?? "—"}</span>
                <span className="text-xs text-muted">min-speech {c.min_speech_duration}</span>
                <span className="text-xs text-muted">min-seg {c.min_segment_length}</span>
                <span className="text-xs text-muted">max {c.max_speakers}</span>
                <span className="text-xs text-muted">overlap {c.overlap_handling}</span>
                <div className="ml-auto flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(c.id); setCreating(false); }}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => remove.mutate(c.id)} isLoading={remove.isPending && remove.variables === c.id}>
                    <Trash2 className="h-4 w-4 text-danger" />
                  </Button>
                </div>
              </Card>
            )
          ))}
        </div>
      )}
    </div>
  );
}

function configToPayload(c: BenchmarkConfig): ConfigPayload {
  return {
    name: c.name,
    diarization_provider: c.diarization_provider,
    cluster_threshold: c.cluster_threshold,
    merge_threshold: c.merge_threshold,
    min_speech_duration: c.min_speech_duration,
    min_segment_length: c.min_segment_length,
    max_speakers: c.max_speakers,
    overlap_handling: c.overlap_handling,
    is_default: c.is_default,
  };
}

function ConfigForm({ id, initial, onDone }: { id?: string; initial: ConfigPayload; onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ConfigPayload>(initial);
  const set = <K extends keyof ConfigPayload>(k: K, v: ConfigPayload[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = useMutation({
    mutationFn: () => (id ? benchmarksApi.configs.update(id, form) : benchmarksApi.configs.create(form)),
    onSuccess: () => {
      toast.success(id ? "Config updated" : "Config created");
      qc.invalidateQueries({ queryKey: ["benchmarks", "configs"] });
      onDone();
    },
    onError: (e) => toast.error("Couldn't save config", getApiErrorMessage(e)),
  });

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Config name" />
          </Field>
          <Field label="Diarization provider">
            <Input value={form.diarization_provider} onChange={(e) => set("diarization_provider", e.target.value)} />
          </Field>
          <SliderField label="Cluster threshold" value={form.cluster_threshold} min={0} max={1} step={0.01}
            onChange={(v) => set("cluster_threshold", v)} />
          <SliderField label="Merge threshold" value={form.merge_threshold ?? 0} min={0} max={1} step={0.01}
            onChange={(v) => set("merge_threshold", v)} />
          <SliderField label="Min speech duration (s)" value={form.min_speech_duration} min={0} max={5} step={0.1}
            onChange={(v) => set("min_speech_duration", v)} />
          <SliderField label="Min segment length (s)" value={form.min_segment_length} min={0} max={5} step={0.1}
            onChange={(v) => set("min_segment_length", v)} />
          <Field label="Max speakers">
            <Input type="number" value={form.max_speakers} onChange={(e) => set("max_speakers", Number(e.target.value))} />
          </Field>
          <Field label="Overlap handling">
            <select value={form.overlap_handling} onChange={(e) => set("overlap_handling", e.target.value as OverlapHandling)}
              className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground">
              {OVERLAP_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </Field>
        </div>
        <label className="flex items-center gap-1.5 text-sm text-muted">
          <input type="checkbox" checked={form.is_default} onChange={(e) => set("is_default", e.target.checked)} /> Default config
        </label>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => form.name.trim() && save.mutate()} isLoading={save.isPending}>Save</Button>
          <Button size="sm" variant="ghost" onClick={onDone}>Cancel</Button>
        </div>
      </CardBody>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}

function SliderField({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center justify-between text-xs font-medium text-muted">
        {label} <span className="text-foreground">{value}</span>
      </span>
      <div className="flex items-center gap-2">
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))} className="flex-1 accent-brand-600" />
        <Input type="number" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))} className="w-20" />
      </div>
    </label>
  );
}

// ---- History tab -----------------------------------------------------------

function HistoryTab() {
  const runs = useQuery({ queryKey: ["benchmarks", "runs"], queryFn: () => benchmarksApi.runs.list() });
  const datasets = useQuery({ queryKey: ["benchmarks", "datasets"], queryFn: () => benchmarksApi.datasets.list() });
  const [selected, setSelected] = useState<string | null>(null);

  if (runs.isLoading) return <SkeletonList rows={6} />;
  if (runs.isError) return <ErrorState title="Couldn't load run history" onRetry={() => runs.refetch()} />;
  if (runs.data && runs.data.length === 0)
    return <EmptyState title="No runs yet" description="Run a benchmark to see history here." />;

  const datasetName = (id: string) => datasets.data?.find((d) => d.id === id)?.name ?? id;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {runs.data?.map((r) => (
          <Card key={r.id} className="cursor-pointer px-4 py-2.5 text-sm hover:bg-slate-50"
            onClick={() => setSelected(selected === r.id ? null : r.id)}>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="text-xs text-muted">{new Date(r.created_at).toLocaleString()}</span>
              <span className="font-medium text-foreground">{r.label || "(unlabeled run)"}</span>
              <span className="flex-1 truncate text-muted">{datasetName(r.dataset)}</span>
              <span className="text-xs text-muted">acc {fmtPct(r.speaker_count_accuracy)}</span>
              <span className={cn("text-xs", r.status === "completed" || r.status === "succeeded" ? "text-success" : r.status === "failed" ? "text-danger" : "text-warning")}>{r.status}</span>
            </div>
          </Card>
        ))}
      </div>
      {selected && <RunDetail id={selected} />}
    </div>
  );
}

function RunDetail({ id }: { id: string }) {
  const detail = useQuery({ queryKey: ["benchmarks", "run", id], queryFn: () => benchmarksApi.runs.detail(id) });
  const [showCompare, setShowCompare] = useState(false);

  if (detail.isLoading) return <Spinner />;
  if (detail.isError) return <ErrorState title="Couldn't load run" onRetry={() => detail.refetch()} />;
  const run = detail.data;
  if (!run) return null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2"><Gauge className="h-4 w-4" /> {run.label || "Run"} details</CardTitle>
          <Button size="sm" variant="outline" onClick={() => setShowCompare((v) => !v)}>
            <BarChart3 className="mr-1 h-4 w-4" /> Compare configs
          </Button>
        </CardHeader>
        <CardBody className="space-y-4"><RunAggregates run={run} /></CardBody>
      </Card>

      {showCompare && <CompareView runId={id} />}

      <Card>
        <CardHeader><CardTitle>Per-recording results</CardTitle></CardHeader>
        <CardBody><ResultsTable results={run.results} /></CardBody>
      </Card>
    </div>
  );
}

function CompareView({ runId }: { runId: string }) {
  const compare = useQuery({ queryKey: ["benchmarks", "compare", runId], queryFn: () => benchmarksApi.runs.compare(runId) });
  const rows = useMemo(
    () => [...(compare.data?.comparison ?? [])].sort((a, b) => (b.speaker_count_accuracy ?? 0) - (a.speaker_count_accuracy ?? 0)),
    [compare.data],
  );
  if (compare.isLoading) return <Spinner />;
  if (compare.isError) return <ErrorState title="Couldn't load comparison" onRetry={() => compare.refetch()} />;
  if (rows.length === 0)
    return <EmptyState title="Nothing to compare" description="This run has a single config." />;

  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Config comparison (best accuracy first)</CardTitle></CardHeader>
      <CardBody>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-muted">
              <tr className="border-b border-border">
                <th className="px-2 py-2 font-medium">Config</th>
                <th className="px-2 py-2 font-medium">Recordings</th>
                <th className="px-2 py-2 font-medium">Speaker-count accuracy</th>
                <th className="px-2 py-2 font-medium">Over-merged</th>
                <th className="px-2 py-2 font-medium">Over-split</th>
                <th className="px-2 py-2 font-medium">Avg emb conf</th>
                <th className="px-2 py-2 font-medium">Avg processing</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.config_label + i} className="border-b border-border/60">
                  <td className="px-2 py-2 font-medium text-foreground">{r.config_label}{i === 0 && <span className="ml-1.5 rounded bg-success-bg px-1.5 py-0.5 text-[10px] text-success">best</span>}</td>
                  <td className="px-2 py-2 text-muted">{r.recordings}</td>
                  <td className="px-2 py-2 text-muted">{fmtPct(r.speaker_count_accuracy)}</td>
                  <td className="px-2 py-2 text-muted">{r.total_over_merged}</td>
                  <td className="px-2 py-2 text-muted">{r.total_over_split}</td>
                  <td className="px-2 py-2 text-muted">{fmtNum(r.avg_embedding_confidence)}</td>
                  <td className="px-2 py-2 text-muted">{fmtMs(r.avg_processing_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  );
}
