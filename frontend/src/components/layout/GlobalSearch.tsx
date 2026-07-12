"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Clock, FileText, Loader2, Search, X } from "lucide-react";

import { knowledgeApi, type SearchResult } from "@/lib/api/knowledge";
import { useRecentsStore } from "@/store/recents";
import { useSearchHistoryStore } from "@/store/searchHistory";
import { cn, formatTimestamp } from "@/lib/utils";

function destinationFor(r: SearchResult): string {
  if (r.meeting_id) return `/meetings/${r.meeting_id}`;
  if (r.project_id) return "/workspace";
  return "/knowledge";
}

/** Full-text/semantic search across meetings, transcripts, decisions, tasks…
 *  Mounted only while open (by the layout) so it always opens with fresh state. */
export function GlobalSearch({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);
  const recents = useRecentsStore((s) => s.items);
  const history = useSearchHistoryStore((s) => s.queries);
  const recordSearch = useSearchHistoryStore((s) => s.record);

  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 220);
    return () => clearTimeout(t);
  }, [query]);

  const { data, isFetching } = useQuery({
    queryKey: ["global-search", debounced],
    queryFn: () => knowledgeApi.search(debounced, {}, 15),
    enabled: debounced.length >= 2,
    staleTime: 30_000,
  });

  // Group results by entity type (sorted so grouped items stay contiguous, which
  // keeps arrow-key navigation over the flat index correct).
  const results = useMemo(
    () => [...(data?.results ?? [])].sort((a, b) => a.entity_type.localeCompare(b.entity_type)),
    [data],
  );

  const go = useCallback(
    (r: SearchResult) => {
      if (debounced) recordSearch(debounced);
      router.push(destinationFor(r));
      onClose();
    },
    [router, onClose, debounced, recordSearch],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => Math.min(a + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
      } else if (e.key === "Enter" && results[active]) {
        e.preventDefault();
        go(results[active]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [results, active, go, onClose]);

  return (
    <div
      className="fixed inset-0 z-[55] flex items-start justify-center bg-slate-900/40 px-4 pt-[12vh] backdrop-blur-sm motion-safe:animate-[fadeIn_120ms_ease-out]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Search"
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Search meetings, transcripts, decisions, tasks…"
            className="h-12 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted focus:outline-none"
          />
          {isFetching && <Loader2 className="h-4 w-4 animate-spin text-muted" />}
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-slate-100" aria-label="Close search">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[52vh] overflow-y-auto scrollbar-thin p-2">
          {debounced.length < 2 ? (
            <>
              {history.length > 0 && (
                <div className="mb-1">
                  <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    Recent searches
                  </p>
                  {history.map((q) => (
                    <button
                      key={q}
                      onClick={() => setQuery(q)}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-50"
                    >
                      <Clock className="h-4 w-4 shrink-0 text-muted" />
                      <span className="truncate text-sm text-foreground">{q}</span>
                    </button>
                  ))}
                </div>
              )}
              <RecentsList
                recents={recents}
                onPick={(id) => {
                  router.push(`/meetings/${id}`);
                  onClose();
                }}
              />
            </>
          ) : results.length === 0 && !isFetching ? (
            <p className="px-3 py-8 text-center text-sm text-muted">No matches for “{debounced}”.</p>
          ) : (
            results.map((r, i) => {
              const showHeader = i === 0 || results[i - 1].entity_type !== r.entity_type;
              return (
                <div key={`${r.entity_type}-${r.entity_id}`}>
                  {showHeader && (
                    <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                      {r.entity_type}
                    </p>
                  )}
                  <button
                    onClick={() => go(r)}
                    onMouseEnter={() => setActive(i)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left",
                      i === active ? "bg-brand-50" : "hover:bg-slate-50",
                    )}
                  >
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
                    <span className="min-w-0 flex-1">
                      <span className="truncate text-sm font-medium text-foreground">{r.title}</span>
                      {r.snippet && <span className="mt-0.5 line-clamp-1 block text-xs text-muted">{r.snippet}</span>}
                      <span className="mt-0.5 block truncate text-[11px] text-muted/80">
                        {r.meeting_title ?? "Knowledge"}
                        {r.speaker ? ` · ${r.speaker}` : ""}
                        {r.timestamp != null ? ` · ${formatTimestamp(r.timestamp)}` : ""}
                      </span>
                    </span>
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

function RecentsList({
  recents,
  onPick,
}: {
  recents: { id: string; title: string }[];
  onPick: (id: string) => void;
}) {
  if (recents.length === 0) {
    return <p className="px-3 py-8 text-center text-sm text-muted">Type at least 2 characters to search.</p>;
  }
  return (
    <div>
      <p className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">Recently opened</p>
      {recents.map((r) => (
        <button
          key={r.id}
          onClick={() => onPick(r.id)}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-50"
        >
          <FileText className="h-4 w-4 shrink-0 text-muted" />
          <span className="truncate text-sm text-foreground">{r.title}</span>
        </button>
      ))}
    </div>
  );
}
