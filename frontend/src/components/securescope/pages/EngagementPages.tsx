"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Activity,
  Calendar,
  Clock,
  Pause,
  Play,
  Plus,
  Shield,
  ShieldAlert,
  Square,
  Zap,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
// Removed mock imports
import { EngagementStateBadge, Pill, RiskTierBadge, StatusBadge } from "../shared/badges";
import { AlertBanner, CyberButton, EmptyState, KeyValue } from "../shared/ui";
import { EventTimeline } from "../shared/lifecycle";
import { KillSwitchControl } from "../shared/secure-cards";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

export function EngagementsListPage() {
  const openEngagement = useApp((s) => s.openEngagement);
  const engagements = useApp((s) => s.engagements);
  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Engagements" }]}
          title="Engagements"
          description="Engagements are operational time windows bound to an authorization. They control when validation executions may run and carry the engagement-level kill switch."
          right={<CyberButton size="sm" variant="primary"><Plus className="w-3 h-3" /> New engagement</CyberButton>}
        />
        <div className="px-4 lg:px-6 py-4">
          <div className="ss-panel overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
                  <th className="text-left px-3 py-2 ss-eyebrow">Code</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Name</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">State</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Authorization</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Window</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Max risk</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Active execs</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Kill switch</th>
                  <th className="text-left px-3 py-2 ss-eyebrow"></th>
                </tr>
              </thead>
              <tbody>
                {engagements.map((e) => (
                  <tr key={e.id} onClick={() => openEngagement(e.id)} className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer">
                    <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{e.code}</code></td>
                    <td className="px-3 py-2.5 text-slate-200">{e.name}</td>
                    <td className="px-3 py-2.5"><EngagementStateBadge state={e.state} /></td>
                    <td className="px-3 py-2.5 ss-mono-xs text-slate-400">{e.authorizationCode}</td>
                    <td className="px-3 py-2.5 ss-mono-xs text-slate-400">{e.windowStart.slice(0,10)} → {e.windowEnd.slice(0,10)}</td>
                    <td className="px-3 py-2.5"><RiskTierBadge tier={e.maxRiskTier} /></td>
                    <td className="px-3 py-2.5 ss-mono-xs text-slate-300 tnum">{e.activeExecutions}</td>
                    <td className="px-3 py-2.5">
                      {e.killSwitch.state === "inactive" ? (
                        <Pill tone="slate">inactive</Pill>
                      ) : (
                        <Pill tone="amber"><ShieldAlert className="w-2.5 h-2.5" /> {e.killSwitch.state}</Pill>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-cyan-300 text-[10px] uppercase tracking-wider">Open →</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

export function EngagementDetailPage() {
  const engId = useApp((s) => s.selectedEngagementId);
  const go = useApp((s) => s.go);
  const openExecution = useApp((s) => s.openExecution);
  const requestKillSwitch = useApp((s) => s.requestKillSwitch);
  const engagements = useApp((s) => s.engagements);
  const executions = useApp((s) => s.executions);
  const eng = engagements.find((e) => e.id === engId) ?? { id: "", code: "—", name: "Unknown", organizationId: "", organizationName: "", projectId: "", projectName: "", authorizationId: "", authorizationCode: "", state: "draft", windowStart: "", windowEnd: "", maxRiskTier: "moderate", scopedAssetNames: [], activeExecutions: 0, killSwitch: { state: "inactive" }, createdAt: "" };
  const engExecs = executions.filter((e) => e.engagementId === eng.id);

  const windowStart = new Date(eng.windowStart).getTime();
  const windowEnd = new Date(eng.windowEnd).getTime();
  const now = Date.now();
  const windowPct = Math.max(0, Math.min(100, ((now - windowStart) / (windowEnd - windowStart)) * 100));

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[
            { label: "Engagements", onClick: () => go("engagements") },
            { label: eng.code },
          ]}
          title={
            <div className="flex items-center gap-3 flex-wrap">
              <code className="ss-mono text-cyan-200">{eng.code}</code>
              <EngagementStateBadge state={eng.state} />
              <RiskTierBadge tier={eng.maxRiskTier} />
              {eng.killSwitch.state !== "inactive" && (
                <Pill tone="amber"><ShieldAlert className="w-2.5 h-2.5" /> kill switch {eng.killSwitch.state}</Pill>
              )}
            </div>
          }
          description={eng.name}
          meta={
            <>
              <Pill tone="slate"><Shield className="w-2.5 h-2.5" /> {eng.authorizationCode}</Pill>
              <Pill tone="slate"><Zap className="w-2.5 h-2.5" /> {eng.activeExecutions} active execs</Pill>
              <Pill tone="slate">{eng.organizationName} / {eng.projectName}</Pill>
            </>
          }
          right={
            <>
              {eng.state === "active" && (
                <CyberButton size="sm" variant="ghost"><Pause className="w-3 h-3" /> Pause</CyberButton>
              )}
              {eng.state === "paused" && (
                <CyberButton size="sm" variant="primary"><Play className="w-3 h-3" /> Resume</CyberButton>
              )}
              <CyberButton size="sm" variant="ghost"><Square className="w-3 h-3" /> Complete</CyberButton>
            </>
          }
        />

        {/* Time window horizontal range */}
        <div className="px-4 lg:px-6 py-4">
          <div className="ss-panel p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-xs font-semibold text-slate-100">Testing window</span>
              </div>
              <div className="flex items-center gap-2">
                <Clock className="w-3 h-3 text-slate-500" />
                <span className="ss-mono-xs text-slate-400">{eng.windowStart.replace("T", " ").slice(0, 16)} → {eng.windowEnd.replace("T", " ").slice(0, 16)} UTC</span>
              </div>
            </div>
            <div className="relative h-2 bg-(--ss-surface-3) rounded-full overflow-hidden">
              <div
                className={cn(
                  "absolute inset-y-0 left-0 rounded-full",
                  eng.state === "active" ? "bg-cyan-400/70" : "bg-slate-600"
                )}
                style={{ width: `${windowPct}%` }}
              />
              <div
                className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3 bg-cyan-300 ss-glow-cyan"
                style={{ left: `${windowPct}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-2 text-[10px] text-slate-500">
              <span>Window start</span>
              <span className={cn(
                "uppercase tracking-wider",
                eng.state === "active" ? "text-cyan-300" : "text-slate-500"
              )}>
                {eng.state === "active" ? "• Now in window" : `state: ${eng.state}`}
              </span>
              <span>Window end</span>
            </div>
          </div>
        </div>

        <div className="px-4 lg:px-6 pb-6 grid lg:grid-cols-[1.4fr_1fr] gap-4">
          {/* Left: active executions + lifecycle */}
          <div className="space-y-4">
            <div className="ss-panel p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Activity className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Active executions</span>
                </div>
                <CyberButton size="sm" variant="primary" onClick={() => go("execution_wizard")}><Plus className="w-3 h-3" /> Queue execution</CyberButton>
              </div>
              {engExecs.length === 0 ? (
                <EmptyState title="No executions on this engagement" icon={<Activity className="w-5 h-5" />} />
              ) : (
                <ul className="space-y-2">
                  {engExecs.map((e) => (
                    <li key={e.id} onClick={() => openExecution(e.id)} className="flex items-center justify-between p-3 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 cursor-pointer">
                      <div className="min-w-0">
                        <code className="ss-mono-xs text-cyan-200">{e.code}</code>
                        <div className="text-[11px] text-slate-400 mt-0.5 truncate">{e.templateName} · {e.assetName}</div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <StatusBadge status={e.status} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="ss-panel p-4">
              <div className="flex items-center gap-2 mb-3">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-xs font-semibold text-slate-100">Engagement lifecycle</span>
              </div>
              <EventTimeline events={[
                { id: "el1", at: eng.createdAt, kind: "worker_started", label: "Engagement created", safeMeta: { by: "k.andrade@nasari.sec" } },
                ...(eng.state === "active" || eng.state === "paused" || eng.state === "completed"
                  ? [{ id: "el2", at: eng.windowStart, kind: "worker_finished", label: "Engagement activated", safeMeta: { state: "active" } }]
                  : []),
                ...(eng.state === "paused"
                  ? [{ id: "el3", at: new Date().toISOString(), kind: "blocked_by_control", label: "Engagement paused", safeMeta: { by: "operator" } }]
                  : []),
              ]} />
            </div>

            <div className="ss-panel p-4">
              <div className="ss-eyebrow mb-2">Safety policy summary</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0">
                <KeyValue k="Max risk tier" v={<RiskTierBadge tier={eng.maxRiskTier} />} />
                <KeyValue k="Authorization" v={<code className="ss-mono-xs text-cyan-200">{eng.authorizationCode}</code>} />
                <KeyValue k="Scoped assets" v={eng.scopedAssetNames.length} mono />
                <KeyValue k="Active executions" v={eng.activeExecutions} mono />
              </div>
              <AlertBanner tone="info" title="Policy enforcement" className="mt-3">
                Execution outside the window, beyond the risk tier, or against unscoped assets is blocked by the safety control and surfaces as <code className="ss-mono-xs text-amber-200">blocked_by_control</code>.
              </AlertBanner>
            </div>
          </div>

          {/* Right: kill switch panel */}
          <div className="space-y-4">
            <KillSwitchControl
              state={eng.killSwitch.state}
              activatedBy={eng.killSwitch.activatedBy}
              activatedAt={eng.killSwitch.activatedAt}
              reason={eng.killSwitch.reason}
              affectedExecutions={eng.killSwitch.affectedExecutions}
              onActivate={() => requestKillSwitch(eng.id)}
              onDisarm={() => requestKillSwitch(null)}
            />

            <div className="ss-panel p-4">
              <div className="ss-eyebrow mb-2">Scoped assets</div>
              <ul className="space-y-1">
                {eng.scopedAssetNames.map((a) => (
                  <li key={a} className="text-[11px] text-slate-200 border border-(--ss-hairline) rounded-sm px-2 py-1">{a}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
