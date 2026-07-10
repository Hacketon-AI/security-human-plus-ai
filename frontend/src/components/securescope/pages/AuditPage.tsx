"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Activity,
  Filter,
  Search,
  User,
  Cpu,
  Calendar,
  Server,
  Shield,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
// Removed mock imports
import { Pill } from "../shared/badges";
import { CyberButton, EmptyState } from "../shared/ui";
import { TopNavCommandBar, PageHeader, SecondaryContextNav } from "../shell/TopNav";

const ACTOR_TYPE_ICON = {
  operator: User,
  system: Server,
  worker: Cpu,
  scheduler: Calendar,
} as const;

const ENTITY_TONE: Record<string, string> = {
  organization: "text-cyan-300",
  project: "text-cyan-300",
  asset: "text-emerald-300",
  authorization: "text-blue-300",
  engagement: "text-amber-300",
  execution: "text-cyan-200",
  credential: "text-slate-300",
  dispatch: "text-cyan-300",
  system: "text-slate-400",
};

export function AuditPage() {
  const [query, setQuery] = React.useState("");
  const [actorType, setActorType] = React.useState<"all" | "operator" | "system" | "worker" | "scheduler">("all");
  const [entityType, setEntityType] = React.useState<string>("all");

  const auditEvents = useApp((s) => s.auditEvents);
  const organizations = useApp((s) => s.organizations);
  const projects = useApp((s) => s.projects);

  const filtered = auditEvents.filter((e) => {
    if (actorType !== "all" && e.actorType !== actorType) return false;
    if (entityType !== "all" && e.entityType !== entityType) return false;
    if (query && !`${e.action} ${e.actor} ${e.entityId}`.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  const openExecution = useApp((s) => s.openExecution);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Audit Trail" }]}
          title="Audit Trail"
          description="Immutable stream of every operator, system, scheduler, and worker action across SecureScope. Filterable by organization, project, asset, execution, and event type."
          meta={
            <>
              <Pill tone="green"><Shield className="w-2.5 h-2.5" /> Append-only</Pill>
              <Pill tone="slate">{auditEvents.length} events · 24h</Pill>
            </>
          }
          right={<CyberButton size="sm" variant="ghost">Export CSV</CyberButton>}
        />
        <SecondaryContextNav
          items={[
            { key: "all", label: "All", count: auditEvents.length },
            { key: "operator", label: "Operator", count: auditEvents.filter((e) => e.actorType === "operator").length },
            { key: "system", label: "System", count: auditEvents.filter((e) => e.actorType === "system").length },
            { key: "worker", label: "Worker", count: auditEvents.filter((e) => e.actorType === "worker").length },
            { key: "scheduler", label: "Scheduler", count: auditEvents.filter((e) => e.actorType === "scheduler").length },
          ]}
          active={actorType}
          onSelect={(k) => setActorType(k as typeof actorType)}
          right={
            <div className="flex items-center gap-2">
              <select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
                className="px-2 py-1 text-[11px] bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-200 outline-none focus:border-cyan-400/50"
              >
                <option value="all">All entities</option>
                <option value="organization">Organization</option>
                <option value="project">Project</option>
                <option value="asset">Asset</option>
                <option value="authorization">Authorization</option>
                <option value="engagement">Engagement</option>
                <option value="execution">Execution</option>
                <option value="credential">Credential</option>
                <option value="dispatch">Dispatch</option>
              </select>
              <div className="flex items-center gap-2 px-2.5 py-1 rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-2)">
                <Search className="w-3 h-3 text-slate-500" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter…"
                  className="bg-transparent text-[11px] text-slate-200 placeholder:text-slate-600 outline-none w-32"
                />
              </div>
            </div>
          }
        />

        <div className="px-4 lg:px-6 py-5">
          {/* Dense event timeline */}
          <div className="ss-panel">
            <div className="px-4 py-2.5 border-b border-(--ss-hairline-strong) flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-xs font-semibold text-slate-100">Event stream</span>
              </div>
              <div className="flex items-center gap-2">
                <Pill tone="cyan">{filtered.length} matching</Pill>
                <Pill tone="slate">newest first</Pill>
              </div>
            </div>
            {auditEvents.length === 0 ? (
              <EmptyState eyebrow="No events" title="No audit events yet" icon={<Activity className="w-5 h-5" />} />
            ) : filtered.length === 0 ? (
              <EmptyState eyebrow="No matches" title="No events match your filters" icon={<Filter className="w-5 h-5" />} />
            ) : (
              <ul className="divide-y divide-(--ss-hairline)">
                {filtered.map((e) => {
                  const Icon = ACTOR_TYPE_ICON[e.actorType] ?? Activity;
                  const time = new Date(e.at).toLocaleString("en-GB", {
                    month: "short",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  });
                  return (
                    <li key={e.id} className="px-4 py-2.5 hover:bg-(--ss-surface-3)/40 transition-colors">
                      <div className="flex items-start gap-3">
                        <div className="shrink-0 mt-0.5 w-6 h-6 rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-2) flex items-center justify-center">
                          <Icon className="w-3 h-3 text-slate-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="ss-mono-xs text-slate-500 tnum">{time}</span>
                              <span className="text-[11px] text-slate-300">{e.actor}</span>
                              <span className="text-slate-700 text-[10px]">·</span>
                              <code className="text-[11px] font-medium text-cyan-200">{e.action}</code>
                            </div>
                            <div className="flex items-center gap-1.5">
                              <Pill tone="slate">{e.actorType}</Pill>
                              <span className={cn("text-[10px] uppercase tracking-wider", ENTITY_TONE[e.entityType])}>
                                {e.entityType}
                              </span>
                            </div>
                          </div>
                          <div className="mt-1 flex items-center gap-2 flex-wrap">
                            <code className="ss-mono-xs text-slate-400">{e.entityId}</code>
                            {e.executionId && (
                              <button
                                onClick={() => {
                                  if (e.executionId) openExecution(e.executionId);
                                }}
                                className="ss-mono-xs text-cyan-300 hover:underline"
                              >
                                {e.executionId}
                              </button>
                            )}
                          </div>
                          {Object.keys(e.safeMetadata).length > 0 && (
                            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                              {Object.entries(e.safeMetadata).map(([k, v]) => (
                                <span key={k} className="text-[10px] text-slate-500">
                                  <span className="text-slate-600">{k}:</span>{" "}
                                  <code className="ss-mono-xs text-slate-400">
                                    {typeof v === "object" && v !== null
                                      ? JSON.stringify(v)
                                      : String(v ?? "")}
                                  </code>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Organization/project filter strip */}
          <div className="mt-4 grid md:grid-cols-2 gap-3">
            <div className="ss-panel p-3">
              <div className="ss-eyebrow mb-2">Filter by organization</div>
              <div className="flex flex-wrap gap-1.5">
                <Pill tone="cyan">All</Pill>
                {organizations.map((o) => (
                  <Pill key={o.id} tone="slate">{o.name}</Pill>
                ))}
              </div>
            </div>
            <div className="ss-panel p-3">
              <div className="ss-eyebrow mb-2">Filter by project</div>
              <div className="flex flex-wrap gap-1.5">
                <Pill tone="cyan">All</Pill>
                {projects.map((p) => (
                  <Pill key={p.id} tone="slate">{p.name}</Pill>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
