import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import { useAuthStore } from "@/store/auth";
import type { ApiError } from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

/** Attach the current access token to every outgoing request. */
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    const headers = AxiosHeaders.from(config.headers);
    headers.set("Authorization", `Bearer ${token}`);
    config.headers = headers;
  }
  return config;
});

// --- Transparent refresh on 401 --------------------------------------------
// A single in-flight refresh is shared by all queued requests so we never fire
// multiple refreshes at once.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = useAuthStore.getState().refreshToken;
  if (!refresh) throw new Error("No refresh token available.");
  const { data } = await axios.post<{ access: string; refresh?: string }>(
    `${API_BASE_URL}/auth/refresh/`,
    { refresh },
  );
  const store = useAuthStore.getState();
  store.setAccessToken(data.access);
  if (data.refresh) {
    useAuthStore.setState({ refreshToken: data.refresh });
  }
  return data.access;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;

    const isAuthEndpoint = original?.url?.includes("/auth/login") ||
      original?.url?.includes("/auth/refresh");

    if (error.response?.status === 401 && original && !original._retry && !isAuthEndpoint) {
      original._retry = true;
      try {
        refreshPromise = refreshPromise ?? refreshAccessToken();
        const newAccess = await refreshPromise;
        refreshPromise = null;
        const headers = AxiosHeaders.from(original.headers);
        headers.set("Authorization", `Bearer ${newAccess}`);
        original.headers = headers;
        return api(original);
      } catch (refreshError) {
        refreshPromise = null;
        // Refresh failed — clear the session and let the app redirect to login.
        useAuthStore.getState().clear();
        if (typeof window !== "undefined") {
          window.location.assign("/login");
        }
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);

/** Extract a human-readable message from an axios error in our envelope shape. */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiError | undefined;
    if (data?.error?.message) return data.error.message;
    if (error.message) return error.message;
  }
  return fallback;
}

/** Extract the machine-readable error code (e.g. `duplicate_upload`) if present. */
export function getApiErrorCode(error: unknown): string | null {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiError | undefined;
    return data?.error?.code ?? null;
  }
  return null;
}

/** Extract the structured `error.details` payload if present. */
export function getApiErrorDetails(error: unknown): Record<string, unknown> | null {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiError | undefined;
    return data?.error?.details ?? null;
  }
  return null;
}
