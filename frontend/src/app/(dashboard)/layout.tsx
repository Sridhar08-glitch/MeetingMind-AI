"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { MobileNav } from "@/components/layout/MobileNav";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { GlobalSearch } from "@/components/layout/GlobalSearch";
import { KeyboardShortcuts } from "@/components/layout/KeyboardShortcuts";
import { DocumentTitle } from "@/components/layout/DocumentTitle";
import { CommandPalette } from "@/components/copilot/CommandPalette";
import { GuidedTour } from "@/components/tour/GuidedTour";
import { ToastViewport } from "@/components/ui/Toast";
import { FullPageSpinner } from "@/components/ui/Feedback";
import { useAuthStore } from "@/store/auth";
import { useProcessingToasts } from "@/hooks/useMeetings";

/** Client-side auth guard wrapping every authenticated page. */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const hydrated = useAuthStore((s) => s.hydrated);
  const accessToken = useAuthStore((s) => s.accessToken);
  const [navOpen, setNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  // App-wide toast when a meeting finishes processing.
  useProcessingToasts();

  useEffect(() => {
    if (hydrated && !accessToken) {
      // Preserve the attempted page so login can return the user to it.
      const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [hydrated, accessToken, router, pathname]);

  // "/" opens global search (unless the user is typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      e.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Wait for persisted auth to load, and avoid flashing protected content.
  if (!hydrated || !accessToken) {
    return <FullPageSpinner />;
  }

  return (
    <div className="flex min-h-screen flex-1">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>
      <Sidebar />
      <MobileNav open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenuClick={() => setNavOpen(true)} onSearch={() => setSearchOpen(true)} />
        {/* Mobile breadcrumb row (topbar shows breadcrumbs only on desktop). */}
        <div className="border-b border-border bg-surface px-4 py-2 lg:hidden">
          <Breadcrumbs />
        </div>
        <main id="main-content" className="flex-1 overflow-y-auto scrollbar-thin p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
      <CommandPalette />
      {searchOpen && <GlobalSearch onClose={() => setSearchOpen(false)} />}
      <KeyboardShortcuts />
      <GuidedTour />
      <ToastViewport />
      <DocumentTitle />
    </div>
  );
}
