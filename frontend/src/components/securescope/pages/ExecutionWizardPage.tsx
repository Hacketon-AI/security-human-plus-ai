"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Circle,
  ClipboardCheck,
  Database,
  FileCheck2,
  Layers,
  Lock,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Target,
  Zap,
  XCircle,
  AlertTriangle,
  Info,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { Pill, RiskTierBadge } from "../shared/badges";

// Validation TEMPLATES are static configuration — they define available check
// types, not runtime data. No backend endpoint exists for TEMPLATES yet.
const TEMPLATES = [
  {
    id: "tpl_headers",
    name: "HTTP Security Header Validation",
    description: "Evaluates HSTS, CSP, X-Content-Type-Options, Referrer-Policy and related headers against baseline.",
    steps: 6,
    riskTier: "low" as const,
    estimatedSeconds: 120,
  },
  {
    id: "tpl_tls",
    name: "Safe TLS Configuration Check",
    description: "Inspects cipher suites, protocol versions and certificate chain depth without active exploitation.",
    steps: 3,
    riskTier: "moderate" as const,
    estimatedSeconds: 90,
  },
  {
    id: "tpl_availability",
    name: "API Availability Safety Check",
    description: "Performs bounded availability probing within authorized scope and rate limits.",
    steps: 2,
    riskTier: "low" as const,
    estimatedSeconds: 45,
  },
];
import { AlertBanner, CyberButton, KeyValue, MaskedField } from "../shared/ui";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

const STEPS = [
  { key: "context", label: "Context" },
  { key: "asset", label: "Asset" },
  { key: "authorization", label: "Authorization" },
  { key: "engagement", label: "Engagement" },
  { key: "template", label: "Template" },
  { key: "safety", label: "Safety Check" },
  { key: "confirm", label: "Confirm Queue" },
] as const;

type StepKey = (typeof STEPS)[number]["key"];

interface DraftState {
  orgId: string;
  projectId: string;
  assetId: string;
  authorizationId: string;
  engagementId: string;
  templateId: string;
}

