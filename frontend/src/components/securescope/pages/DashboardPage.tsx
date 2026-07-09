"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Clock,
  Cpu,
  Gauge,
  Layers,
  Network,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Target,
  Zap,
  Radio,
  Server,
  BrainCircuit,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
// Mock imports removed
import { KpiCell, SectionHeader, StatusBadge, OutcomeBadge, RiskTierBadge, Pill } from "../shared/badges";
import { AlertBanner, CyberButton, EmptyState, KeyValue } from "../shared/ui";
import { EventTimeline, ExecutionLifecycleRail } from "../shared/lifecycle";
import { TopNavCommandBar } from "../shell/TopNav";

// ============================================================
// DispatchStatusStrip — full-width command strip
// ============================================================

function DispatchStatusStrip() {
  const items = [
    { label: "Environment", value: "Staging", tone: "amber" as const, hint: "Pre-prod mirror" },
    { label: "Dispatch Backend", value: "Celery", tone: "green" as const, hint: "online · eu-1" },
    { label: "Worker Auth Mode", value: "Per-execution", tone: "cyan" as const, hint: "credential" },
    { label: "Shared-token Fallback", value: "Disabled", tone: "default" as const, hint: "policy" },
    { label: "Global Kill Switch", value: "Inactive", tone: "green" as const, hint: "armed: 1 engagement" },
    { label: "Running Executions", value: "1", tone: "cyan" as const, hint: "EXEC-2026-0702-002" },
    { label: "Failed / Blocked (24h)", value: "1 / 1", tone: "red" as const, hint: "see audit trail" },
    { label: "Last Dispatch Event", value: "00:13s ago", tone: "blue" as const, hint: "worker heartbeat" },
  ];
  return (
    <div className="border-b border-(--ss-hairline-strong) bg-[#050810]/60">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 divide-x divide-(--ss-hairline)">
        {items.map((it) => (
          <KpiCell
            key={it.label}
            label={it.label}
            value={it.value}
            tone={it.tone}
            hint={it.hint}
          />
        ))}
      </div>
    </div>
  );
}

// ============================================================
// ValidationOperationsMap — pipeline visualization
// ============================================================

interface PipelineNode {
  key: string;
  label: string;
  count: number;
  icon: React.ReactNode;
  tone: "slate" | "cyan" | "green" | "amber" | "red" | "blue";
  pulse?: boolean;
  sub?: string;
}

