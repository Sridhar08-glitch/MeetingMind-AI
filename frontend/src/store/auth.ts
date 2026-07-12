import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { User } from "@/lib/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  /** True once the persisted state has been read from storage on the client. */
  hydrated: boolean;
  setSession: (payload: { access: string; refresh: string; user: User }) => void;
  setAccessToken: (access: string) => void;
  setUser: (user: User) => void;
  setHydrated: () => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      hydrated: false,
      setSession: ({ access, refresh, user }) =>
        set({ accessToken: access, refreshToken: refresh, user }),
      setAccessToken: (access) => set({ accessToken: access }),
      setUser: (user) => set({ user }),
      setHydrated: () => set({ hydrated: true }),
      clear: () => set({ accessToken: null, refreshToken: null, user: null }),
    }),
    {
      name: "meetingmind-auth",
      // Persist only the credentials, not transient flags.
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated();
      },
    },
  ),
);

/** Non-reactive token accessors for use inside axios interceptors. */
export const authTokens = {
  getAccess: () => useAuthStore.getState().accessToken,
  getRefresh: () => useAuthStore.getState().refreshToken,
};
