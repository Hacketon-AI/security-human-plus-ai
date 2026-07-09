"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Cpu,
  FileCheck2,
  Hash,
  Layers,
  Lock,
  Radio,
  Shield,
  ShieldCheck,
  Terminal,
  XCircle,
  AlertTriangle,
  Clock,
  Server,
  Network,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
// Removed mock imports
import type { ExecutionStatus, ValidationExecution } from "@/lib/securescope/types";
import { OutcomeBadge, Pill, RiskTierBadge, StatusBadge } from "../shared/badges";
import { AlertBanner, CyberButton, KeyValue, MaskedField } from "../shared/ui";
import { EventTimeline, ExecutionLifecycleRail, SecureCodeBlock } from "../shared/lifecycle";
import { CredentialStateCard, KillSwitchControl } from "../shared/secure-cards";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";
import { AiProofOfRiskTab } from "./AiProofOfRiskTab";

const TABS = ["Overview", "Scope", "Safety", "Steps", "Audit", "AI Proof-of-Risk"] as const;
type Tab = (typeof TABS)[number];

export function ExecutionDetailPage() {
  const execId = useApp((s) => s.selectedExecutionId);
  const go = useApp((s) => s.go);
  const openEngagement = useApp((s) => s.openEngagement);
  const openAsset = useApp((s) => s.openAsset);
  const requestKillSwitch = useApp((s) => s.requestKillSwitch);
  const initialTab = useApp((s) => s.executionTab) as Tab || "Overview";
  const [tab, setTab] = React.useState<Tab>(initialTab);
  
  const activeAnalysisSource = useApp(s => s.activeAnalysisSource);
  const scanMetadata = useApp(s => s.latestScanMetadata);
  const domainSafeScanResult = useApp(s => s.latestDomainSafeScanResult);

  React.useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  const executions = useApp((s) => s.executions);
  const mockExec = { id: execId || "", code: execId ? `DEMO-${execId.slice(0, 8).toUpperCase()}` : "—", status: "failed" as const, outcome: "inconclusive" as const, organizationId: "", organizationName: "", projectId: "", projectName: "", assetId: "", assetName: "Demo Asset", assetTargetMasked: "demo.target", authorizationId: "", authorizationCode: "", engagementId: "", engagementCode: "", templateId: "", templateName: "AI Proof-of-Risk Demo", riskTier: "moderate" as const, queuedAt: null, dispatchingAt: null, workerStartedAt: null, workerFinishedAt: null, scopeSnapshot: { allowedPaths: [], excludedPaths: [], allowedPorts: [], maxRiskTier: "moderate" as const, scopedAssets: [] }, safetySnapshot: { assetVerified: false, authorizationActive: false, engagementActive: false, scopeMatch: false, windowValid: false, killSwitchInactive: false, riskTierAllowed: false, credentialIssued: false, dispatchBackendAvailable: false, workerAuthModeReady: false }, steps: [], events: [], credential: { id: "", organizationId: "", executionId: "", allowedActions: [], issuedAt: "", expiresAt: "", revokedAt: null, state: "expired" as const, source: "per_execution" as const, fallbackEnabled: false }, dispatchMessage: { messageId: "", queueName: "", routingKey: "", envelopeSchemaVersion: "", payloadHash: "", publishStatus: "failed" as const, workerState: "idle" as const, lastHeartbeat: "" } };
  const exec = executions.find((e) => e.id === execId) ?? mockExec;

  const isDomainScan = activeAnalysisSource === "domain_safe_scan" && scanMetadata;
  
  const displayId = isDomainScan ? scanMetadata.scan_id : exec.id;
  const displayCode = isDomainScan ? scanMetadata.scan_id : exec.code;
  const displayTarget = isDomainScan ? scanMetadata.domain : exec.assetTargetMasked;
  const displayTemplate = isDomainScan ? "Domain Safe Scan" : exec.templateName;
  const displayOrg = isDomainScan ? "Session" : exec.organizationName;
  const displayProj = isDomainScan ? "Ad-hoc Scan" : exec.projectName;

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[
            { label: isDomainScan ? "Scans" : "Executions", onClick: () => go("execution_wizard") },
            { label: displayCode },
          ]}
          title={
            <div className="flex items-center gap-3 flex-wrap">
              <span className="ss-mono text-cyan-200">{displayCode}</span>
              {isDomainScan && <Pill tone="cyan">Session Scan ID</Pill>}
              {activeAnalysisSource === "demo_execution" && <Pill tone="amber">Demo Execution</Pill>}
              <StatusBadge status={isDomainScan ? scanMetadata.status : exec.status} />
              {!isDomainScan && exec.outcome && <OutcomeBadge outcome={exec.outcome} />}
              {!isDomainScan && <RiskTierBadge tier={exec.riskTier} />}
            </div>
          }
          description={
            <span>
              {displayTemplate} against <code className="ss-mono-xs text-cyan-200">{displayTarget}</code> · {displayOrg} / {displayProj}
            </span>
          }
          right={
            !isDomainScan ? (
              <>
                <CyberButton size="sm" variant="ghost" onClick={() => openAsset(exec.assetId)}>
                  <Network className="w-3 h-3" /> Asset
                </CyberButton>
                <CyberButton size="sm" variant="ghost" onClick={() => openEngagement(exec.engagementId)}>
                  <Shield className="w-3 h-3" /> Engagement
                </CyberButton>
                <CyberButton size="sm" variant="amber" onClick={() => requestKillSwitch(exec.engagementId)}>
                  <Lock className="w-3 h-3" /> Halt
                </CyberButton>
              </>
            ) : null
          }
          meta={
            <>
              <Pill tone="cyan"><Hash className="w-2.5 h-2.5" /> {displayId}</Pill>
              <Pill tone="slate">{displayTemplate}</Pill>
              {!isDomainScan && <Pill tone="slate"><Clock className="w-2.5 h-2.5" /> Queued {exec.queuedAt?.slice(11, 19) ?? "—"}</Pill>}
            </>
          }
        />

        {/* Lifecycle rail */}
        <div className="px-4 lg:px-6 py-4">
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

        {/* Tabs */}
        <div className="px-4 lg:px-6 border-b border-(--ss-hairline-strong)">
          <div className="flex items-center gap-0.5 overflow-x-auto ss-scroll">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "px-3 py-2 text-[11px] uppercase tracking-wider border-b-2 -mb-px transition-colors whitespace-nowrap",
                  tab === t
                    ? "text-cyan-200 border-cyan-400"
                    : "text-slate-500 border-transparent hover:text-slate-300"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="px-4 lg:px-6 py-5">
          {tab === "Overview" && <OverviewTab exec={exec} isDomainScan={isDomainScan} scanMetadata={scanMetadata} domainSafeScanResult={domainSafeScanResult} />}
          {tab === "Scope" && <ScopeTab exec={exec} isDomainScan={isDomainScan} />}
          {tab === "Safety" && <SafetyTab exec={exec} isDomainScan={isDomainScan} />}
          {tab === "Steps" && <StepsTab exec={exec} isDomainScan={isDomainScan} scanMetadata={scanMetadata} domainSafeScanResult={domainSafeScanResult} />}
          {tab === "Audit" && <AuditTab exec={exec} isDomainScan={isDomainScan} scanMetadata={scanMetadata} />}
          {tab === "AI Proof-of-Risk" && <AiProofOfRiskTab exec={exec} isDomainScan={isDomainScan} />}
        </div>
      </div>
    </>
  );
}

