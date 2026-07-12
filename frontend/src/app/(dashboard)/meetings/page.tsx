"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Archive, ChevronLeft, ChevronRight, Download, ExternalLink, Radio, Search, Star, Trash2, UploadCloud } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ProcessingBadge } from "@/components/ui/Badge";
import { EmptyState, SkeletonList, ErrorState } from "@/components/ui/Feedback";
import { ContextMenu, type ContextMenuState } from "@/components/ui/ContextMenu";
import { ImportsQueue } from "@/components/meetings/ImportsQueue";
import { getApiErrorMessage } from "@/lib/api/client";
import { meetingsApi } from "@/lib/api/meetings";
import { cn, formatBytes, formatDate, formatDuration } from "@/lib/utils";
import type { Meeting, ProcessingStatus } from "@/lib/types";
import { toast } from "@/store/toast";
import { useDeleteMeeting, useMeetings, useToggleFavorite } from "@/hooks/useMeetings";

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Not started" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Processing" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

export default function MeetingsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [starredOnly, setStarredOnly] = useState(false);
  const [page, setPage] = useState(1);

  const params = useMemo(
    () => ({
      search: search || undefined,
      processing_status: status || undefined,
      is_favorite: starredOnly || undefined,
      page,
    }),
    [search, status, starredOnly, page],
  );

  const router = useRouter();
  const { data, isLoading, isError, error, isFetching, refetch } = useMeetings(params);
  const deleteMeeting = useDeleteMeeting();
  const toggleFavorite = useToggleFavorite();
  const [menu, setMenu] = useState<ContextMenuState | null>(null);

  const handleDelete = (id: string, title: string) => {
    if (window.confirm(`Delete "${title}"? This can be undone by an administrator.`)) {
      deleteMeeting.mutate(id);
    }
  };

  const downloadRecording = async (m: Meeting) => {
    const file = m.current_file;
    if (!file?.download_url) {
      toast.error("Nothing to download", "This meeting has no recording file.");
      return;
    }
    try {
      const blob = await meetingsApi.download(m.id, file.version);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.original_filename || "recording";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Download failed");
    }
  };

  const archive = async (m: Meeting) => {
    try {
      await meetingsApi.update(m.id, { is_archived: !m.is_archived });
      toast.success(m.is_archived ? "Unarchived" : "Archived", m.title);
      refetch();
    } catch {
      toast.error("Could not update the meeting.");
    }
  };

  const openMenu = (e: React.MouseEvent, m: Meeting) => {
    e.preventDefault();
    setMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { label: "Open", icon: ExternalLink, onClick: () => router.push(`/meetings/${m.id}`) },
        {
          label: m.is_favorite ? "Unstar" : "Star",
          icon: Star,
          onClick: () => toggleFavorite.mutate(m.id),
        },
        { label: m.is_archived ? "Unarchive" : "Archive", icon: Archive, onClick: () => archive(m) },
        { label: "Download recording", icon: Download, onClick: () => downloadRecording(m) },
        { label: "Delete", icon: Trash2, danger: true, onClick: () => handleDelete(m.id, m.title) },
      ],
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Meetings</h1>
          <p className="mt-1 text-sm text-muted">Browse, search and manage your uploaded meetings.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/meetings/live">
            <Button variant="outline">
              <Radio className="h-4 w-4" /> Go live
            </Button>
          </Link>
          <Link href="/meetings/upload">
            <Button>
              <UploadCloud className="h-4 w-4" /> Upload meeting
            </Button>
          </Link>
        </div>
      </div>

      {/* Persistent, backend-backed view of imports in progress (survives navigation). */}
      <ImportsQueue />

      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input
            className="pl-9"
            placeholder="Search by title or description…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-foreground focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => {
            setStarredOnly((v) => !v);
            setPage(1);
          }}
          aria-pressed={starredOnly}
          className={cn(
            "inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium transition-colors",
            starredOnly
              ? "border-amber-300 bg-amber-50 text-amber-700"
              : "border-border bg-surface text-muted hover:text-foreground",
          )}
        >
          <Star className={cn("h-4 w-4", starredOnly && "fill-amber-400 text-amber-400")} />
          Starred
        </button>
      </div>

      {isLoading ? (
        <SkeletonList rows={6} label="Loading meetings" />
      ) : isError ? (
        <ErrorState title="Couldn't load meetings"
          description={getApiErrorMessage(error, "Could not load meetings.")}
          onRetry={() => refetch()} />
      ) : !data || data.results.length === 0 ? (
        <EmptyState
          title="No meetings yet"
          description="Once you upload a recording it will appear here with its transcript and AI insights."
          action={
            <Link href="/meetings/upload">
              <Button>
                <UploadCloud className="h-4 w-4" /> Upload your first meeting
              </Button>
            </Link>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-slate-50 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Title</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Duration</th>
                <th className="px-5 py-3 font-medium">Size</th>
                <th className="px-5 py-3 font-medium">Created</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.results.map((meeting) => (
                <tr
                  key={meeting.id}
                  className="hover:bg-slate-50/60"
                  onContextMenu={(e) => openMenu(e, meeting)}
                >
                  <td className="px-5 py-3">
                    <Link href={`/meetings/${meeting.id}`} className="font-medium text-foreground hover:text-brand-600">
                      {meeting.title}
                    </Link>
                    {meeting.description && (
                      <p className="mt-0.5 line-clamp-1 text-xs text-muted">{meeting.description}</p>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <ProcessingBadge status={meeting.processing_status as ProcessingStatus} />
                  </td>
                  <td className="px-5 py-3 text-muted">{formatDuration(meeting.duration_seconds)}</td>
                  <td className="px-5 py-3 text-muted">{formatBytes(meeting.current_file?.size_bytes)}</td>
                  <td className="px-5 py-3 text-muted">{formatDate(meeting.created_at)}</td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => toggleFavorite.mutate(meeting.id)}
                        className={cn(
                          "rounded-md p-1.5 hover:bg-amber-50",
                          meeting.is_favorite ? "text-amber-500" : "text-muted hover:text-amber-500",
                        )}
                        aria-label={meeting.is_favorite ? `Unstar ${meeting.title}` : `Star ${meeting.title}`}
                        aria-pressed={meeting.is_favorite}
                      >
                        <Star className={cn("h-4 w-4", meeting.is_favorite && "fill-amber-400")} />
                      </button>
                      <button
                        onClick={() => handleDelete(meeting.id, meeting.title)}
                        className="rounded-md p-1.5 text-muted hover:bg-danger-bg hover:text-danger"
                        aria-label={`Delete ${meeting.title}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted">
            Page {data.page} of {data.total_pages} · {data.count} total
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!data.previous || isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!data.next || isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {menu && <ContextMenu {...menu} onClose={() => setMenu(null)} />}
    </div>
  );
}
