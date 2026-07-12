import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface RecentMeeting {
  id: string;
  title: string;
  at: number;
}

interface RecentsState {
  items: RecentMeeting[];
  record: (m: { id: string; title: string }) => void;
  clear: () => void;
}

const MAX_RECENTS = 8;

/** Most-recently opened meetings, persisted client-side (no backend needed). */
export const useRecentsStore = create<RecentsState>()(
  persist(
    (set) => ({
      items: [],
      record: (m) =>
        set((s) => ({
          items: [
            { id: m.id, title: m.title, at: Date.now() },
            ...s.items.filter((x) => x.id !== m.id),
          ].slice(0, MAX_RECENTS),
        })),
      clear: () => set({ items: [] }),
    }),
    { name: "meetingmind-recents" },
  ),
);
