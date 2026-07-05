"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Search,
  Bell,
  ChevronDown,
  Shield,
  Activity,
  Server,
  Radio,
  Settings,
  LogOut,
  User,
  Globe,
  Command,
} from "lucide-react";
import { useApp, NAV_ITEMS } from "@/lib/securescope/store";
import type { RouteKey } from "@/lib/securescope/types";

// ============================================================
// TopNavCommandBar — global fixed header
// Left: SecureScope mark · Center: horizontal nav · Right: search,
// environment badge, dispatch status, notifications, user menu.
// ============================================================

function activeModule(route: RouteKey): string {
  if (route.startsWith("organization")) return "Organizations";
  if (route.startsWith("project")) return "Projects";
  if (route.startsWith("asset")) return "Assets";
  if (route.startsWith("authorization")) return "Authorizations";
  if (route.startsWith("engagement")) return "Engagements";
  if (route.startsWith("execution")) return "Executions";
  if (route === "workers") return "Workers";
  if (route === "audit") return "Audit";
  if (route === "settings") return "Settings";
  return "Dashboard";
}

function SecureScopeMark() {
  return (
    <div className="flex items-center gap-2.5 select-none">
      <div className="relative">
        <div className="w-7 h-7 border border-cyan-400/50 bg-cyan-500/10 rounded-sm flex items-center justify-center ss-glow-cyan">
          <Shield className="w-3.5 h-3.5 text-cyan-300" />
        </div>
        <div className="absolute -bottom-0.5 -right-0.5 w-1.5 h-1.5 bg-emerald-400 rounded-full ss-pulse-green" />
      </div>
      <div className="leading-none">
        <div className="text-[15px] font-semibold tracking-tight text-slate-100">
          Secure<span className="text-cyan-300">Scope</span>
        </div>
        <div className="text-[9px] uppercase tracking-[0.22em] text-slate-500 mt-0.5">
          Validation Control
        </div>
      </div>
    </div>
  );
}

function EnvironmentBadge() {
  return (
    <div className="hidden lg:flex items-center gap-1.5 px-2 py-1 rounded-sm border border-amber-500/30 bg-amber-500/5">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
      <span className="text-[10px] uppercase tracking-wider text-amber-300 font-medium">Staging</span>
    </div>
  );
}

function DispatchStatusPill() {
  return (
    <div className="hidden xl:flex items-center gap-2 px-2 py-1 rounded-sm border border-emerald-500/25 bg-emerald-500/5">
      <div className="relative">
        <Server className="w-3 h-3 text-emerald-400" />
      </div>
      <div className="leading-none">
        <div className="text-[9px] uppercase tracking-wider text-slate-500">Dispatch</div>
        <div className="text-[10px] text-emerald-300 font-medium">Celery · online</div>
      </div>
    </div>
  );
}

function GlobalSearch() {
  return (
    <div className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-2) min-w-[220px] lg:min-w-[280px]">
      <Search className="w-3.5 h-3.5 text-slate-500" />
      <input
        type="text"
        placeholder="Search executions, assets, authorizations…"
        className="bg-transparent text-xs text-slate-200 placeholder:text-slate-600 outline-none flex-1 min-w-0"
      />
      <kbd className="ss-mono-xs text-[10px] text-slate-500 border border-(--ss-hairline-strong) rounded-sm px-1.5 py-0.5 hidden lg:inline-flex items-center gap-0.5">
        <Command className="w-2.5 h-2.5" />K
      </kbd>
    </div>
  );
}

