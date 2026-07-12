import { create } from "zustand";
import { persist } from "zustand/middleware";

/** First-run guided tour state. `tourSeen` is persisted so the tour shows once. */
interface TourState {
  /** True once the user has completed or skipped the tour. */
  tourSeen: boolean;
  /** Whether the tour overlay is currently open. */
  open: boolean;
  /** Current step index (0-based). */
  step: number;
  start: () => void;
  next: () => void;
  prev: () => void;
  goTo: (step: number) => void;
  skip: () => void;
  finish: () => void;
  /** Re-launch the tour from the beginning (e.g. from Settings). */
  restart: () => void;
}

export const useTourStore = create<TourState>()(
  persist(
    (set) => ({
      tourSeen: false,
      open: false,
      step: 0,
      start: () => set({ open: true, step: 0 }),
      next: () => set((s) => ({ step: s.step + 1 })),
      prev: () => set((s) => ({ step: Math.max(0, s.step - 1) })),
      goTo: (step) => set({ step }),
      skip: () => set({ open: false, tourSeen: true }),
      finish: () => set({ open: false, tourSeen: true }),
      restart: () => set({ open: true, step: 0, tourSeen: false }),
    }),
    {
      name: "meetingmind-tour",
      // Only persist whether the tour has been seen; open/step are transient.
      partialize: (state) => ({ tourSeen: state.tourSeen }),
    },
  ),
);