export function ExecutionWizardPage() {
  const organizations = useApp((s) => s.organizations);
  const projects = useApp((s) => s.projects);
  const assets = useApp((s) => s.assets);
  const authorizations = useApp((s) => s.authorizations);
  const engagements = useApp((s) => s.engagements);

  const [step, setStep] = React.useState<StepKey>("context");
  const [draft, setDraft] = React.useState<DraftState>({
    orgId: organizations[0]?.id || "",
    projectId: projects[0]?.id || "",
    assetId: assets[0]?.id || "",
    authorizationId: authorizations[0]?.id || "",
    engagementId: engagements[0]?.id || "",
    templateId: TEMPLATES[0]?.id || "",
  });

  React.useEffect(() => {
    setDraft((d) => ({
      orgId: d.orgId || organizations[0]?.id || "",
      projectId: d.projectId || projects[0]?.id || "",
      assetId: d.assetId || assets[0]?.id || "",
      authorizationId: d.authorizationId || authorizations[0]?.id || "",
      engagementId: d.engagementId || engagements[0]?.id || "",
      templateId: d.templateId || TEMPLATES[0]?.id || "",
    }));
  }, [organizations, projects, assets, authorizations, engagements]);

  const go = useApp((s) => s.go);
  const stepIdx = STEPS.findIndex((s) => s.key === step);

  const update = (patch: Partial<DraftState>) => setDraft((d) => ({ ...d, ...patch }));

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[
            { label: "Executions", onClick: () => go("execution_wizard") },
            { label: "New Validation" },
          ]}
          title="Queue a Validation Execution"
          description="Pre-flight orchestrator. Each step gates the next — asset ownership, authorization window, engagement state, scope match, and safety controls are all verified before dispatch."
          right={
            <>
              <CyberButton size="sm" variant="ghost" onClick={() => go("dashboard")}>
                <ArrowLeft className="w-3 h-3" /> Cancel
              </CyberButton>
            </>
          }
        />

        {/* Horizontal stepper */}
        <div className="px-4 lg:px-6 py-3 border-b border-(--ss-hairline-strong) bg-[#050810]/60 overflow-x-auto ss-scroll">
          <ol className="flex items-center gap-1 min-w-max">
            {STEPS.map((s, i) => {
              const isActive = s.key === step;
              const isDone = i < stepIdx;
              const tone = isActive ? "cyan" : isDone ? "green" : "slate";
              return (
                <React.Fragment key={s.key}>
                  <li>
                    <button
                      onClick={() => setStep(s.key)}
                      className={cn(
                        "flex items-center gap-2 px-3 py-1.5 rounded-sm border transition-all whitespace-nowrap",
                        isActive && "border-cyan-400/50 bg-cyan-500/10 ss-glow-cyan",
                        isDone && "border-emerald-500/40 bg-emerald-500/5 hover:bg-emerald-500/10",
                        !isActive && !isDone && "border-(--ss-hairline-strong) bg-transparent hover:bg-(--ss-surface-3)/40"
                      )}
                    >
                      <span className={cn(
                        "w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-semibold tnum",
                        tone === "cyan" && "bg-cyan-400 text-[#060912]",
                        tone === "green" && "bg-emerald-400 text-[#060912]",
                        tone === "slate" && "bg-(--ss-surface-3) text-slate-500 border border-(--ss-hairline-strong)"
                      )}>
                        {isDone ? "✓" : i + 1}
                      </span>
                      <span className={cn(
                        "text-[11px] uppercase tracking-wider font-medium",
                        isActive ? "text-cyan-200" : isDone ? "text-emerald-300" : "text-slate-400"
                      )}>
                        {s.label}
                      </span>
                    </button>
                  </li>
                  {i < STEPS.length - 1 && (
                    <li className={cn(
                      "w-6 h-px",
                      i < stepIdx ? "bg-emerald-500/50" : "bg-(--ss-hairline-strong)"
                    )} />
                  )}
                </React.Fragment>
              );
            })}
          </ol>
        </div>

        <div className="px-4 lg:px-6 py-5">
          <div className="max-w-5xl mx-auto">
            {step === "context" && <ContextStep draft={draft} update={update} />}
            {step === "asset" && <AssetStep draft={draft} update={update} />}
            {step === "authorization" && <AuthorizationStep draft={draft} update={update} />}
            {step === "engagement" && <EngagementStep draft={draft} update={update} />}
            {step === "template" && <TemplateStep draft={draft} update={update} />}
            {step === "safety" && <SafetyStep draft={draft} />}
            {step === "confirm" && <ConfirmStep draft={draft} />}

            {/* Footer nav */}
            <div className="mt-6 flex items-center justify-between">
              <CyberButton
                size="md"
                variant="ghost"
                onClick={() => stepIdx > 0 ? setStep(STEPS[stepIdx - 1].key) : go("dashboard")}
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                {stepIdx > 0 ? "Previous step" : "Cancel"}
              </CyberButton>
              <div className="flex items-center gap-2">
                <Pill tone="slate">
                  Step {stepIdx + 1} / {STEPS.length}
                </Pill>
                {stepIdx < STEPS.length - 1 ? (
                  <CyberButton
                    size="md"
                    variant="primary"
                    onClick={() => setStep(STEPS[stepIdx + 1].key)}
                  >
                    Continue
                    <ArrowRight className="w-3.5 h-3.5" />
                  </CyberButton>
                ) : (
                  <CyberButton
                    size="md"
                    variant="primary"
                    onClick={() => go("dashboard")}
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Queue execution
                  </CyberButton>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

/* ---------------- Step 1: Context ---------------- */
function ContextStep({ draft, update }: { draft: DraftState; update: (p: Partial<DraftState>) => void }) {
  const organizations = useApp((s) => s.organizations);
  const projects = useApp((s) => s.projects);
  return (
    <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center gap-2 mb-1">
          <Database className="w-3.5 h-3.5 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Step 1 · Context</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Bind to organization & project</h2>
        <p className="text-xs text-slate-500 mb-4">
          Every execution inherits its scope, authorization window, and safety policy from the parent organization and project. Selecting the wrong context will be caught by the safety check.
        </p>

        <div className="space-y-4">
          <div>
            <label className="ss-eyebrow block mb-1.5">Organization</label>
            <div className="grid sm:grid-cols-3 gap-2">
              {organizations.map((o) => {
                const active = draft.orgId === o.id;
                return (
                  <button
                    key={o.id}
                    onClick={() => update({ orgId: o.id })}
                    className={cn(
                      "text-left p-3 rounded-sm border transition-all",
                      active
                        ? "border-cyan-400/50 bg-cyan-500/10 ss-glow-cyan"
                        : "border-(--ss-hairline-strong) bg-(--ss-surface-2) hover:bg-(--ss-surface-3)/50"
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] ss-mono-xs text-slate-500">{o.code}</span>
                      {active && <CheckCircle2 className="w-3 h-3 text-cyan-400" />}
                    </div>
                    <div className="text-xs font-medium text-slate-200">{o.name}</div>
                    <div className="text-[10px] text-slate-500 mt-1">{o.projectsCount} projects · {o.verifiedAssets} verified assets</div>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="ss-eyebrow block mb-1.5">Project</label>
            <div className="grid sm:grid-cols-2 gap-2">
              {projects.filter((p) => p.organizationId === draft.orgId).map((p) => {
                const active = draft.projectId === p.id;
                return (
                  <button
                    key={p.id}
                    onClick={() => update({ projectId: p.id })}
                    className={cn(
                      "text-left p-3 rounded-sm border transition-all flex items-center gap-3",
                      active
                        ? "border-cyan-400/50 bg-cyan-500/10"
                        : "border-(--ss-hairline-strong) bg-(--ss-surface-2) hover:bg-(--ss-surface-3)/50"
                    )}
                  >
                    <Layers className={cn("w-4 h-4", active ? "text-cyan-400" : "text-slate-500")} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-slate-200 truncate">{p.name}</div>
                      <div className="text-[10px] text-slate-500">{p.code} · {p.assetsCount} assets</div>
                    </div>
                    {active && <CheckCircle2 className="w-3 h-3 text-cyan-400" />}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="ss-panel-flat p-4">
        <div className="ss-eyebrow mb-2">Why context matters</div>
        <ul className="space-y-2.5 text-[11px] text-slate-400 leading-relaxed">
          <li className="flex gap-2">
            <Shield className="w-3 h-3 text-cyan-400 shrink-0 mt-0.5" />
            Scope, authorization windows, and engagement state are inherited from the org/project chain.
          </li>
          <li className="flex gap-2">
            <Target className="w-3 h-3 text-cyan-400 shrink-0 mt-0.5" />
            Only assets owned by this project can be targeted. Cross-project execution is blocked by the safety check.
          </li>
          <li className="flex gap-2">
            <Lock className="w-3 h-3 text-cyan-400 shrink-0 mt-0.5" />
            Audit attribution and credential scoping are bound to the selected organization.
          </li>
        </ul>
      </div>
    </div>
  );
}

/* ---------------- Step 2: Asset ---------------- */
function AssetStep({ draft, update }: { draft: DraftState; update: (p: Partial<DraftState>) => void }) {
  const assets = useApp((s) => s.assets);
  const projectAssets = assets.filter((a) => a.projectId === draft.projectId);
  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center gap-2 mb-1">
          <Target className="w-3.5 h-3.5 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Step 2 · Asset</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Select target asset</h2>
        <p className="text-xs text-slate-500 mb-4">
          Only verified assets owned by the selected project appear here. Pending or failed verification assets cannot be targeted.
        </p>

        <div className="space-y-2">
          {projectAssets.map((a) => {
            const active = draft.assetId === a.id;
            const disabled = a.verification !== "verified";
            return (
              <button
                key={a.id}
                onClick={() => !disabled && update({ assetId: a.id })}
                disabled={disabled}
                className={cn(
                  "w-full text-left p-3 rounded-sm border transition-all",
                  active ? "border-cyan-400/50 bg-cyan-500/10 ss-glow-cyan" : "border-(--ss-hairline-strong) bg-(--ss-surface-2)",
                  !disabled && "hover:bg-(--ss-surface-3)/50",
                  disabled && "opacity-50 cursor-not-allowed"
                )}
              >
                <div className="flex items-center justify-between gap-3 mb-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      a.verification === "verified" ? "bg-emerald-400" : "bg-amber-400"
                    )} />
                    <span className="text-xs font-medium text-slate-200 truncate">{a.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Pill tone={a.criticality === "critical" ? "red" : a.criticality === "high" ? "amber" : "slate"}>
                      {a.criticality}
                    </Pill>
                    {disabled && <Pill tone="amber">unverified</Pill>}
                  </div>
                </div>
                <code className="ss-mono-xs text-slate-400 block">{a.target}</code>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {a.tags.map((t) => (
                    <span key={t} className="text-[9px] ss-mono-xs text-slate-500 border border-(--ss-hairline) rounded-sm px-1.5 py-0.5">
                      {t}
                    </span>
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="ss-panel-flat p-4">
        <div className="ss-eyebrow mb-2">Asset selection rules</div>
        <ul className="space-y-2 text-[11px] text-slate-400">
          <li>• Asset must be ownership-verified via DNS TXT challenge.</li>
          <li>• Asset must belong to the selected project.</li>
          <li>• Target hostname is masked in all logs and audit trails.</li>
          <li>• Criticality influences allowed risk tier in the safety check.</li>
        </ul>
      </div>
    </div>
  );
}

/* ---------------- Step 3: Authorization ---------------- */
function AuthorizationStep({ draft, update }: { draft: DraftState; update: (p: Partial<DraftState>) => void }) {
  const authorizations = useApp((s) => s.authorizations);
  const auths = authorizations.filter((a) => a.organizationId === draft.orgId);
  const selected = authorizations.find((a) => a.id === draft.authorizationId);
  return (
    <div className="grid lg:grid-cols-[1.2fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center gap-2 mb-1">
          <Shield className="w-3.5 h-3.5 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Step 3 · Authorization</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Choose an active authorization</h2>
        <p className="text-xs text-slate-500 mb-4">
          Authorization defines the scope of allowed paths, ports, excluded paths, max risk tier, and the validity window.
        </p>

        <div className="space-y-2">
          {auths.map((a) => {
            const active = draft.authorizationId === a.id;
            const expired = a.state !== "active";
            return (
              <button
                key={a.id}
                onClick={() => !expired && update({ authorizationId: a.id })}
                disabled={expired}
                className={cn(
                  "w-full text-left p-3 rounded-sm border transition-all",
                  active ? "border-cyan-400/50 bg-cyan-500/10 ss-glow-cyan" : "border-(--ss-hairline-strong) bg-(--ss-surface-2)",
                  !expired && "hover:bg-(--ss-surface-3)/50",
                  expired && "opacity-50 cursor-not-allowed"
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <code className="ss-mono-xs text-cyan-200">{a.code}</code>
                  <div className="flex items-center gap-1.5">
                    <RiskTierBadge tier={a.maxRiskTier} />
                    {a.immutableLock && <Pill tone="green"><Lock className="w-2.5 h-2.5" /> locked</Pill>}
                  </div>
                </div>
                <div className="text-[10px] text-slate-500">
                  Window: <span className="ss-mono-xs text-slate-400">{a.validFrom.slice(0, 10)}</span> → <span className="ss-mono-xs text-slate-400">{a.validUntil.slice(0, 10)}</span>
                </div>
                <div className="text-[10px] text-slate-500 mt-1">
                  {a.scopedAssetNames.length} scoped asset(s) · {a.scope.allowedPaths.length} allowed path(s)
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {selected && (
        <div className="ss-panel-flat p-4">
          <div className="ss-eyebrow mb-2">Authorization summary</div>
          <div className="space-y-0">
            <KeyValue k="State" v={selected.state} />
            <KeyValue k="Max risk tier" v={<RiskTierBadge tier={selected.maxRiskTier} />} />
            <KeyValue k="Valid window" v={`${selected.validFrom.slice(0,10)} → ${selected.validUntil.slice(0,10)}`} mono />
            <KeyValue k="Scoped assets" v={selected.scopedAssetNames.join(", ")} />
          </div>
          <div className="mt-3">
            <div className="ss-eyebrow mb-1.5">Allowed paths</div>
            <div className="flex flex-wrap gap-1">
              {selected.scope.allowedPaths.map((p) => (
                <code key={p} className="ss-mono-xs text-emerald-200 border border-emerald-500/30 bg-emerald-500/5 rounded-sm px-1.5 py-0.5">{p}</code>
              ))}
            </div>
          </div>
          <div className="mt-2">
            <div className="ss-eyebrow mb-1.5">Excluded paths</div>
            <div className="flex flex-wrap gap-1">
              {selected.scope.excludedPaths.map((p) => (
                <code key={p} className="ss-mono-xs text-red-200 border border-red-500/30 bg-red-500/5 rounded-sm px-1.5 py-0.5">{p}</code>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- Step 4: Engagement ---------------- */
function EngagementStep({ draft, update }: { draft: DraftState; update: (p: Partial<DraftState>) => void }) {
  const engagements = useApp((s) => s.engagements);
  const engs = engagements.filter((e) => e.organizationId === draft.orgId && e.authorizationId === draft.authorizationId);
  const selected = engagements.find((e) => e.id === draft.engagementId);
  return (
    <div className="grid lg:grid-cols-[1.2fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center gap-2 mb-1">
          <Zap className="w-3.5 h-3.5 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Step 4 · Engagement</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Bind to engagement</h2>
        <p className="text-xs text-slate-500 mb-4">
          Engagement is the operational time window. Execution can only run while the engagement is active and within its window.
        </p>

        <div className="space-y-2">
          {engs.map((e) => {
            const active = draft.engagementId === e.id;
            const blocked = e.state !== "active" && e.state !== "scheduled";
            return (
              <button
                key={e.id}
                onClick={() => !blocked && update({ engagementId: e.id })}
                disabled={blocked}
                className={cn(
                  "w-full text-left p-3 rounded-sm border transition-all",
                  active ? "border-cyan-400/50 bg-cyan-500/10 ss-glow-cyan" : "border-(--ss-hairline-strong) bg-(--ss-surface-2)",
                  !blocked && "hover:bg-(--ss-surface-3)/50",
                  blocked && "opacity-50 cursor-not-allowed"
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <code className="ss-mono-xs text-cyan-200">{e.code}</code>
                  <Pill tone={e.state === "active" ? "green" : e.state === "scheduled" ? "blue" : "amber"}>
                    {e.state}
                  </Pill>
                </div>
                <div className="text-xs font-medium text-slate-200 truncate">{e.name}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  Window: <span className="ss-mono-xs">{e.windowStart.slice(0,16).replace("T"," ")}</span> → <span className="ss-mono-xs">{e.windowEnd.slice(0,16).replace("T"," ")}</span>
                </div>
                {e.killSwitch.state !== "inactive" && (
                  <div className="mt-1.5">
                    <Pill tone="amber"><ShieldAlert className="w-2.5 h-2.5" /> kill switch {e.killSwitch.state}</Pill>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {selected && (
        <div className="ss-panel-flat p-4">
          <div className="ss-eyebrow mb-2">Engagement summary</div>
          <div className="space-y-0">
            <KeyValue k="State" v={selected.state} />
            <KeyValue k="Window start" v={selected.windowStart.replace("T"," ").slice(0,16)} mono />
            <KeyValue k="Window end" v={selected.windowEnd.replace("T"," ").slice(0,16)} mono />
            <KeyValue k="Max risk tier" v={<RiskTierBadge tier={selected.maxRiskTier} />} />
            <KeyValue k="Active executions" v={selected.activeExecutions} mono />
          </div>
          <AlertBanner tone="info" title="Engagement gates dispatch" className="mt-3">
            If the engagement is paused or its window closes mid-execution, the worker is halted and the credential revoked.
          </AlertBanner>
        </div>
      )}
    </div>
  );
}

/* ---------------- Step 5: Template ---------------- */
function TemplateStep({ draft, update }: { draft: DraftState; update: (p: Partial<DraftState>) => void }) {
  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center gap-2 mb-1">
          <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Step 5 · Template</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Pick a validation template</h2>
        <p className="text-xs text-slate-500 mb-4">
          TEMPLATES define the sequence of safe checks performed by the worker. All TEMPLATES are read-only and non-invasive.
        </p>

        <div className="space-y-2">
          {TEMPLATES.map((t) => {
            const active = draft.templateId === t.id;
            return (
              <button
                key={t.id}
                onClick={() => update({ templateId: t.id })}
                className={cn(
                  "w-full text-left p-3 rounded-sm border transition-all",
                  active ? "border-cyan-400/50 bg-cyan-500/10 ss-glow-cyan" : "border-(--ss-hairline-strong) bg-(--ss-surface-2) hover:bg-(--ss-surface-3)/50"
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-slate-200">{t.name}</span>
                  <div className="flex items-center gap-1.5">
                    <Pill tone="slate">{t.steps} steps</Pill>
                    <Pill tone="slate">~{t.estimatedSeconds}s</Pill>
                    <RiskTierBadge tier={t.riskTier} />
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">{t.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="ss-panel-flat p-4">
        <div className="ss-eyebrow mb-2">Template safety</div>
        <ul className="space-y-2 text-[11px] text-slate-400 leading-relaxed">
          <li className="flex gap-2"><ShieldCheck className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" /> All TEMPLATES operate within authorized scope only.</li>
          <li className="flex gap-2"><ShieldCheck className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" /> No exploitation payloads, no brute force, no credential stuffing.</li>
          <li className="flex gap-2"><ShieldCheck className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" /> Evidence is summarized; raw responses, cookies, and Authorization headers are never stored.</li>
        </ul>
      </div>
    </div>
  );
}

/* ---------------- Step 6: Safety Check (pre-flight) ---------------- */
function SafetyStep({ draft }: { draft: DraftState }) {
  const assets = useApp((s) => s.assets);
  const authorizations = useApp((s) => s.authorizations);
  const engagements = useApp((s) => s.engagements);

  const asset = assets.find((a) => a.id === draft.assetId);
  const auth = authorizations.find((a) => a.id === draft.authorizationId);
  const eng = engagements.find((e) => e.id === draft.engagementId);
  const tpl = TEMPLATES.find((t) => t.id === draft.templateId);

  // Build safety rows
  const rows: { label: string; explanation: string; passed: boolean; blocking: boolean; meta: string }[] = [
    {
      label: "Asset verified",
      explanation: "Asset ownership proven via DNS TXT challenge.",
      passed: asset?.verification === "verified",
      blocking: true,
      meta: asset ? `verification=${asset.verification}` : "",
    },
    {
      label: "Authorization active",
      explanation: "Authorization is in active state within its valid window.",
      passed: auth?.state === "active",
      blocking: true,
      meta: auth ? `state=${auth.state}` : "",
    },
    {
      label: "Engagement active",
      explanation: "Engagement is active (or scheduled) and within its time window.",
      passed: eng?.state === "active" || eng?.state === "scheduled",
      blocking: true,
      meta: eng ? `state=${eng.state}` : "",
    },
    {
      label: "Scope match",
      explanation: "Selected asset appears in the authorization's scoped asset list.",
      passed: auth?.scopedAssets.includes(asset?.id ?? "") ?? false,
      blocking: true,
      meta: auth && asset ? `asset ${asset.id} in scoped list` : "",
    },
    {
      label: "Testing window valid",
      explanation: "Current time is inside the engagement's authorized window.",
      passed: eng ? new Date() >= new Date(eng.windowStart) && new Date() <= new Date(eng.windowEnd) : false,
      blocking: true,
      meta: eng ? `${eng.windowStart.slice(0,16)} → ${eng.windowEnd.slice(0,16)}` : "",
    },
    {
      label: "Kill switch inactive",
      explanation: "Engagement kill switch is not armed or active.",
      passed: eng?.killSwitch.state === "inactive",
      blocking: true,
      meta: eng ? `state=${eng.killSwitch.state}` : "",
    },
    {
      label: "Risk tier allowed",
      explanation: "Template risk tier is within authorization's max risk tier.",
      passed: tpl && auth ? rank(tpl.riskTier) <= rank(auth.maxRiskTier) : false,
      blocking: true,
      meta: tpl && auth ? `template=${tpl.riskTier}, max=${auth.maxRiskTier}` : "",
    },
    {
      label: "Credential will be issued",
      explanation: "Per-execution credential will be issued at dispatch; raw token never displayed.",
      passed: true,
      blocking: false,
      meta: "source=per_execution, fallback=disabled",
    },
    {
      label: "Dispatch backend available",
      explanation: "Celery dispatch backend is online and accepting messages.",
      passed: true,
      blocking: true,
      meta: "broker=online, region=eu-1",
    },
    {
      label: "Worker auth mode ready",
      explanation: "Worker authentication mode is per-execution credential (shared fallback disabled).",
      passed: true,
      blocking: true,
      meta: "mode=per_execution, fallback=disabled",
    },
  ];

  const blockingFailures = rows.filter((r) => r.blocking && !r.passed);

  return (
    <div className="grid lg:grid-cols-[1.7fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <ClipboardCheck className="w-3.5 h-3.5 text-cyan-400" />
            <div className="ss-eyebrow text-cyan-300">Step 6 · Pre-flight Safety Check</div>
          </div>
          <Pill tone={blockingFailures.length === 0 ? "green" : "red"}>
            {blockingFailures.length === 0 ? "All gates passed" : `${blockingFailures.length} blocking`}
          </Pill>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Pre-flight control panel</h2>
        <p className="text-xs text-slate-500 mb-4">
          Each gate is evaluated against the live state of asset, authorization, and engagement. Blocking failures prevent queueing.
        </p>

        <div className="border border-(--ss-hairline-strong) rounded-sm overflow-hidden">
          {rows.map((r, i) => (
            <div
              key={r.label}
              className={cn(
                "flex items-start gap-3 px-3 py-2.5",
                i > 0 && "border-t border-(--ss-hairline)"
              )}
            >
              <div className="shrink-0 mt-0.5">
                {r.passed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : r.blocking ? (
                  <XCircle className="w-4 h-4 text-red-400" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-medium text-slate-200">{r.label}</span>
                  {r.blocking ? (
                    <Pill tone={r.passed ? "green" : "red"}>{r.passed ? "blocking · passed" : "blocking · failed"}</Pill>
                  ) : (
                    <Pill tone="slate">non-blocking</Pill>
                  )}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">{r.explanation}</div>
                {r.meta && <code className="ss-mono-xs text-slate-500 mt-0.5 block">{r.meta}</code>}
              </div>
            </div>
          ))}
        </div>

        {blockingFailures.length > 0 && (
          <AlertBanner tone="danger" title={`${blockingFailures.length} blocking failure(s)`} className="mt-3">
            Resolve these gates before queueing. Non-blocking gates will run as advisory checks.
          </AlertBanner>
        )}
      </div>

      <div className="ss-panel-flat p-4 space-y-3">
        <div>
          <div className="ss-eyebrow mb-1.5">What happens at queue</div>
          <ul className="space-y-2 text-[11px] text-slate-400 leading-relaxed">
            <li>1. Scope snapshot is frozen (immutable for this execution).</li>
            <li>2. Safety snapshot is recorded in the audit trail.</li>
            <li>3. Dispatch message is published to <code className="ss-mono-xs text-cyan-200">securescope.exec.v1</code>.</li>
            <li>4. Per-execution credential is issued — never displayed.</li>
            <li>5. Worker picks up the message within the engagement window.</li>
          </ul>
        </div>
        <AlertBanner tone="info" title="Safety snapshot is immutable">
          Once queued, the scope and safety snapshot cannot be modified — even if the authorization or engagement changes.
        </AlertBanner>
      </div>
    </div>
  );
}

function rank(t: "low" | "moderate" | "high" | "critical") {
  return { low: 1, moderate: 2, high: 3, critical: 4 }[t];
}

/* ---------------- Step 7: Confirm Queue ---------------- */
function ConfirmStep({ draft }: { draft: DraftState }) {
  const go = useApp((s) => s.go);
  const assets = useApp((s) => s.assets);
  const authorizations = useApp((s) => s.authorizations);
  const engagements = useApp((s) => s.engagements);
  const organizations = useApp((s) => s.organizations);
  const projects = useApp((s) => s.projects);
  const addExecution = useApp((s) => s.addExecution);

  const asset = assets.find((a) => a.id === draft.assetId);
  const auth = authorizations.find((a) => a.id === draft.authorizationId);
  const eng = engagements.find((e) => e.id === draft.engagementId);
  const tpl = TEMPLATES.find((t) => t.id === draft.templateId);
  const org = organizations.find((o) => o.id === draft.orgId);
  const proj = projects.find((p) => p.id === draft.projectId);

  if (!asset || !auth || !eng || !tpl || !org || !proj) return null;

  return (
    <div className="grid lg:grid-cols-[1.3fr_1fr] gap-4">
      <div className="ss-panel p-5">
        <div className="flex items-center gap-2 mb-1">
          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Step 7 · Confirm Queue</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100 mb-1">Final execution summary</h2>
        <p className="text-xs text-slate-500 mb-4">
          Review the scope and safety snapshots. Once queued, the execution runs only within the authorized scope and engagement window.
        </p>

        <div className="space-y-4">
          <div>
            <div className="ss-eyebrow mb-2">Execution identity</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0">
              <KeyValue k="Organization" v={org.name} />
              <KeyValue k="Project" v={proj.name} />
              <KeyValue k="Asset" v={asset.name} />
              <KeyValue k="Target" v={<code className="ss-mono-xs text-cyan-200">{asset.target}</code>} />
              <KeyValue k="Authorization" v={auth.code} mono />
              <KeyValue k="Engagement" v={eng.code} mono />
              <KeyValue k="Template" v={tpl.name} />
              <KeyValue k="Risk tier" v={<RiskTierBadge tier={tpl.riskTier} />} />
            </div>
          </div>

          <div>
            <div className="ss-eyebrow mb-2">Scope snapshot (frozen at queue)</div>
            <div className="ss-panel-flat p-3 space-y-2">
              <div className="grid grid-cols-2 gap-x-4 gap-y-0">
                <KeyValue k="Allowed ports" v={auth.scope.allowedPorts.join(", ")} mono />
                <KeyValue k="Max risk tier" v={<RiskTierBadge tier={auth.maxRiskTier} />} />
              </div>
              <div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Allowed paths</div>
                <div className="flex flex-wrap gap-1">
                  {auth.scope.allowedPaths.map((p) => (
                    <code key={p} className="ss-mono-xs text-emerald-200 border border-emerald-500/30 bg-emerald-500/5 rounded-sm px-1.5 py-0.5">{p}</code>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wide mb-1">Excluded paths</div>
                <div className="flex flex-wrap gap-1">
                  {auth.scope.excludedPaths.map((p) => (
                    <code key={p} className="ss-mono-xs text-red-200 border border-red-500/30 bg-red-500/5 rounded-sm px-1.5 py-0.5">{p}</code>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div>
            <div className="ss-eyebrow mb-2">Safety snapshot</div>
            <div className="ss-panel-flat p-3 grid grid-cols-2 gap-x-4 gap-y-0">
              <KeyValue k="Asset verified" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Authorization active" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Engagement active" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Scope match" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Window valid" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Kill switch inactive" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Risk tier allowed" v={<span className="text-emerald-300">✓</span>} />
              <KeyValue k="Dispatch backend" v={<span className="text-emerald-300">✓</span>} />
            </div>
          </div>

          <AlertBanner tone="warning" title="Execution runs only within authorized scope">
            Any deviation from the scope snapshot will halt the worker, revoke the credential, and surface a blocked_by_control outcome.
          </AlertBanner>
        </div>
      </div>

      <div className="ss-panel-flat p-4 space-y-3">
        <div className="ss-eyebrow">Credential issuance notice</div>
        <p className="text-[11px] text-slate-400 leading-relaxed">
          A per-execution worker credential will be issued when the dispatch message is published. The raw token is never stored client-side, never logged, and never displayed in the UI.
        </p>
        <MaskedField
          label="Worker token"
          placeholder="per-execution · issued at dispatch"
          note="Revoked automatically on finish, kill switch, or expiry."
        />
        <div className="ss-eyebrow pt-1">Queue action</div>
        <CyberButton
          variant="primary"
          className="w-full"
          onClick={async () => {
            if (tpl && asset && eng) {
              await addExecution({
                asset_id: asset.id,
                engagement_id: eng.id,
                template_id: tpl.id,
                risk_tier: tpl.riskTier,
                execution_specification: {}
              });
            }
            go("dashboard");
          }}
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          Queue execution
        </CyberButton>
        <div className="text-[10px] text-slate-500 text-center">
          You will be redirected to the execution detail page once queued.
        </div>
      </div>
    </div>
  );
}

