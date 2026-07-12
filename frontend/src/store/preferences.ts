import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { MeetingSource } from "@/lib/types";

interface PreferencesState {
  /** Show a toast when a meeting finishes processing. */
  notifyOnComplete: boolean;
  /** Default "source" pre-selected on the upload page. */
  defaultSource: MeetingSource;
  // Remembered language preferences for live meetings (Phase 13). The actual
  // available languages come from the provider capabilities endpoint, not here.
  meetingLanguage: string; // "" = auto-detect
  transcriptLanguage: string; // "original" or a target code
  aiLanguage: string; // "" = same as transcript
  rememberLanguages: boolean;
  setNotifyOnComplete: (v: boolean) => void;
  setDefaultSource: (s: MeetingSource) => void;
  setLanguages: (v: {
    meetingLanguage?: string;
    transcriptLanguage?: string;
    aiLanguage?: string;
  }) => void;
  setRememberLanguages: (v: boolean) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      notifyOnComplete: true,
      defaultSource: "manual_upload",
      meetingLanguage: "",
      transcriptLanguage: "original",
      aiLanguage: "",
      rememberLanguages: true,
      setNotifyOnComplete: (notifyOnComplete) => set({ notifyOnComplete }),
      setDefaultSource: (defaultSource) => set({ defaultSource }),
      setLanguages: (v) => set((s) => ({ ...s, ...v })),
      setRememberLanguages: (rememberLanguages) => set({ rememberLanguages }),
    }),
    { name: "meetingmind-prefs" },
  ),
);
