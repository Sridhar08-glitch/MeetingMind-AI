import { create } from "zustand";
import { persist } from "zustand/middleware";

interface DashboardState {
  /** Widget ids the user pinned to the top, in pin order. */
  pinned: string[];
  toggle: (id: string) => void;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      pinned: [],
      toggle: (id) =>
        set((s) => ({
          pinned: s.pinned.includes(id) ? s.pinned.filter((x) => x !== id) : [...s.pinned, id],
        })),
    }),
    { name: "meetingmind-dashboard" },
  ),
);
