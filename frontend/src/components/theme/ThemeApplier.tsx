"use client";

import { useEffect } from "react";

import { useThemeStore } from "@/store/theme";

/** Applies the chosen theme to <html> and follows the OS in "system" mode. */
export function ThemeApplier() {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    if (theme === "system") {
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [theme]);

  return null;
}