function NotificationBell() {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative w-8 h-8 flex items-center justify-center rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-2) hover:bg-(--ss-surface-3) text-slate-400 hover:text-slate-200 transition-colors"
        aria-label="Notifications"
      >
        <Bell className="w-3.5 h-3.5" />
        <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-amber-400 ss-pulse-amber" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-10 z-40 w-80 ss-panel-raised shadow-2xl">
            <div className="px-3 py-2 border-b border-(--ss-hairline-strong) flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200">Operational Alerts</span>
              <span className="text-[10px] text-slate-500">3 unread</span>
            </div>
            <ul className="max-h-72 overflow-y-auto ss-scroll">
              {[
                { t: "Kill switch armed on ENG-CBV-001", at: "2m ago", tone: "amber" },
                { t: "Authorization AUTH-NSL-001 expires in 13d", at: "1h ago", tone: "yellow" },
                { t: "EXEC-2026-0702-003 validated · 6/6 steps", at: "20m ago", tone: "green" },
              ].map((n, i) => (
                <li key={i} className="px-3 py-2 border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/50 cursor-pointer">
                  <div className="flex items-start gap-2">
                    <span
                      className={cn(
                        "mt-1 w-1.5 h-1.5 rounded-full",
                        n.tone === "amber" && "bg-amber-400",
                        n.tone === "yellow" && "bg-yellow-400",
                        n.tone === "green" && "bg-emerald-400"
                      )}
                    />
                    <div className="flex-1">
                      <div className="text-[11px] text-slate-200">{n.t}</div>
                      <div className="text-[10px] text-slate-500 mt-0.5">{n.at}</div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
            <div className="px-3 py-2 border-t border-(--ss-hairline-strong)">
              <button className="text-[10px] text-cyan-300 hover:text-cyan-200 uppercase tracking-wider">
                View audit trail →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function UserMenu() {
  const [open, setOpen] = React.useState(false);
  const logout = useApp((s) => s.logout);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 pl-1.5 pr-2 py-1 rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-2) hover:bg-(--ss-surface-3) transition-colors"
      >
        <div className="w-6 h-6 rounded-sm bg-linear-to-br from-cyan-500/30 to-blue-600/20 border border-cyan-400/30 flex items-center justify-center">
          <span className="text-[10px] font-semibold text-cyan-200">KA</span>
        </div>
        <div className="hidden sm:block leading-none text-left">
          <div className="text-[11px] font-medium text-slate-200">k.andrade</div>
          <div className="text-[9px] text-slate-500 uppercase tracking-wider">Operator</div>
        </div>
        <ChevronDown className="w-3 h-3 text-slate-500" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-10 z-40 w-56 ss-panel-raised shadow-2xl">
            <div className="px-3 py-2.5 border-b border-(--ss-hairline-strong)">
              <div className="text-xs font-medium text-slate-200">Karim Andrade</div>
              <div className="text-[10px] text-slate-500">k.andrade@nasari.sec</div>
              <div className="mt-1 flex items-center gap-1.5">
                <span className="text-[9px] uppercase tracking-wider text-emerald-300 border border-emerald-500/30 bg-emerald-500/5 px-1.5 py-0.5 rounded-sm">
                  MFA Verified
                </span>
                <span className="text-[9px] uppercase tracking-wider text-cyan-300 border border-cyan-500/30 bg-cyan-500/5 px-1.5 py-0.5 rounded-sm">
                  Pentest Coordinator
                </span>
              </div>
            </div>
            <ul className="py-1">
              {[
                { icon: User, label: "Operator profile" },
                { icon: Globe, label: "Region · eu-1" },
                { icon: Settings, label: "Settings" },
              ].map((it) => (
                <li key={it.label}>
                  <button className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-(--ss-surface-3)/50 hover:text-slate-100">
                    <it.icon className="w-3 h-3 text-slate-500" />
                    {it.label}
                  </button>
                </li>
              ))}
            </ul>
            <div className="py-1 border-t border-(--ss-hairline-strong)">
              <button
                onClick={logout}
                className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-red-300 hover:bg-red-500/5"
              >
                <LogOut className="w-3 h-3" />
                Sign out
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function TopNavCommandBar() {
  const route = useApp((s) => s.route);
  const go = useApp((s) => s.go);
  const moduleLabel = activeModule(route);

  return (
    <header className="fixed top-0 left-0 right-0 z-40 h-14 border-b border-(--ss-hairline-strong) bg-[#070B14]/95 backdrop-blur-md">
      <div className="h-full flex items-center gap-4 px-4">
        {/* Left: mark */}
        <button onClick={() => go("dashboard")} className="shrink-0 pr-4 border-r border-(--ss-hairline) h-full flex items-center">
          <SecureScopeMark />
        </button>

        {/* Center: nav */}
        <nav className="flex-1 min-w-0 flex items-center justify-start overflow-x-auto ss-scroll">
          <ul className="flex items-center gap-0.5">
            {NAV_ITEMS.map((item) => {
              const isActive =
                item.key === route ||
                (item.key === "organizations" && route.startsWith("organization")) ||
                (item.key === "projects" && route.startsWith("project")) ||
                (item.key === "assets" && route.startsWith("asset")) ||
                (item.key === "authorizations" && route.startsWith("authorization")) ||
                (item.key === "engagements" && route.startsWith("engagement")) ||
                (item.key === "execution_wizard" && route.startsWith("execution"));
              return (
                <li key={item.key}>
                  <button
                    onClick={() => go(item.key)}
                    className={cn(
                      "relative px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm transition-colors whitespace-nowrap",
                      isActive
                        ? "text-cyan-200 bg-cyan-500/10"
                        : "text-slate-400 hover:text-slate-200 hover:bg-(--ss-surface-3)/50"
                    )}
                  >
                    {item.label}
                    {isActive && (
                      <span className="absolute left-2 right-2 -bottom-px h-px bg-cyan-400 ss-glow-cyan" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Right cluster */}
        <div className="shrink-0 flex items-center gap-2">
          <GlobalSearch />
          <EnvironmentBadge />
          <DispatchStatusPill />
          <NotificationBell />
          <div className="w-px h-6 bg-(--ss-hairline) mx-1" />
          <UserMenu />
        </div>
      </div>

      {/* Module subline (very thin) */}
      <div className="h-5 px-4 flex items-center justify-between border-t border-(--ss-hairline) bg-[#050810]/80 text-[10px]">
        <div className="flex items-center gap-3 text-slate-500">
          <span className="flex items-center gap-1">
            <Activity className="w-2.5 h-2.5" />
            <span className="uppercase tracking-wider">Module</span>
            <span className="text-slate-300">{moduleLabel}</span>
          </span>
          <span className="text-slate-700">/</span>
          <span className="flex items-center gap-1">
            <Radio className="w-2.5 h-2.5" />
            <span className="uppercase tracking-wider">Region</span>
            <span className="text-slate-300 ss-mono-xs">eu-1</span>
          </span>
        </div>
        <div className="hidden md:flex items-center gap-3 text-slate-500">
          <span className="ss-mono-xs">Session · 04:18:22</span>
          <span className="text-slate-700">/</span>
          <span className="flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-emerald-400" />
            <span className="uppercase tracking-wider text-emerald-400">Channel Secure</span>
          </span>
        </div>
      </div>
    </header>
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
    <div className="sticky top-[76px] z-20 h-10 flex items-center justify-between px-4 border-b border-(--ss-hairline-strong) bg-[#070B14]/80 backdrop-blur-sm">
      <div className="flex items-center gap-0.5 overflow-x-auto ss-scroll">
        {items.map((it) => {
          const isActive = it.key === active;
          return (
            <button
              key={it.key}
              onClick={() => onSelect(it.key)}
              className={cn(
                "px-2.5 py-1 text-[11px] uppercase tracking-wider rounded-sm transition-colors whitespace-nowrap flex items-center gap-1.5",
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
      <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-2">
        {breadcrumbs.map((b, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="text-slate-700">/</span>}
            {b.onClick ? (
              <button onClick={b.onClick} className="hover:text-slate-300 uppercase tracking-wider">
                {b.label}
              </button>
            ) : (
              <span className="uppercase tracking-wider">{b.label}</span>
            )}
          </React.Fragment>
        ))}
      </div>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl lg:text-2xl font-semibold tracking-tight text-slate-100">{title}</h1>
          {description && <p className="text-xs text-slate-400 mt-1 max-w-3xl leading-relaxed">{description}</p>}
          {meta && <div className="mt-2.5 flex flex-wrap items-center gap-2">{meta}</div>}
        </div>
        {right && <div className="shrink-0 flex items-center gap-2">{right}</div>}
      </div>
    </div>
  );
}
