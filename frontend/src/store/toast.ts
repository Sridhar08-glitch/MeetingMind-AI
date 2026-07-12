import { create } from "zustand";

export type ToastVariant = "success" | "error" | "info";

export interface Toast {
  id: string;
  title: string;
  message?: string;
  variant: ToastVariant;
  duration: number; // ms; 0 = sticky
  href?: string; // optional click-through
}

interface ToastState {
  toasts: Toast[];
  push: (t: Partial<Toast> & { title: string }) => string;
  dismiss: (id: string) => void;
}

let counter = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = t.id ?? `toast-${(counter += 1)}-${Date.now()}`;
    set((s) => {
      // De-dupe by id so a repeated event (e.g. polling) doesn't stack toasts.
      if (s.toasts.some((x) => x.id === id)) return s;
      const next: Toast = { duration: 5000, variant: "info", message: undefined, href: undefined, ...t, id };
      return { toasts: [...s.toasts, next] };
    });
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** Imperative helper so any code can raise a toast without a hook. */
export const toast = {
  success: (title: string, message?: string, extra?: Partial<Toast>) =>
    useToastStore.getState().push({ title, message, variant: "success", ...extra }),
  error: (title: string, message?: string, extra?: Partial<Toast>) =>
    useToastStore.getState().push({ title, message, variant: "error", ...extra }),
  info: (title: string, message?: string, extra?: Partial<Toast>) =>
    useToastStore.getState().push({ title, message, variant: "info", ...extra }),
  show: (t: Partial<Toast> & { title: string }) => useToastStore.getState().push(t),
  dismiss: (id: string) => useToastStore.getState().dismiss(id),
};
