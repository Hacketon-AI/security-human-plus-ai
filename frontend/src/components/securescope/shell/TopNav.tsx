"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, LogOut, Menu, Settings, X } from "lucide-react";
import { useApp, NAV_ITEMS } from "@/lib/securescope/store";
import { BrandLogo } from "../shared/ui";
import type { RouteKey } from "@/lib/securescope/types";

// ============================================================
// Console shell — grouped sidebar (drawer below lg) + slim top bar.
// The top bar only shows real state: where you are and who you are.
// ============================================================

const NAV_GROUPS: { label: string; keys: RouteKey[] }[] = [
  { label: "monitor", keys: ["dashboard", "operations", "ai_intelligence"] },
  { label: "inventory", keys: ["organizations", "projects", "assets"] },
  { label: "governance", keys: ["authorizations", "engagements", "execution_wizard"] },
  { label: "runtime", keys: ["workers", "pentest_audit"] },
  { label: "system", keys: ["audit", "settings"] },
];

// Looked up at render time, not module load, so modules importing this file
// don't require the store's NAV_ITEMS to exist (e.g. under test mocks).
function navLabel(key: RouteKey): string {
  return NAV_ITEMS.find((item) => item.key === key)?.label ?? key;
}

function isNavActive(key: RouteKey, route: RouteKey): boolean {
  if (key === route) return true;
  if (key === "organizations") return route.startsWith("organization");
  if (key === "projects") return route.startsWith("project");
  if (key === "assets") return route.startsWith("asset");
  if (key === "authorizations") return route.startsWith("authorization");
  if (key === "engagements") return route.startsWith("engagement");
  if (key === "execution_wizard") return route.startsWith("execution");
  return false;
}

function consolePath(route: RouteKey): string {
  const key = NAV_ITEMS.find((item) => isNavActive(item.key, route))?.key ?? "dashboard";
  return `~/console/${navLabel(key).toLowerCase().replace(/\s+/g, "-")}`;
}

const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300";

