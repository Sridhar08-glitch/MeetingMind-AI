"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { authApi, type RegisterPayload } from "@/lib/api/auth";
import { useAuthStore } from "@/store/auth";

/** Handle login: obtain tokens, persist the session, and route to the Copilot
 * (the primary entry) — or back to the protected page the user first attempted.
 * `next` is read from the URL in onSuccess (client-only) to avoid pulling
 * useSearchParams into every page that imports this hook. */
export function useLogin() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);

  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authApi.login(email, password),
    onSuccess: (data) => {
      setSession({ access: data.access, refresh: data.refresh, user: data.user });
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next && next.startsWith("/") ? next : "/copilot");
    },
  });
}

export function useRegister() {
  return useMutation({
    mutationFn: (payload: RegisterPayload) => authApi.register(payload),
  });
}

export function useLogout() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clear = useAuthStore((s) => s.clear);

  return useMutation({
    mutationFn: async () => {
      const refresh = useAuthStore.getState().refreshToken;
      if (refresh) {
        try {
          await authApi.logout(refresh);
        } catch {
          // Logout is best-effort; clear locally regardless of server outcome.
        }
      }
    },
    onSettled: () => {
      clear();
      queryClient.clear();
      router.replace("/login");
    },
  });
}

export function useForgotPassword() {
  return useMutation({ mutationFn: (email: string) => authApi.forgotPassword(email) });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: ({ token, password }: { token: string; password: string }) =>
      authApi.resetPassword(token, password),
  });
}

export function useUpdateProfile() {
  const setUser = useAuthStore((s) => s.setUser);
  return useMutation({
    mutationFn: (payload: { first_name?: string; last_name?: string }) =>
      authApi.updateProfile(payload),
    onSuccess: (user) => setUser(user),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: { current_password: string; new_password: string }) =>
      authApi.changePassword(payload),
  });
}
