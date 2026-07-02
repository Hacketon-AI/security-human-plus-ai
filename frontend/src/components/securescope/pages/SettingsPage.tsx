"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Cog,
  Database,
  Lock,
  Server,
  Settings as SettingsIcon,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import { Pill } from "../shared/badges";
import { AlertBanner, CyberButton, KeyValue, MaskedField } from "../shared/ui";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

const SECTIONS = [
  { key: "environment", label: "Environment" },
  { key: "dispatch", label: "Dispatch backend" },
  { key: "worker_auth", label: "Worker authentication" },
  { key: "safety", label: "Safety controls" },
  { key: "secrets", label: "Secrets policy" },
] as const;

export function SettingsPage() {
  const [section, setSection] = React.useState<(typeof SECTIONS)[number]["key"]>("environment");

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Settings" }]}
          title="System Configuration"
          description="Non-sensitive operational configuration. Secrets, raw worker tokens, broker credentials, and database URLs are never exposed."
          meta={
            <>
              <Pill tone="amber">Staging</Pill>
              <Pill tone="green"><ShieldCheck className="w-2.5 h-2.5" /> Policy enforced</Pill>
            </>
          }
        />

        <div className="px-4 lg:px-6 py-5 grid lg:grid-cols-[200px_1fr] gap-5">
          {/* Section nav (contextual, not a global sidebar) */}
          <nav className="ss-panel-flat p-2 h-max lg:sticky lg:top-[88px]">
            <ul className="space-y-0.5">
              {SECTIONS.map((s) => (
                <li key={s.key}>
                  <button
                    onClick={() => setSection(s.key)}
                    className={cn(
                      "w-full text-left px-2.5 py-1.5 text-[11px] uppercase tracking-wider rounded-sm transition-colors",
                      section === s.key
                        ? "text-cyan-200 bg-cyan-500/10"
                        : "text-slate-400 hover:text-slate-200 hover:bg-[var(--ss-surface-3)]/40"
                    )}
                  >
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          <div className="space-y-4">
            {section === "environment" && (
              <div className="ss-panel p-5">
                <div className="flex items-center gap-2 mb-1">
                  <Cog className="w-4 h-4 text-cyan-400" />
                  <div className="ss-eyebrow text-cyan-300">Environment</div>
                </div>
                <h2 className="text-base font-semibold text-slate-100 mb-3">Environment configuration</h2>
                <div className="grid md:grid-cols-2 gap-x-6 gap-y-0">
                  <KeyValue k="Environment" v="Staging" />
                  <KeyValue k="Region" v="eu-1" mono />
                  <KeyValue k="Build" v="2026.07.02" mono />
                  <KeyValue k="Schema version" v="v1.4.0" mono />
                  <KeyValue k="Timezone" v="UTC" mono />
                  <KeyValue k="Session timeout" v="04:00:00" mono />
                </div>
                <AlertBanner tone="warning" title="Staging environment" className="mt-3">
                  This environment mirrors production but uses sanitized data. Do not assume live asset state.
                </AlertBanner>
              </div>
            )}

            {section === "dispatch" && (
              <div className="ss-panel p-5">
                <div className="flex items-center gap-2 mb-1">
                  <Server className="w-4 h-4 text-cyan-400" />
                  <div className="ss-eyebrow text-cyan-300">Dispatch backend</div>
                </div>
                <h2 className="text-base font-semibold text-slate-100 mb-3">Dispatch backend configuration</h2>
                <div className="grid md:grid-cols-2 gap-x-6 gap-y-0">
                  <KeyValue k="Backend" v="Celery" />
                  <KeyValue k="Broker status" v={<Pill tone="green">online</Pill>} />
                  <KeyValue k="Default queue" v={<code className="ss-mono-xs text-cyan-200">securescope.exec.v1</code>} />
                  <KeyValue k="Dead-letter queue" v={<code className="ss-mono-xs text-cyan-200">securescope.deadletter.v1</code>} />
                  <KeyValue k="Heartbeat interval" v="5s" mono />
                  <KeyValue k="Visibility timeout" v="300s" mono />
                </div>
                <MaskedField
                  label="Broker URL"
                  placeholder="amqp://••••••••@••••••••"
                  note="Broker connection details are managed via the secrets manager and never exposed in the UI."
                  className="mt-3"
                />
              </div>
            )}

            {section === "worker_auth" && (
              <div className="ss-panel p-5">
                <div className="flex items-center gap-2 mb-1">
                  <Shield className="w-4 h-4 text-cyan-400" />
                  <div className="ss-eyebrow text-cyan-300">Worker authentication</div>
                </div>
                <h2 className="text-base font-semibold text-slate-100 mb-3">Worker authentication mode</h2>
                <div className="grid md:grid-cols-2 gap-x-6 gap-y-0 mb-4">
                  <KeyValue k="Auth mode" v={<Pill tone="cyan">Per-execution credential</Pill>} />
                  <KeyValue k="Credential source" v="per_execution" mono />
                  <KeyValue k="Shared-token fallback" v={<Pill tone="slate"><ToggleRight className="w-3 h-3" /> Disabled</Pill>} />
                  <KeyValue k="Token rotation" v="automatic on finish" />
                  <KeyValue k="Algorithm" v="ed25519" mono />
                  <KeyValue k="Token TTL" v="engagement window" />
                </div>
                <AlertBanner tone="success" title="Per-execution credentials enforced">
                  Each worker receives a single-use credential scoped to one execution. Fallback to shared tokens is disabled by policy.
                </AlertBanner>
                <div className="mt-3 grid md:grid-cols-2 gap-3">
                  <div className="ss-panel-flat p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-slate-300">Allow shared-token fallback</span>
                      <ToggleRight className="w-5 h-5 text-slate-600" />
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1">Disabled by policy — cannot be overridden per organization.</div>
                  </div>
                  <div className="ss-panel-flat p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-slate-300">Revoke credential on finish</span>
                      <ToggleRight className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1">Automatic revocation is always on.</div>
                  </div>
                </div>
              </div>
            )}

            {section === "safety" && (
              <div className="ss-panel p-5">
                <div className="flex items-center gap-2 mb-1">
                  <ShieldAlert className="w-4 h-4 text-cyan-400" />
                  <div className="ss-eyebrow text-cyan-300">Safety controls</div>
                </div>
                <h2 className="text-base font-semibold text-slate-100 mb-3">Safety control configuration</h2>
                <div className="grid md:grid-cols-2 gap-x-6 gap-y-0 mb-4">
                  <KeyValue k="Global kill switch" v={<Pill tone="green">Inactive</Pill>} />
                  <KeyValue k="Kill switch armed engagements" v="1" mono />
                  <KeyValue k="Pre-flight safety check" v={<Pill tone="green">Enforced</Pill>} />
                  <KeyValue k="Scope snapshot" v="immutable at queue" />
                  <KeyValue k="Safety snapshot" v="immutable at queue" />
                  <KeyValue k="Max risk tier cap" v={<Pill tone="amber">Critical</Pill>} />
                </div>
                <AlertBanner tone="info" title="Kill switch is always available">
                  The global kill switch halts all in-flight executions across all engagements and revokes every active credential. Activation requires confirmation and is audited.
                </AlertBanner>
                <div className="mt-3">
                  <CyberButton variant="amber">Arm global kill switch</CyberButton>
                </div>
              </div>
            )}

            {section === "secrets" && (
              <div className="ss-panel p-5">
                <div className="flex items-center gap-2 mb-1">
                  <Lock className="w-4 h-4 text-cyan-400" />
                  <div className="ss-eyebrow text-cyan-300">Secrets policy</div>
                </div>
                <h2 className="text-base font-semibold text-slate-100 mb-3">Secrets exposure policy</h2>
                <p className="text-xs text-slate-400 mb-4">
                  SecureScope enforces a strict no-exposure policy for sensitive material. The following are never stored client-side, never logged, and never displayed in the UI.
                </p>
                <div className="space-y-2">
                  {[
                    "Raw worker tokens / credentials",
                    "Broker URLs and broker credentials",
                    "Database URLs",
                    "Raw HTTP response bodies",
                    "Cookies (request and Set-Cookie)",
                    "Authorization headers",
                    "Sensitive request payloads",
                    "Private signing keys",
                  ].map((s) => (
                    <div key={s} className="flex items-center justify-between p-2.5 border border-[var(--ss-hairline)] rounded-sm">
                      <span className="text-[11px] text-slate-300">{s}</span>
                      <Pill tone="red"><Lock className="w-2.5 h-2.5" /> Never exposed</Pill>
                    </div>
                  ))}
                </div>
                <AlertBanner tone="success" title="No reveal, no copy, no export" className="mt-3">
                  There is no UI affordance to reveal, copy, or export any of the above. Failures are explained without leaking sensitive internals.
                </AlertBanner>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