function SidebarNav({ onNavigate }: { onNavigate: () => void }) {
  const route = useApp((s) => s.route);
  const go = useApp((s) => s.go);
  return (
    <nav aria-label="Console" className="flex-1 overflow-y-auto px-2 py-3 ss-scroll">
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="mb-4">
          <p className="px-2.5 pb-1 font-mono text-[11px] text-slate-500"># {group.label}</p>
          <ul>
            {group.keys.map((key) => {
              const active = isNavActive(key, route);
              return (
                <li key={key}>
                  <button
                    type="button"
                    onClick={() => {
                      go(key);
                      onNavigate();
                    }}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center rounded-md border-l-2 px-2.5 py-1.5 text-left font-mono text-[13px] transition-colors",
                      FOCUS_RING,
                      active
                        ? "border-cyan-300 bg-white/5 text-white"
                        : "border-transparent text-slate-400 hover:bg-white/[0.03] hover:text-slate-100"
                    )}
                  >
                    {navLabel(key).toLowerCase()}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function UserMenu() {
  const [open, setOpen] = React.useState(false);
  const logout = useApp((state) => state.logout);
  const go = useApp((state) => state.go);
  const user = React.useMemo(() => {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem("securescope_user");
    if (!raw) return null;
    try {
      return JSON.parse(raw) as { email: string; full_name: string | null; role: string; username: string };
    } catch {
      return null;
    }
  }, []);
  const displayName = user?.full_name || user?.username || "operator";

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={cn("flex h-9 items-center gap-2 rounded-md border border-(--ss-hairline-strong) px-2.5 font-mono text-[13px] text-slate-200 transition-colors hover:bg-white/5", FOCUS_RING)}
      >
        <span className="text-cyan-300">@</span>
        <span className="max-w-[12rem] truncate">{user?.username || "operator"}</span>
        <span className="hidden text-slate-500 sm:inline">({user?.role || "operator"})</span>
        <ChevronDown className="size-3.5 text-slate-500" aria-hidden />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div role="menu" className="absolute right-0 top-11 z-40 w-64 rounded-md border border-(--ss-hairline-strong) bg-(--ss-surface-2) shadow-2xl">
            <div className="border-b border-(--ss-hairline-strong) px-3 py-2.5">
              <p className="text-sm font-medium text-slate-100">{displayName}</p>
              <p className="truncate font-mono text-xs text-slate-500">{user?.email || ""}</p>
            </div>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                go("settings");
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-slate-300 hover:bg-white/5 hover:text-white"
            >
              <Settings className="size-4 text-slate-500" aria-hidden />
              Settings
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={logout}
              className="flex w-full items-center gap-2.5 border-t border-(--ss-hairline-strong) px-3 py-2 text-sm text-red-300 hover:bg-red-500/5"
            >
              <LogOut className="size-4" aria-hidden />
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function TopNavCommandBar() {
  const route = useApp((s) => s.route);
  const go = useApp((s) => s.go);
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  return (
    <>
      {drawerOpen && <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setDrawerOpen(false)} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-56 flex-col border-r border-(--ss-hairline-strong) bg-(--ss-surface-1) transition-transform lg:translate-x-0",
          drawerOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-(--ss-hairline-strong) px-4">
          <button type="button" onClick={() => go("dashboard")} className={cn("rounded-md", FOCUS_RING)} aria-label="Double AA overview">
            <BrandLogo className="select-none" />
          </button>
          <button type="button" onClick={() => setDrawerOpen(false)} className={cn("rounded-md p-1 text-slate-400 lg:hidden", FOCUS_RING)} aria-label="Close menu">
            <X className="size-5" aria-hidden />
          </button>
        </div>
        <SidebarNav onNavigate={() => setDrawerOpen(false)} />
      </aside>

      <header className="fixed left-0 right-0 top-0 z-30 h-14 border-b border-(--ss-hairline-strong) bg-(--ss-surface-1)/95 backdrop-blur lg:left-56">
        <div className="flex h-full items-center justify-between gap-3 px-4 lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" onClick={() => setDrawerOpen(true)} className={cn("rounded-md p-1 text-slate-300 lg:hidden", FOCUS_RING)} aria-label="Open menu">
              <Menu className="size-5" aria-hidden />
            </button>
            <p className="truncate font-mono text-[13px] text-slate-400">
              <span className="text-cyan-300">$</span> {consolePath(route)}
            </p>
          </div>
          <UserMenu />
        </div>
      </header>
    </>
  );
}

// ============================================================
// SecondaryContextNav — module-level contextual nav
// ============================================================

export function SecondaryContextNav({
  items,
  active,
  onSelect,
  right,
}: {
  items: { key: string; label: string; count?: number }[];
  active: string;
  onSelect: (key: string) => void;
  right?: React.ReactNode;
}) {
  return (
    <div className="sticky top-14 z-20 h-10 flex items-center justify-between px-4 border-b border-(--ss-hairline-strong) bg-[#0B0D10]/80 backdrop-blur-sm">
      <div className="flex items-center gap-0.5 overflow-x-auto ss-scroll">
        {items.map((it) => {
          const isActive = it.key === active;
          return (
            <button
              key={it.key}
              onClick={() => onSelect(it.key)}
              className={cn(
                "px-2.5 py-1 font-mono text-[13px] rounded-md transition-colors whitespace-nowrap flex items-center gap-1.5",
                isActive ? "text-cyan-200 bg-cyan-500/10" : "text-slate-500 hover:text-slate-300"
              )}
            >
              {it.label}
              {typeof it.count === "number" && (
                <span
                  className={cn(
                    "ss-mono-xs px-1 rounded-sm",
                    isActive ? "bg-cyan-500/20 text-cyan-200" : "bg-(--ss-surface-3) text-slate-500"
                  )}
                >
                  {it.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {right && <div className="flex items-center gap-2 shrink-0">{right}</div>}
    </div>
  );
}

// ============================================================
// PageHeader — breadcrumb + title + actions
// ============================================================

export function PageHeader({
  breadcrumbs,
  title,
  description,
  right,
  meta,
}: {
  breadcrumbs: { label: string; onClick?: () => void }[];
  title: React.ReactNode;
  description?: React.ReactNode;
  right?: React.ReactNode;
  meta?: React.ReactNode;
}) {
  return (
    <div className="px-4 lg:px-6 pt-4 pb-3 border-b border-(--ss-hairline)">
      <div className="flex items-center gap-1.5 font-mono text-xs text-slate-500 mb-2">
        {breadcrumbs.map((b, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="text-slate-700">/</span>}
            {b.onClick ? (
              <button onClick={b.onClick} className="hover:text-slate-300 lowercase">
                {b.label}
              </button>
            ) : (
              <span className="lowercase">{b.label}</span>
            )}
          </React.Fragment>
        ))}
      </div>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0 flex-1">
          <h1 className="font-mono text-xl lg:text-2xl font-bold tracking-tight text-white">{title}</h1>
          {description && <p className="text-sm text-slate-400 mt-1.5 max-w-3xl leading-relaxed">{description}</p>}
          {meta && <div className="mt-2.5 flex flex-wrap items-center gap-2">{meta}</div>}
        </div>
        {right && <div className="shrink-0 flex items-center gap-2">{right}</div>}
      </div>
    </div>
  );
}