function PipelineNodeCard({ node, onClick }: { node: PipelineNode; onClick?: () => void }) {
  const toneMap = {
    slate: { ring: "border-slate-600/40", text: "text-slate-300", dot: "bg-slate-500", glow: "" },
    cyan: { ring: "border-cyan-500/50", text: "text-cyan-300", dot: "bg-cyan-400", glow: "ss-glow-cyan" },
    green: { ring: "border-emerald-500/50", text: "text-emerald-300", dot: "bg-emerald-400", glow: "ss-glow-green" },
    amber: { ring: "border-amber-500/50", text: "text-amber-300", dot: "bg-amber-400", glow: "ss-glow-amber" },
    red: { ring: "border-red-500/50", text: "text-red-300", dot: "bg-red-400", glow: "ss-glow-red" },
    blue: { ring: "border-blue-500/50", text: "text-blue-300", dot: "bg-blue-400", glow: "" },
  };
  const t = toneMap[node.tone];
  return (
    <button
      onClick={onClick}
      className={cn(
        "group relative w-full ss-panel border p-3 text-left transition-all hover:bg-(--ss-surface-3)/40",
        t.ring,
        node.pulse && t.glow
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div className={cn("w-7 h-7 rounded-sm border flex items-center justify-center", t.ring, "bg-(--ss-surface-2)")}>
          {node.icon}
        </div>
        <span className={cn("w-1.5 h-1.5 rounded-full", t.dot, node.pulse && "ss-pulse-cyan")} />
      </div>
      <div className="ss-eyebrow mb-0.5">{node.label}</div>
      <div className={cn("text-2xl font-semibold tnum leading-none", t.text)}>{node.count}</div>
      {node.sub && <div className="text-[10px] text-slate-500 mt-1">{node.sub}</div>}
    </button>
  );
}

function ValidationOperationsMap() {
  const go = useApp((s) => s.go);
  const openAsset = useApp((s) => s.openAsset);
  const openExecution = useApp((s) => s.openExecution);

  const assets = useApp((s) => s.assets);
  const authorizations = useApp((s) => s.authorizations);
  const engagements = useApp((s) => s.engagements);
  const executions = useApp((s) => s.executions);

  const verifiedAssets = assets.filter((a) => a.verification === "verified").length;
  const activeAuths = authorizations.filter((a) => a.state === "active").length;
  const activeEngagements = engagements.filter((e) => e.state === "active").length;
  const queued = executions.filter((e) => e.status === "queued").length;
  const executing = executions.filter((e) => e.status === "executing").length;
  const finished = executions.filter((e) => ["succeeded", "failed", "blocked", "cancelled"].includes(e.status)).length;

  const nodes: PipelineNode[] = [
    { key: "assets", label: "Verified Assets", count: verifiedAssets, tone: "green", icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />, sub: "ownership proven" },
    { key: "auths", label: "Active Authorizations", count: activeAuths, tone: "cyan", icon: <Shield className="w-3.5 h-3.5 text-cyan-400" />, sub: "scope-locked" },
    { key: "engagements", label: "Active Engagements", count: activeEngagements, tone: "cyan", icon: <Zap className="w-3.5 h-3.5 text-cyan-400" />, sub: "in window" },
    { key: "queued", label: "Queued Executions", count: queued, tone: "blue", icon: <Layers className="w-3.5 h-3.5 text-blue-400" />, sub: "awaiting worker" },
    { key: "executing", label: "Executing", count: executing, tone: "cyan", pulse: true, icon: <Activity className="w-3.5 h-3.5 text-cyan-300" />, sub: "live · eu-1" },
    { key: "finished", label: "Finished", count: finished, tone: "slate", icon: <Gauge className="w-3.5 h-3.5 text-slate-400" />, sub: "24h window" },
  ];

  return (
    <div className="ss-panel p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="ss-eyebrow mb-1">Validation Operations Map</div>
          <h2 className="text-sm font-semibold text-slate-100">
            Live pipeline · Organization → Project → Asset → Authorization → Engagement → Execution
          </h2>
        </div>
        <div className="hidden md:flex items-center gap-2">
          <Pill tone="green">
            <span className="w-1 h-1 rounded-full bg-emerald-400 ss-pulse-green" />
            Live
          </Pill>
          <span className="text-[10px] text-slate-500 ss-mono-xs">refresh · 5s</span>
        </div>
      </div>

      <div className="relative">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          {nodes.map((n, i) => (
            <React.Fragment key={n.key}>
              <PipelineNodeCard
                node={n}
                onClick={() => {
                  if (n.key === "assets") go("assets");
                  else if (n.key === "auths") go("authorizations");
                  else if (n.key === "engagements") go("engagements");
                  else if (n.key === "queued" || n.key === "executing" || n.key === "finished") go("execution_wizard");
                }}
              />
              {i < nodes.length - 1 && (
                <div
                  className="hidden lg:flex absolute items-center justify-center pointer-events-none"
                  style={{
                    left: `${((i + 1) / nodes.length) * 100}%`,
                    top: "50%",
                    transform: "translate(-50%, -50%)",
                  }}
                >
                  <ArrowRight className="w-3 h-3 text-cyan-500/50" />
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
        {/* connecting flow line */}
        <div className="hidden lg:block mt-3 h-px relative overflow-hidden">
          <div className="absolute inset-0 bg-(--ss-hairline)" />
          <div className="absolute inset-0 ss-flow-line opacity-60" />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1.5 text-[10px] text-slate-500">
        <div className="flex items-center gap-1.5">
          <span className="w-1 h-1 rounded-full bg-emerald-400" /> verified · ownership proven via DNS TXT
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1 h-1 rounded-full bg-cyan-400" /> active · within authorization window
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1 h-1 rounded-full bg-amber-400" /> armed · kill switch staged
        </div>
      </div>
    </div>
  );
}

// ============================================================
// ActivityRail — right-side live event rail
// ============================================================

function ActivityRail() {
  const openExecution = useApp((s) => s.openExecution);
  const openEngagement = useApp((s) => s.openEngagement);
  const executions = useApp((s) => s.executions);

  const events = [
    {
      id: "ar1",
      kind: "worker_started",
      tone: "cyan" as const,
      title: "Worker started",
      detail: "EXEC-2026-0702-002 · eu-1",
      at: "00:13s ago",
      target: "exec_002",
    },
    {
      id: "ar2",
      kind: "blocked_by_control",
      tone: "amber" as const,
      title: "Kill switch armed",
      detail: "ENG-CBV-001 · by r.varga",
      at: "3m ago",
      target: "eng_002",
    },
    {
      id: "ar3",
      kind: "worker_finished",
      tone: "green" as const,
      title: "Execution validated",
      detail: "EXEC-2026-0702-003 · 6/6 steps",
      at: "20m ago",
      target: "exec_003",
    },
    {
      id: "ar4",
      kind: "credential_revoked",
      tone: "slate" as const,
      title: "Credential revoked",
      detail: "EXEC-2026-0702-003 · execution_finished",
      at: "20m ago",
      target: "exec_003",
    },
    {
      id: "ar5",
      kind: "failed_safely",
      tone: "red" as const,
      title: "Execution failed safely",
      detail: "EXEC-2026-0701-014 · 2 missing headers",
      at: "8h ago",
      target: "exec_prev_1",
    },
    {
      id: "ar6",
      kind: "auth_expiry_warning",
      tone: "amber" as const,
      title: "Authorization expiry",
      detail: "AUTH-CBV-001 · expires in 3d",
      at: "1h ago",
    },
  ];

  const toneDot = {
    cyan: "bg-cyan-400",
    green: "bg-emerald-400",
    amber: "bg-amber-400",
    red: "bg-red-400",
    slate: "bg-slate-500",
  };

  return (
    <div className="ss-panel flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-(--ss-hairline-strong) flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Live Activity Rail</span>
        </div>
        <Pill tone="cyan">
          <span className="w-1 h-1 rounded-full bg-cyan-400 ss-pulse-cyan" />
          streaming
        </Pill>
      </div>
      <div className="flex-1 overflow-y-auto ss-scroll p-2">
        <ul className="space-y-1">
          {events.map((e) => (
            <li key={e.id}>
              <button
                onClick={() => {
                  if (e.target?.startsWith("exec_")) {
                    const exec = executions.find((x) => x.id === e.target);
                    if (exec) openExecution(exec.id);
                  } else if (e.target?.startsWith("eng_")) {
                    openEngagement(e.target);
                  }
                }}
                className="w-full text-left p-2 rounded-sm border border-transparent hover:border-(--ss-hairline-strong) hover:bg-(--ss-surface-3)/40 transition-colors"
              >
                <div className="flex items-start gap-2">
                  <span className={cn("mt-1 w-1.5 h-1.5 rounded-full shrink-0", toneDot[e.tone], e.tone === "cyan" && "ss-pulse-cyan")} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-medium text-slate-200 truncate">{e.title}</span>
                      <span className="ss-mono-xs text-slate-500 shrink-0">{e.at}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5 ss-mono-xs truncate">{e.detail}</div>
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="px-3 py-2 border-t border-(--ss-hairline-strong)">
        <button
          onClick={() => useApp.getState().go("audit")}
          className="text-[10px] uppercase tracking-wider text-cyan-300 hover:text-cyan-200"
        >
          View full audit stream →
        </button>
      </div>
    </div>
  );
}

// ============================================================
// ActiveExecutionFocus — large horizontal focus panel
// ============================================================

function ActiveExecutionFocus() {
  const openExecution = useApp((s) => s.openExecution);
  const requestKillSwitch = useApp((s) => s.requestKillSwitch);
  const executions = useApp((s) => s.executions);
  const exec = executions.find((e) => e.status === "executing");

  if (!exec) {
    return (
      <EmptyState
        eyebrow="Active Execution Focus"
        title="No execution currently running"
        description="Queued executions will appear here once a worker picks up the dispatch."
        icon={<Activity className="w-6 h-6" />}
      />
    );
  }

  return (
    <div className="ss-panel">
      <div className="px-4 py-2.5 border-b border-(--ss-hairline-strong) flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 ss-pulse-cyan" />
          <span className="text-xs font-semibold text-slate-100">Active Execution Focus</span>
          <span className="text-slate-700">·</span>
          <code className="ss-mono-xs text-cyan-200">{exec.code}</code>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={exec.status} />
          <RiskTierBadge tier={exec.riskTier} />
          <CyberButton size="sm" variant="ghost" onClick={() => openExecution(exec.id)}>
            Open detail →
          </CyberButton>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1.4fr_1fr] gap-0 divide-x divide-(--ss-hairline)">
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-0">
            <KeyValue k="Asset Target" v={<code className="ss-mono-xs text-cyan-200">{exec.assetTargetMasked}</code>} />
            <KeyValue k="Template" v={exec.templateName} />
            <KeyValue k="Engagement" v={exec.engagementCode} mono />
            <KeyValue k="Authorization" v={exec.authorizationCode} mono />
            <KeyValue k="Worker started" v={exec.workerStartedAt ?? "—"} mono />
            <KeyValue k="Last heartbeat" v={exec.dispatchMessage.lastHeartbeat} mono />
          </div>

          <ExecutionLifecycleRail
            status={exec.status}
            outcome={exec.outcome}
            timestamps={{
              queuedAt: exec.queuedAt,
              dispatchingAt: exec.dispatchingAt,
              workerStartedAt: exec.workerStartedAt,
              workerFinishedAt: exec.workerFinishedAt,
            }}
          />
        </div>

        <div className="p-4 space-y-3">
          <div>
            <div className="ss-eyebrow mb-1.5">Safety Snapshot</div>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { k: "Asset verified", v: exec.safetySnapshot.assetVerified },
                { k: "Authorization active", v: exec.safetySnapshot.authorizationActive },
                { k: "Engagement active", v: exec.safetySnapshot.engagementActive },
                { k: "Scope match", v: exec.safetySnapshot.scopeMatch },
                { k: "Window valid", v: exec.safetySnapshot.windowValid },
                { k: "Kill switch inactive", v: exec.safetySnapshot.killSwitchInactive },
                { k: "Risk tier allowed", v: exec.safetySnapshot.riskTierAllowed },
                { k: "Credential issued", v: exec.safetySnapshot.credentialIssued },
              ].map((row) => (
                <div
                  key={row.k}
                  className={cn(
                    "flex items-center gap-1.5 px-2 py-1 rounded-sm border text-[10px]",
                    row.v
                      ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
                      : "border-red-500/30 bg-red-500/5 text-red-300"
                  )}
                >
                  <span className={cn("w-1 h-1 rounded-full", row.v ? "bg-emerald-400" : "bg-red-400")} />
                  {row.k}
                </div>
              ))}
            </div>
          </div>

          <AlertBanner tone="warning" title="Kill switch armed on this engagement">
            Operator r.varga staged a manual hold. Activating will halt EXEC-2026-0702-002 and revoke its credential.
          </AlertBanner>

          <div className="flex items-center gap-2">
            <CyberButton
              size="sm"
              variant="amber"
              onClick={() => requestKillSwitch(exec.engagementId)}
            >
              <ShieldAlert className="w-3 h-3" />
              Activate kill switch
            </CyberButton>
            <CyberButton size="sm" variant="ghost" onClick={() => openExecution(exec.id)}>
              View evidence
            </CyberButton>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// BottomIntelligenceLayer — 3 panels of different shapes
// ============================================================

function RiskDistributionMatrix() {
  // simple matrix: rows = risk tiers, cols = outcome states
  const rows = ["critical", "high", "moderate", "low"] as const;
  const cols = ["validated", "failed_safely", "blocked_by_control", "inconclusive"] as const;
  const matrix: Record<string, Record<string, number>> = {
    critical: { validated: 0, failed_safely: 0, blocked_by_control: 0, inconclusive: 0 },
    high: { validated: 1, failed_safely: 0, blocked_by_control: 0, inconclusive: 0 },
    moderate: { validated: 0, failed_safely: 0, blocked_by_control: 0, inconclusive: 0 },
    low: { validated: 0, failed_safely: 1, blocked_by_control: 1, inconclusive: 0 },
  };
  return (
    <div className="ss-panel p-4">
      <SectionHeader
        eyebrow="Intelligence Layer"
        title="Risk Distribution Matrix"
        right={<Pill tone="slate">24h</Pill>}
      />
      <div className="overflow-hidden border border-(--ss-hairline) rounded-sm">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="bg-(--ss-surface-2)">
              <th className="text-left px-2 py-1.5 ss-eyebrow">Risk \ Outcome</th>
              {cols.map((c) => (
                <th key={c} className="px-2 py-1.5 ss-eyebrow text-center">{c.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r} className="border-t border-(--ss-hairline)">
                <td className="px-2 py-1.5 text-slate-300 capitalize">{r}</td>
                {cols.map((c) => {
                  const v = matrix[r][c];
                  const intensity =
                    c === "validated" ? "bg-emerald-500" :
                    c === "failed_safely" ? "bg-red-500" :
                    c === "blocked_by_control" ? "bg-amber-500" : "bg-yellow-500";
                  return (
                    <td key={c} className="px-2 py-1.5 text-center">
                      <div
                        className={cn(
                          "inline-flex items-center justify-center w-6 h-6 rounded-sm ss-mono-xs tnum",
                          v > 0 ? `${intensity} text-[#060912] font-semibold` : "text-slate-600 border border-(--ss-hairline)"
                        )}
                      >
                        {v > 0 ? v : "·"}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-[10px] text-slate-500">
        <span className="ss-mono-xs">2 executions</span> resolved in the last 24h across <span className="ss-mono-xs">3 risk tiers</span>.
      </div>
    </div>
  );
}

function AuthorizationExpiryRadar() {
  const authorizations = useApp((s) => s.authorizations);
  const items = authorizations
    .filter((a) => a.state === "active" || a.state === "draft")
    .map((a) => {
      const days = Math.max(
        0,
        Math.round((new Date(a.validUntil).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      );
      return { id: a.id, code: a.code, days, state: a.state };
    })
    .sort((x, y) => x.days - y.days);

  return (
    <div className="ss-panel p-4">
      <SectionHeader
        eyebrow="Intelligence Layer"
        title="Authorization Expiry Radar"
        right={<Pill tone="amber">3 active</Pill>}
      />
      <ul className="space-y-2">
        {items.map((it) => {
          const pct = Math.min(100, (it.days / 30) * 100);
          const tone =
            it.days <= 3 ? "bg-amber-500" : it.days <= 7 ? "bg-yellow-500" : "bg-emerald-500";
          return (
            <li key={it.id} className="space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="ss-mono-xs text-slate-300">{it.code}</span>
                <span className={cn(
                  "ss-mono-xs tnum",
                  it.days <= 3 ? "text-amber-300" : it.days <= 7 ? "text-yellow-300" : "text-emerald-300"
                )}>
                  {it.days}d remaining
                </span>
              </div>
              <div className="h-1 rounded-full bg-(--ss-surface-3) overflow-hidden">
                <div className={cn("h-full rounded-full", tone)} style={{ width: `${Math.max(8, pct)}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AssetVerificationQueue() {
  const assets = useApp((s) => s.assets);
  const queue = assets.filter((a) => a.verification === "pending" || a.verification === "failed");
  const openAsset = useApp((s) => s.openAsset);
  return (
    <div className="ss-panel p-4">
      <SectionHeader
        eyebrow="Intelligence Layer"
        title="Asset Verification Queue"
        right={<Pill tone="cyan">{queue.length} pending</Pill>}
      />
      {queue.length === 0 ? (
        <div className="text-[11px] text-slate-500 italic py-3 text-center">No assets awaiting verification.</div>
      ) : (
        <ul className="space-y-2">
          {queue.map((a) => (
            <li key={a.id}>
              <button
                onClick={() => openAsset(a.id)}
                className="w-full text-left p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[11px] font-medium text-slate-200 truncate">{a.name}</div>
                    <code className="ss-mono-xs text-slate-500 truncate block">{a.target}</code>
                  </div>
                  <Pill tone={a.verification === "pending" ? "amber" : "red"}>
                    {a.verification}
                  </Pill>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RecentAuditTrail() {
  const go = useApp((s) => s.go);
  const auditEvents = useApp((s) => s.auditEvents);
  const recent = auditEvents.slice(0, 5);
  return (
    <div className="ss-panel p-4">
      <SectionHeader
        eyebrow="Intelligence Layer"
        title="Recent Audit Trail"
        right={
          <button onClick={() => go("audit")} className="text-[10px] uppercase tracking-wider text-cyan-300 hover:text-cyan-200">
            Open audit →
          </button>
        }
      />
      <ul className="space-y-2.5">
        {recent.map((e) => {
          const time = new Date(e.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
          return (
            <li key={e.id} className="flex items-start gap-2 text-[11px]">
              <span className="ss-mono-xs text-slate-500 tnum shrink-0 w-16">{time}</span>
              <span className="text-slate-300 font-mono text-[10px]">{e.actor}</span>
              <span className="text-slate-500 truncate flex-1">{e.action}</span>
              <code className="ss-mono-xs text-cyan-300/80 shrink-0">{e.entityId}</code>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

import {
  AiProofOfRiskCommandStrip,
  DashboardQuickActions,
  AiProofOfRiskWorkflowRail,
  AiRoutingPipelinePanel,
  AttackSurfacePreviewPanel,
  DigitalTwinProofPanel,
  MultiAgentTribunalPanel,
  AuthorizedDomainScanPanel
} from "./DashboardAiPanels";

export function DashboardPage() {
  const workspaceWarning = useApp(s => s.workspaceWarning);
  const demoWorkspaceMode = useApp(s => s.demoWorkspaceMode);
  
  const showWarning = workspaceWarning || demoWorkspaceMode === "real_scan_standalone";
  const warningMessage = workspaceWarning || "Optional workspace context failed to load. Workspace seed data unavailable. Real authorized scan mode is still available.";

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen pb-12">
        <AiProofOfRiskCommandStrip />

        <div className="px-4 lg:px-6 py-4 space-y-4">
          {showWarning && (
            <AlertBanner tone="amber" title="Optional workspace context failed to load">
              {warningMessage}
            </AlertBanner>
          )}

          {/* ============================================================ */}
          {/* SECTION A: MANUAL BACKEND SECURITY VALIDATION                */}
          {/* ============================================================ */}
          <div className="mb-8 space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h2 className="text-lg font-semibold text-slate-100">Section A: Manual Backend Security Validation</h2>
              <Pill tone="green">Deterministic Backend</Pill>
            </div>
            
            <div className="grid lg:grid-cols-3 gap-4">
              <div className="lg:col-span-1 flex flex-col gap-4">
                <AuthorizedDomainScanPanel />
              </div>
              <div className="lg:col-span-2">
                <ValidationOperationsMap />
              </div>
            </div>

            <DispatchStatusStrip />

            <div className="grid lg:grid-cols-[1.85fr_1fr] gap-4">
              <ActiveExecutionFocus />
              <div className="min-h-[320px]">
                <ActivityRail />
              </div>
            </div>

            <div className="grid lg:grid-cols-12 gap-4">
              <div className="lg:col-span-5">
                <RiskDistributionMatrix />
              </div>
              <div className="lg:col-span-3">
                <AuthorizationExpiryRadar />
              </div>
              <div className="lg:col-span-4">
                <AssetVerificationQueue />
              </div>
            </div>

            <RecentAuditTrail />
          </div>

          <div className="h-px bg-(--ss-hairline-strong) my-8 relative">
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#050810] px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
              <ArrowRight className="w-4 h-4" /> AI Integration Boundary <ArrowRight className="w-4 h-4" />
            </div>
          </div>

          {/* ============================================================ */}
          {/* SECTION B: AI PROOF-OF-RISK INTELLIGENCE                     */}
          {/* ============================================================ */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <BrainCircuit className="w-5 h-5 text-cyan-400" />
              <h2 className="text-lg font-semibold text-slate-100">Section B: AI Proof-of-Risk Intelligence</h2>
              <Pill tone="cyan">Generative Intelligence</Pill>
            </div>

            <DashboardQuickActions />
            <AiProofOfRiskWorkflowRail />

            <div className="grid lg:grid-cols-4 gap-4">
              <AiRoutingPipelinePanel />
              <AttackSurfacePreviewPanel />
              <DigitalTwinProofPanel />
              <MultiAgentTribunalPanel />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
