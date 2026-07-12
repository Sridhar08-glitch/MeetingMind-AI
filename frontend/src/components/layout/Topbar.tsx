"use client";

import { LogOut, Menu, Search } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { useAuthStore } from "@/store/auth";
import { useLogout } from "@/hooks/useAuth";

export function Topbar({ onMenuClick, onSearch }: { onMenuClick?: () => void; onSearch?: () => void }) {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();

  const initials = (user?.full_name || user?.email || "?")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <header className="flex h-16 items-center gap-3 border-b border-border bg-surface px-4 sm:px-6">
      {/* Mobile: menu + brand */}
      <div className="flex items-center gap-2 lg:hidden">
        <button
          onClick={onMenuClick}
          aria-label="Open navigation"
          className="rounded-lg p-2 text-muted hover:bg-slate-100 hover:text-foreground"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-lg font-semibold text-brand-700">MeetingMind</span>
      </div>

      {/* Desktop: breadcrumbs */}
      <div className="hidden min-w-0 flex-1 lg:block">
        <Breadcrumbs />
      </div>

      <div className="ml-auto flex items-center gap-3">
        {/* Global search trigger */}
        <button
          onClick={onSearch}
          className="hidden items-center gap-2 rounded-lg border border-border bg-slate-50/60 px-3 py-1.5 text-sm text-muted transition-colors hover:border-brand-300 hover:text-foreground sm:flex"
          aria-label="Search everything"
        >
          <Search className="h-4 w-4" />
          <span>Search…</span>
          <kbd className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-muted">/</kbd>
        </button>
        <button
          onClick={onSearch}
          className="rounded-lg p-2 text-muted hover:bg-slate-100 hover:text-foreground sm:hidden"
          aria-label="Search"
        >
          <Search className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
            {initials}
          </div>
          <div className="hidden lg:block">
            <p className="text-sm font-medium text-foreground">{user?.full_name}</p>
            <p className="text-xs text-muted">{user?.email}</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={() => logout.mutate()} isLoading={logout.isPending}>
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Sign out</span>
        </Button>
      </div>
    </header>
  );
}