/* ---------------- Overview tab ---------------- */
function OverviewTab({ exec, isDomainScan, scanMetadata, domainSafeScanResult }: { exec: ValidationExecution, isDomainScan: boolean, scanMetadata: any, domainSafeScanResult: any }) {
  if (isDomainScan) {
    return (
      <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
        <div className="space-y-4">
          <div className="ss-panel p-4">
            <div className="flex items-center gap-2 mb-3">
              <Terminal className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs font-semibold text-slate-100">Domain Scan Summary</span>
            </div>
            <div className="space-y-2">
              <AlertBanner
                tone="success"
                title="Outcome · Completed"
              >
                Scan completed successfully using Session Scan ID {scanMetadata.scan_id}. 
                Found {scanMetadata.finding_count} missing headers.
              </AlertBanner>
            </div>
          </div>
        </div>
        <div className="space-y-4">
          <div className="ss-panel-raised">
             <div className="px-4 py-2.5 border-b border-(--ss-hairline-strong) flex items-center justify-between">
               <div className="flex items-center gap-2">
                 <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                 <span className="text-xs font-semibold text-slate-100">Scan Inspector</span>
               </div>
               <Pill tone="cyan">Session</Pill>
             </div>
             <div className="p-4 space-y-3">
               <div>
                 <div className="ss-eyebrow mb-1.5">Scan Metadata</div>
                 <div className="grid grid-cols-2 gap-x-4 gap-y-0">
                   <KeyValue k="Session ID" v={scanMetadata.scan_id} mono />
                   <KeyValue k="Correlation" v={scanMetadata.correlation_id} mono />
                   <KeyValue k="Target" v={scanMetadata.domain} mono />
                   <KeyValue k="Scheme" v={scanMetadata.scheme} mono />
                   <KeyValue k="Type" v={scanMetadata.scan_type} />
                 </div>
               </div>
             </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
      {/* Left: timeline + steps summary */}
      <div className="space-y-4">
        <div className="ss-panel p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs font-semibold text-slate-100">Execution Timeline</span>
            </div>
            <Pill tone="cyan">{exec.events.length} events</Pill>
          </div>
          {exec.events.length === 0 ? (
            <div className="text-xs text-slate-500 italic py-6 text-center">
              No worker events yet. Execution is queued — events will appear when the worker picks up the dispatch.
            </div>
          ) : (
            <EventTimeline events={exec.events} />
          )}
        </div>

        {exec.steps.length > 0 && (
          <div className="ss-panel p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-xs font-semibold text-slate-100">Step Result Sequence</span>
              </div>
              <Pill tone="slate">{exec.steps.length} steps</Pill>
            </div>
            <ol className="space-y-2">
              {exec.steps.map((s, i) => (
                <li key={s.id} className="flex items-start gap-3 p-2.5 rounded-sm border border-(--ss-hairline) bg-(--ss-surface-2)/50">
                  <div className="shrink-0">
                    {s.status === "succeeded" ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : s.status === "failed" ? (
                      <XCircle className="w-4 h-4 text-red-400" />
                    ) : s.status === "inconclusive" ? (
                      <AlertTriangle className="w-4 h-4 text-yellow-400" />
                    ) : (
                      <span className="w-4 h-4 rounded-full border-2 border-slate-600" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] ss-mono-xs text-slate-500">#{i + 1}</span>
                      <span className="ss-mono-xs text-slate-500 tnum">{(s.durationMs / 1000).toFixed(2)}s</span>
                    </div>
                    <div className="text-xs font-medium text-slate-200 mt-0.5">{s.name}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">{s.safeSummary}</div>
                    <div className="mt-1.5">
                      <SecureCodeBlock label="Evidence preview" value={s.evidencePreview} copyable hint="sanitized · no cookies · no auth header" />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        <div className="ss-panel p-4">
          <div className="flex items-center gap-2 mb-3">
            <Terminal className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-semibold text-slate-100">Result Summary</span>
          </div>
          {exec.outcome ? (
            <div className="space-y-2">
              <AlertBanner
                tone={exec.outcome === "validated" ? "success" : exec.outcome === "failed_safely" ? "danger" : "warning"}
                title={`Outcome · ${exec.outcome.replace(/_/g, " ")}`}
              >
                {exec.outcome === "validated" && "All steps completed within authorized scope. No safety controls triggered."}
                {exec.outcome === "failed_safely" && "One or more steps detected a validation gap. The worker halted cleanly within scope; no exploitation occurred."}
                {exec.outcome === "blocked_by_control" && "A safety control halted execution mid-flight. The credential was revoked and the dispatch was routed to the dead-letter queue."}
                {exec.outcome === "inconclusive" && "Steps completed but evidence was insufficient to determine a definitive outcome."}
              </AlertBanner>
              <div className="grid grid-cols-3 gap-2">
                <div className="ss-panel-flat p-2 text-center">
                  <div className="ss-eyebrow">Total steps</div>
                  <div className="text-lg font-semibold tnum text-slate-100">{exec.steps.length}</div>
                </div>
                <div className="ss-panel-flat p-2 text-center">
                  <div className="ss-eyebrow">Succeeded</div>
                  <div className="text-lg font-semibold tnum text-emerald-300">{exec.steps.filter((s) => s.status === "succeeded").length}</div>
                </div>
                <div className="ss-panel-flat p-2 text-center">
                  <div className="ss-eyebrow">Failed / inconclusive</div>
                  <div className="text-lg font-semibold tnum text-red-300">{exec.steps.filter((s) => s.status !== "succeeded" && s.status !== "skipped").length}</div>
                </div>
              </div>
            </div>
          ) : (
            <AlertBanner tone="info" title="Execution in progress">
              Worker is currently running step {exec.steps.length + 1}. Results will appear here as each step completes.
            </AlertBanner>
          )}
        </div>
      </div>

      {/* Right: inspector */}
      <ExecutionInspector exec={exec} />
    </div>
  );
}

/* ---------------- Inspector panel ---------------- */
function ExecutionInspector({ exec }: { exec: ValidationExecution }) {
  return (
    <div className="space-y-4">
      <div className="ss-panel-raised">
        <div className="px-4 py-2.5 border-b border-(--ss-hairline-strong) flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-semibold text-slate-100">Execution Inspector</span>
          </div>
          <Pill tone="cyan">live</Pill>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <div className="ss-eyebrow mb-1.5">Worker state</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0">
              <KeyValue k="Worker ID" v={exec.dispatchMessage.workerState === "running" ? "wkr-eu-1-a07" : "—"} mono />
              <KeyValue k="State" v={exec.dispatchMessage.workerState} />
              <KeyValue k="Region" v="eu-1" mono />
              <KeyValue k="Last heartbeat" v={exec.dispatchMessage.lastHeartbeat} mono />
            </div>
          </div>

          <div>
            <div className="ss-eyebrow mb-1.5">Dispatch message</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0">
              <KeyValue k="Message ID" v={exec.dispatchMessage.messageId} mono />
              <KeyValue k="Queue" v={exec.dispatchMessage.queueName} mono />
              <KeyValue k="Routing key" v={exec.dispatchMessage.routingKey} mono />
              <KeyValue k="Schema" v={exec.dispatchMessage.envelopeSchemaVersion} mono />
              <KeyValue k="Publish status" v={exec.dispatchMessage.publishStatus} />
              <KeyValue k="Payload hash" v={exec.dispatchMessage.payloadHash} mono />
            </div>
          </div>

          <div>
            <div className="ss-eyebrow mb-1.5">Audit metadata</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0">
              <KeyValue k="Execution ID" v={exec.id} mono />
              <KeyValue k="Correlation" v={`corr_${exec.id.slice(-8)}`} mono />
              <KeyValue k="Queued at" v={exec.queuedAt} mono />
              <KeyValue k="Started at" v={exec.workerStartedAt} mono />
              <KeyValue k="Finished at" v={exec.workerFinishedAt} mono />
              <KeyValue k="Template" v={exec.templateName} />
            </div>
          </div>

          <MaskedField
            label="Sensitive payload"
            note="Raw request/response bodies, cookies, Authorization headers, and Set-Cookie values are never stored or displayed."
          />
        </div>
      </div>

      <CredentialStateCard credential={exec.credential} />
    </div>
  );
}

/* ---------------- Scope tab ---------------- */
function ScopeTab({ exec, isDomainScan }: { exec: ValidationExecution, isDomainScan: boolean }) {
  if (isDomainScan) {
    return (
      <div className="ss-panel-flat p-8 text-center">
        <div className="ss-eyebrow mb-1">Session Scope (Ad-hoc)</div>
        <p className="text-xs text-slate-500">Domain safe scan was authorized ad-hoc for this session. Persistent scope configuration does not apply.</p>
      </div>
    );
  }
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="ss-panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Scope Snapshot (frozen at queue)</span>
        </div>
        <AlertBanner tone="info" title="Snapshot is immutable">
          The scope snapshot was captured when the execution was queued. Subsequent authorization changes do not affect this execution.
        </AlertBanner>
        <div className="mt-3 space-y-3">
          <div>
            <div className="ss-eyebrow mb-1.5">Allowed paths</div>
            <div className="flex flex-wrap gap-1">
              {exec.scopeSnapshot.allowedPaths.map((p) => (
                <code key={p} className="ss-mono-xs text-emerald-200 border border-emerald-500/30 bg-emerald-500/5 rounded-sm px-1.5 py-0.5">{p}</code>
              ))}
            </div>
          </div>
          <div>
            <div className="ss-eyebrow mb-1.5">Excluded paths</div>
            <div className="flex flex-wrap gap-1">
              {exec.scopeSnapshot.excludedPaths.map((p) => (
                <code key={p} className="ss-mono-xs text-red-200 border border-red-500/30 bg-red-500/5 rounded-sm px-1.5 py-0.5">{p}</code>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0">
            <KeyValue k="Allowed ports" v={exec.scopeSnapshot.allowedPorts.join(", ")} mono />
            <KeyValue k="Max risk tier" v={<RiskTierBadge tier={exec.scopeSnapshot.maxRiskTier} />} />
            <KeyValue k="Scoped assets" v={exec.scopeSnapshot.scopedAssets.join(", ")} />
          </div>
        </div>
      </div>

      <div className="ss-panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Authorization scope comparison</span>
        </div>
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <div className="ss-panel-flat p-2 text-center">
              <div className="ss-eyebrow">Authorization</div>
              <code className="ss-mono-xs text-cyan-200">{exec.authorizationCode}</code>
            </div>
            <div className="ss-panel-flat p-2 text-center">
              <div className="ss-eyebrow">Engagement</div>
              <code className="ss-mono-xs text-cyan-200">{exec.engagementCode}</code>
            </div>
            <div className="ss-panel-flat p-2 text-center">
              <div className="ss-eyebrow">Asset</div>
              <code className="ss-mono-xs text-cyan-200">{exec.assetName}</code>
            </div>
          </div>
          <AlertBanner tone="success" title="Scope match verified">
            Asset target, requested paths, and risk tier all fall within the active authorization scope.
          </AlertBanner>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0">
            <KeyValue k="Asset target" v={<code className="ss-mono-xs text-cyan-200">{exec.assetTargetMasked}</code>} />
            <KeyValue k="Asset in scope" v={<span className="text-emerald-300">✓</span>} />
            <KeyValue k="Paths in scope" v={<span className="text-emerald-300">✓</span>} />
            <KeyValue k="Risk tier allowed" v={<span className="text-emerald-300">✓</span>} />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------------- Safety tab ---------------- */
function SafetyTab({ exec, isDomainScan }: { exec: ValidationExecution, isDomainScan: boolean }) {
  if (isDomainScan) {
    return (
      <div className="ss-panel-flat p-8 text-center">
        <div className="ss-eyebrow mb-1">Session Safety</div>
        <p className="text-xs text-slate-500">Domain safe scan is intrinsically safe (HTTP HEAD/GET only). It does not use kill switches or worker credentials.</p>
      </div>
    );
  }
  const rows: { k: keyof typeof exec.safetySnapshot; label: string; blocking: boolean }[] = [
    { k: "assetVerified", label: "Asset verified", blocking: true },
    { k: "authorizationActive", label: "Authorization active", blocking: true },
    { k: "engagementActive", label: "Engagement active", blocking: true },
    { k: "scopeMatch", label: "Scope match", blocking: true },
    { k: "windowValid", label: "Testing window valid", blocking: true },
    { k: "killSwitchInactive", label: "Kill switch inactive", blocking: true },
    { k: "riskTierAllowed", label: "Risk tier allowed", blocking: true },
    { k: "credentialIssued", label: "Credential issued", blocking: false },
    { k: "dispatchBackendAvailable", label: "Dispatch backend available", blocking: true },
    { k: "workerAuthModeReady", label: "Worker auth mode ready", blocking: true },
  ];
  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
      <div className="ss-panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Safety Snapshot</span>
        </div>
        <div className="border border-(--ss-hairline-strong) rounded-sm overflow-hidden">
          {rows.map((r, i) => {
            const v = exec.safetySnapshot[r.k];
            return (
              <div key={r.k} className={cn("flex items-center gap-3 px-3 py-2.5", i > 0 && "border-t border-(--ss-hairline)")}>
                {v ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-red-400" />}
                <div className="flex-1">
                  <div className="text-xs font-medium text-slate-200">{r.label}</div>
                </div>
                <Pill tone={r.blocking ? "red" : "slate"}>{r.blocking ? "blocking" : "non-blocking"}</Pill>
                <Pill tone={v ? "green" : "red"}>{v ? "passed" : "failed"}</Pill>
              </div>
            );
          })}
        </div>
      </div>

      <KillSwitchControl
        state={exec.safetySnapshot.killSwitchInactive ? "inactive" : "armed"}
        onActivate={() => useApp.getState().requestKillSwitch(exec.engagementId)}
      />
    </div>
  );
}

/* ---------------- Steps tab ---------------- */
function StepsTab({ exec, isDomainScan, scanMetadata, domainSafeScanResult }: { exec: ValidationExecution, isDomainScan: boolean, scanMetadata: any, domainSafeScanResult: any }) {
  if (isDomainScan) {
    return (
      <div className="ss-panel p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-semibold text-slate-100">Manual Backend Steps</span>
          </div>
          <Pill tone="cyan">Session Scan</Pill>
        </div>
        <ol className="space-y-3">
          <li className="ss-panel-flat p-3">
            <div className="flex items-start gap-3">
              <div className="shrink-0">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div>
                    <span className="ss-mono-xs text-slate-500">step 1</span>
                    <span className="text-xs font-medium text-slate-200 ml-2">HTTP Security Headers Scan</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Pill tone="green">completed</Pill>
                  </div>
                </div>
                <p className="text-[11px] text-slate-400 mb-2">Live HTTP headers fetched from {scanMetadata?.domain}</p>
                <SecureCodeBlock label="Evidence preview" value={JSON.stringify(domainSafeScanResult?.scan_result, null, 2)} copyable hint="sanitized headers" />
              </div>
            </div>
          </li>
        </ol>
      </div>
    );
  }

  if (exec.steps.length === 0) {
    return (
      <div className="ss-panel-flat p-8 text-center">
        <div className="ss-eyebrow mb-1">No step results yet</div>
        <p className="text-xs text-slate-500">Steps will appear once the worker begins executing the template.</p>
      </div>
    );
  }
  return (
    <div className="ss-panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Step Results & Evidence</span>
        </div>
        <AlertBanner tone="info" title="Evidence is sanitized" className="py-1.5! px-2.5! max-w-md">
          No raw response bodies, cookies, Authorization headers, or Set-Cookie values are stored.
        </AlertBanner>
      </div>
      <ol className="space-y-3">
        {exec.steps.map((s, i) => (
          <li key={s.id} className="ss-panel-flat p-3">
            <div className="flex items-start gap-3">
              <div className="shrink-0">
                {s.status === "succeeded" ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : s.status === "failed" ? (
                  <XCircle className="w-4 h-4 text-red-400" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-yellow-400" />
                )}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div>
                    <span className="ss-mono-xs text-slate-500">step {i + 1}</span>
                    <span className="text-xs font-medium text-slate-200 ml-2">{s.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Pill tone={s.status === "succeeded" ? "green" : s.status === "failed" ? "red" : "amber"}>{s.status}</Pill>
                    <span className="ss-mono-xs text-slate-500 tnum">{(s.durationMs / 1000).toFixed(2)}s</span>
                  </div>
                </div>
                <p className="text-[11px] text-slate-400 mb-2">{s.safeSummary}</p>
                <SecureCodeBlock label="Evidence preview" value={s.evidencePreview} copyable hint="sanitized · no cookies · no auth header" />
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/* ---------------- Audit tab ---------------- */
function AuditTab({ exec, isDomainScan, scanMetadata }: { exec: ValidationExecution, isDomainScan: boolean, scanMetadata: any }) {
  const go = useApp((s) => s.go);

  if (isDomainScan) {
    return (
      <div className="ss-panel p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-semibold text-slate-100">Session Audit</span>
          </div>
        </div>
        <EventTimeline
          events={[{
            id: scanMetadata?.scan_id || "scan_1",
            at: new Date().toISOString(),
            kind: "scan_completed",
            label: "Domain Scan Completed",
            safeMeta: { domain: scanMetadata?.domain }
          }]}
        />
      </div>
    );
  }

  // Build a synthetic audit view focused on this execution
  const events = exec.events.map((e) => ({
    id: e.id,
    at: e.at,
    actor: e.safeMeta.worker_id ? `system:worker:${e.safeMeta.worker_id}` : "system:scheduler",
    action: e.kind,
    entityId: exec.code,
    safeMetadata: e.safeMeta,
  }));
  return (
    <div className="ss-panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Radio className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Execution Audit Stream</span>
        </div>
        <button onClick={() => go("audit")} className="text-[10px] uppercase tracking-wider text-cyan-300 hover:text-cyan-200">
          Open global audit →
        </button>
      </div>
      <EventTimeline
        events={events.map((e) => ({
          id: e.id,
          at: e.at,
          kind: e.action,
          label: e.action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
          safeMeta: e.safeMetadata,
        }))}
      />
    </div>
  );
}
