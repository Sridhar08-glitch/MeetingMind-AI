import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SearchHistoryState {
  queries: string[];
  record: (q: string) => void;
  clear: () => void;
}

export const useSearchHistoryStore = create<SearchHistoryState>()(
  persist(
    (set) => ({
      queries: [],
      record: (q) =>
        set((s) => {
          const t = q.trim();
          if (t.length < 2) return s;
          return { queries: [t, ...s.queries.filter((x) => x.toLowerCase() !== t.toLowerCase())].slice(0, 6) };
        }),
      clear: () => set({ queries: [] }),
    }),
    { name: "meetingmind-search-history" },
  ),
);
