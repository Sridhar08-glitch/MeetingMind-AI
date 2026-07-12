"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Download, FileBarChart, FileText, Loader2, Sparkles } from "lucide-react";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { EmptyState, SkeletonList } from "@/components/ui/Feedback";
import { meetingsApi } from "@/lib/api/meetings";
import { workspaceApi } from "@/lib/api/workspace";
import { formatDate } from "@/lib/utils";
import { toast } from "@/store/toast";
import type { TranscriptFormat } from "@/lib/types";

const FORMATS: TranscriptFormat[] = ["txt", "md", "srt", "vtt", "json"];
const REPORT_TYPES = [
  { value: "sprint", label: "Sprint report" },
  { value: "progress", label: "Progress report" },
  { value: "executive", label: "Executive report" },
  { value: "technical", label: "Technical report" },
  { value: "customer", label: "Customer report" },
];

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function ExportsPage() {
  const completed = useQuery({
    queryKey: ["exports-meetings"],
    queryFn: () => meetingsApi.list({ processing_status: "completed", page_size: 50 }),
  });
  const [reportType, setReportType] = useState("sprint");
  const [generating, setGenerating] = useState(false);

  const exportTranscript = async (id: string, title: string, fmt: TranscriptFormat) => {
    try {
      const blob = await meetingsApi.downloadTranscript(id, fmt);
      downloadBlob(blob, `${title.replace(/[^\w]+/g, "_")}.${fmt}`);
    } catch {
      toast.error("Export failed", "Could not download that transcript.");
    }
  };

  const generateReport = async () => {
    setGenerating(true);
    try {
      const { content, title } = await workspaceApi.generateReport(reportType);
      downloadBlob(new Blob([content], { type: "text/markdown" }), `${title.replace(/[^\w]+/g, "_")}.md`);
      toast.success("Report generated", title);
    } catch {
      toast.error("Generation failed", "Could not generate that report.");
    } finally {
      setGenerating(false);
    }
  };

  const meetings = completed.data?.results ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Export Center</h1>
        <p className="mt-1 text-sm text-muted">Download transcripts, generate reports, and export executive briefs.</p>
      </div>

      {/* Transcripts */}
      <Card>
        <CardHeader className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-brand-500" />
          <CardTitle>Transcripts</CardTitle>
        </CardHeader>
        <CardBody>
          {completed.isLoading ? (
            <SkeletonList rows={4} label="Loading meetings" />
          ) : meetings.length === 0 ? (
            <EmptyState
              title="No transcripts yet"
              description="Once a meeting finishes processing, export its transcript here in any format."
            />
          ) : (
            <ul className="divide-y divide-border">
              {meetings.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <span className="min-w-0">
                    <Link href={`/meetings/${m.id}`} className="text-sm font-medium text-foreground hover:text-brand-600">
                      {m.title}
                    </Link>
                    <span className="ml-2 text-xs text-muted">{formatDate(m.created_at)}</span>
                  </span>
                  <span className="flex overflow-hidden rounded-lg border border-border">
                    {FORMATS.map((f) => (
                      <button
                        key={f}
                        onClick={() => exportTranscript(m.id, m.title, f)}
                        className="border-r border-border px-2.5 py-1 text-xs font-medium uppercase text-muted last:border-r-0 hover:bg-slate-50 hover:text-foreground"
                      >
                        {f}
                      </button>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {/* Reports */}
      <Card>
        <CardHeader className="flex items-center gap-2">
          <FileBarChart className="h-4 w-4 text-brand-500" />
          <CardTitle>Reports</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-muted">Generate an AI report across your workspace and download it as Markdown.</p>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            >
              {REPORT_TYPES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <Button onClick={generateReport} isLoading={generating}>
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Generate &amp; download
            </Button>
          </div>
        </CardBody>
      </Card>

      {/* Executive brief */}
      <Card>
        <CardHeader className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-500" />
          <CardTitle>Executive brief</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">
            Generate daily, weekly or monthly executive briefs from the Executive dashboard.
          </p>
          <Link href="/executive?view=brief">
            <Button variant="outline">
              <FileText className="h-4 w-4" /> Open Brief
            </Button>
          </Link>
        </CardBody>
      </Card>
    </div>
  );
}
