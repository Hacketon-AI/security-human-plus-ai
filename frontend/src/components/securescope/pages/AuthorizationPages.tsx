"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  FileText,
  Lock,
  Plus,
  Shield,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
// Removed mock imports
import { AuthorizationStateBadge, Pill, RiskTierBadge } from "../shared/badges";
import { AlertBanner, CyberButton, EmptyState, KeyValue } from "../shared/ui";
import { EventTimeline } from "../shared/lifecycle";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

export function AuthorizationsListPage() {
  const openAuthorization = useApp((s) => s.openAuthorization);
  const authorizations = useApp((s) => s.authorizations);
  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Authorizations" }]}
          title="Authorizations"
          description="Authorizations define scope (allowed/excluded paths, ports, hosts), max risk tier, and the validity window. Active authorizations carry an immutable lock."
          right={<CyberButton size="sm" variant="primary"><Plus className="w-3 h-3" /> Request authorization</CyberButton>}
        />
        <div className="px-4 lg:px-6 py-4">
          <div className="ss-panel overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[var(--ss-surface-2)] border-b border-[var(--ss-hairline-strong)]">
                  <th className="text-left px-3 py-2 ss-eyebrow">Code</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">State</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Organization</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Project</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Max risk</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Valid window</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Scoped assets</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Lock</th>
                  <th className="text-left px-3 py-2 ss-eyebrow"></th>
                </tr>
              </thead>
              <tbody>
                {authorizations.map((a) => (
                  <tr key={a.id} onClick={() => openAuthorization(a.id)} className="border-b border-[var(--ss-hairline)] hover:bg-[var(--ss-surface-3)]/40 cursor-pointer">
                    <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{a.code}</code></td>
                    <td className="px-3 py-2.5"><AuthorizationStateBadge state={a.state} /></td>
                    <td className="px-3 py-2.5 text-slate-300">{a.organizationName}</td>
                    <td className="px-3 py-2.5 text-slate-400">{a.projectName}</td>
                    <td className="px-3 py-2.5"><RiskTierBadge tier={a.maxRiskTier} /></td>
                    <td className="px-3 py-2.5 ss-mono-xs text-slate-400">{a.validFrom.slice(0,10)} → {a.validUntil.slice(0,10)}</td>
                    <td className="px-3 py-2.5 text-slate-300 tnum">{a.scopedAssetNames.length}</td>
                    <td className="px-3 py-2.5">
                      {a.immutableLock ? (
                        <Pill tone="green"><Lock className="w-2.5 h-2.5" /> locked</Pill>
                      ) : (
                        <Pill tone="slate">unlocked</Pill>
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

export function AuthorizationDetailPage() {
  const authId = useApp((s) => s.selectedAuthorizationId);
  const go = useApp((s) => s.go);
  const authorizations = useApp((s) => s.authorizations);
  const auth = authorizations.find((a) => a.id === authId) ?? { id: "", code: "—", organizationId: "", organizationName: "", projectId: "", projectName: "", state: "draft", validFrom: "", validUntil: "", maxRiskTier: "moderate", scopedAssets: [], scopedAssetNames: [], scope: { allowedPaths: [], excludedPaths: [], allowedPorts: [], allowedHosts: [] }, supportingDoc: { name: "", hash: "", signedBy: "", signedAt: "" }, approvalTimeline: [], immutableLock: false };

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        {/* Status banner */}
        <div className={cn(
          "px-4 lg:px-6 pt-4 pb-3 border-b",
          auth.state === "active"
            ? "border-emerald-500/30 bg-emerald-500/5"
            : auth.state === "expired"
            ? "border-slate-600/30 bg-slate-500/5"
            : auth.state === "blocked"
            ? "border-red-500/30 bg-red-500/5"
            : "border-[var(--ss-hairline-strong)] bg-[var(--ss-surface-2)]/30"
        )}>
          <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-2">
            <button onClick={() => go("authorizations")} className="hover:text-slate-300 uppercase tracking-wider">Authorizations</button>
            <span className="text-slate-700">/</span>
            <span className="uppercase tracking-wider">{auth.code}</span>
          </div>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-start gap-4 min-w-0 flex-1">
              <div className={cn(
                "w-12 h-12 rounded-sm border flex items-center justify-center shrink-0",
                auth.state === "active" ? "border-emerald-400/40 bg-emerald-500/10 ss-glow-green" : "border-cyan-400/30 bg-cyan-500/5"
              )}>
                <Shield className={cn("w-5 h-5", auth.state === "active" ? "text-emerald-300" : "text-cyan-300")} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-xl lg:text-2xl font-semibold tracking-tight text-slate-100">
                    <code className="ss-mono text-cyan-200">{auth.code}</code>
                  </h1>
                  <AuthorizationStateBadge state={auth.state} />
                  <RiskTierBadge tier={auth.maxRiskTier} />
                  {auth.immutableLock && (
                    <Pill tone="green"><Lock className="w-2.5 h-2.5" /> Immutable active lock</Pill>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {auth.organizationName} · {auth.projectName} · {auth.scopedAssetNames.length} scoped asset(s)
                </p>
                <p className="text-[11px] text-slate-500 mt-1 ss-mono-xs">
                  Valid: {auth.validFrom.replace("T", " ").slice(0, 16)} → {auth.validUntil.replace("T", " ").slice(0, 16)} UTC
                </p>
              </div>
            </div>
            <div className="shrink-0 flex items-center gap-2">
              <CyberButton size="sm" variant="ghost">Export scope</CyberButton>
              {!auth.immutableLock && (
                <CyberButton size="sm" variant="primary">Submit for approval</CyberButton>
              )}
            </div>
          </div>

          {/* Active lock ribbon */}
          {auth.immutableLock && auth.state === "active" && (
            <div className="mt-3 flex items-center gap-2 px-3 py-2 border border-emerald-500/30 bg-emerald-500/5 rounded-sm">
              <Lock className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[11px] text-emerald-200">
                Active lock engaged. Scope, paths, ports, and risk tier cannot be modified while this authorization is active.
              </span>
            </div>
          )}
        </div>

        <div className="px-4 lg:px-6 py-5">
          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
            {/* Left: scope matrix + policy summary */}
            <div className="space-y-4">
              {/* Scope matrix */}
              <div className="ss-panel p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-100">Scope Matrix</span>
                  </div>
                  <Pill tone="cyan">{auth.scope.allowedPaths.length} allowed · {auth.scope.excludedPaths.length} excluded</Pill>
                </div>

                <div className="grid md:grid-cols-2 gap-3">
                  <div>
                    <div className="ss-eyebrow mb-1.5 flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-emerald-400" /> Allowed paths</div>
                    <div className="space-y-1">
                      {auth.scope.allowedPaths.map((p) => (
                        <code key={p} className="block ss-mono-xs text-emerald-200 border border-emerald-500/30 bg-emerald-500/5 rounded-sm px-2 py-1">{p}</code>
                      ))}
                    </div>
                    <div className="ss-eyebrow mt-3 mb-1.5 flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-emerald-400" /> Allowed ports</div>
                    <div className="flex flex-wrap gap-1">
                      {auth.scope.allowedPorts.map((p) => (
                        <code key={p} className="ss-mono-xs text-emerald-200 border border-emerald-500/30 bg-emerald-500/5 rounded-sm px-2 py-0.5">{p}</code>
                      ))}
                    </div>
                    <div className="ss-eyebrow mt-3 mb-1.5 flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-emerald-400" /> Allowed hosts</div>
                    <div className="space-y-1">
                      {auth.scope.allowedHosts.map((h) => (
                        <code key={h} className="block ss-mono-xs text-emerald-200 border border-emerald-500/30 bg-emerald-500/5 rounded-sm px-2 py-1">{h}</code>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="ss-eyebrow mb-1.5 flex items-center gap-1.5"><XCircle className="w-3 h-3 text-red-400" /> Excluded paths</div>
                    <div className="space-y-1">
                      {auth.scope.excludedPaths.map((p) => (
                        <code key={p} className="block ss-mono-xs text-red-200 border border-red-500/30 bg-red-500/5 rounded-sm px-2 py-1">{p}</code>
                      ))}
                      {auth.scope.excludedPaths.length === 0 && (
                        <div className="text-[11px] text-slate-500 italic">None</div>
                      )}
                    </div>
                    <div className="ss-eyebrow mt-3 mb-1.5">Scoped assets</div>
                    <div className="space-y-1">
                      {auth.scopedAssetNames.map((a) => (
                        <div key={a} className="text-[11px] text-slate-200 border border-[var(--ss-hairline)] rounded-sm px-2 py-1">{a}</div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Policy summary */}
              <div className="ss-panel p-4">
                <div className="ss-eyebrow mb-2">Policy summary</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-0">
                  <KeyValue k="State" v={<AuthorizationStateBadge state={auth.state} />} />
                  <KeyValue k="Max risk tier" v={<RiskTierBadge tier={auth.maxRiskTier} />} />
                  <KeyValue k="Valid from" v={auth.validFrom.replace("T", " ").slice(0, 16)} mono />
                  <KeyValue k="Valid until" v={auth.validUntil.replace("T", " ").slice(0, 16)} mono />
                  <KeyValue k="Immutable lock" v={auth.immutableLock ? "Engaged" : "Not engaged"} />
                  <KeyValue k="Scoped assets" v={auth.scopedAssetNames.length} mono />
                </div>
              </div>
            </div>

            {/* Right: lifecycle rail + doc metadata */}
            <div className="space-y-4">
              {/* Lifecycle rail */}
              <div className="ss-panel-flat p-4">
                <div className="ss-eyebrow mb-3">Authorization lifecycle</div>
                <div className="relative">
                  <div className="absolute left-[5px] top-1 bottom-1 w-px bg-[var(--ss-hairline-strong)]" />
                  <ul className="space-y-3">
                    {auth.approvalTimeline.map((t, i) => {
                      const isLast = i === auth.approvalTimeline.length - 1;
                      return (
                        <li key={i} className="relative pl-6">
                          <span className={cn(
                            "absolute left-0 top-1 w-[11px] h-[11px] rounded-full border-2 border-[#0A111E]",
                            isLast && auth.state === "active" ? "bg-emerald-400" : "bg-cyan-400"
                          )} />
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="text-xs font-medium text-slate-200 capitalize">{t.action}</span>
                            <span className="ss-mono-xs text-slate-500">{new Date(t.at).toLocaleString("en-GB", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                          </div>
                          <div className="text-[10px] text-slate-500 ss-mono-xs">{t.actor}</div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              </div>

              {/* Document metadata */}
              <div className="ss-panel p-4">
                <div className="flex items-center gap-2 mb-2">
                  <FileText className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Supporting documentation</span>
                </div>
                <div className="grid grid-cols-1 gap-y-0">
                  <KeyValue k="Document" v={auth.supportingDoc.name} />
                  <KeyValue k="Hash" v={<code className="ss-mono-xs text-cyan-200">{auth.supportingDoc.hash}</code>} />
                  <KeyValue k="Signed by" v={auth.supportingDoc.signedBy} />
                  <KeyValue k="Signed at" v={auth.supportingDoc.signedAt} mono />
                </div>
                {auth.state === "draft" && (
                  <AlertBanner tone="warning" title="Awaiting signature" className="mt-3">
                    This authorization is in draft state. It must be signed and approved before activation.
                  </AlertBanner>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
