"use client";

import * as React from "react";
import { Shield, Lock, Fingerprint, ArrowRight, AlertTriangle } from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { CyberButton } from "../shared/ui";

const DEV_ORG_ID = process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? "";

export function LoginPage() {
  const login = useApp((s) => s.login);
  const error = useApp((s) => s.error);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [mfa, setMfa] = React.useState("");
  const [orgId, setOrgId] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [localError, setLocalError] = React.useState<string | null>(null);

  const devLogin = () => {
    login(DEV_ORG_ID);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const trimmed = orgId.trim();
    if (!trimmed) {
      setLocalError("Organization ID is required.");
      return;
    }
    const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRe.test(trimmed)) {
      setLocalError("Enter a valid Organization ID (UUID format).");
      return;
    }
    setSubmitting(true);
    try {
      login(trimmed);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen ss-vignette flex flex-col">
      {/* Top thin strip */}
      <div className="h-8 px-6 flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-slate-500 border-b border-(--ss-hairline)">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-amber-400" />
            Environment · Staging
          </span>
          <span className="text-slate-700">/</span>
          <span>Region · eu-1</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="ss-mono-xs">Build 2026.07.02</span>
          <span className="text-slate-700">/</span>
          <span className="flex items-center gap-1">
            <Lock className="w-2.5 h-2.5" />
            TLS 1.3
          </span>
        </div>
      </div>

      <div className="flex-1 grid lg:grid-cols-[1.2fr_1fr]">
        {/* Left: brand + context */}
        <div className="relative hidden lg:flex flex-col justify-between p-12 ss-grid-bg">
          <div className="absolute inset-0 pointer-events-none" style={{
            background: "radial-gradient(ellipse 70% 50% at 30% 20%, rgba(34,211,238,0.08), transparent 60%)"
          }} />
          <div className="relative">
            <div className="flex items-center gap-3 mb-12">
              <div className="w-10 h-10 border border-cyan-400/50 bg-cyan-500/10 rounded-sm flex items-center justify-center ss-glow-cyan">
                <Shield className="w-5 h-5 text-cyan-300" />
              </div>
              <div>
                <div className="text-2xl font-semibold tracking-tight text-slate-100">
                  Secure<span className="text-cyan-300">Scope</span>
                </div>
                <div className="text-[10px] uppercase tracking-[0.25em] text-slate-500 mt-0.5">
                  Authorized Security Validation Control
                </div>
              </div>
            </div>

            <div className="max-w-md">
              <div className="text-[10px] uppercase tracking-[0.2em] text-cyan-400/80 mb-3">
                Operator Briefing
              </div>
              <h2 className="text-2xl font-light text-slate-200 leading-snug mb-4">
                Orchestrate authorized security validation against verified assets — within enforceable scope, time windows, and safety controls.
              </h2>
              <p className="text-xs text-slate-500 leading-relaxed">
                Every execution is bound to an active authorization and engagement. Worker credentials are issued per-execution, never displayed, and revoked automatically on completion, kill switch, or expiry.
              </p>
            </div>
          </div>

          <div className="relative grid grid-cols-3 gap-3">
            {[
              { label: "Asset Verification", v: "DNS TXT challenge", note: "ownership-bound" },
              { label: "Authorization", v: "Scope-locked", note: "immutable active lock" },
              { label: "Safety Controls", v: "Kill switch armed", note: "audited activation" },
            ].map((x) => (
              <div key={x.label} className="ss-panel-flat p-3">
                <div className="ss-eyebrow mb-1">{x.label}</div>
                <div className="text-xs font-medium text-cyan-200">{x.v}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{x.note}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: login panel */}
        <div className="flex items-center justify-center p-6 lg:p-12">
          <div className="w-full max-w-sm">
            <div className="lg:hidden flex items-center gap-3 mb-8 justify-center">
              <div className="w-9 h-9 border border-cyan-400/50 bg-cyan-500/10 rounded-sm flex items-center justify-center">
                <Shield className="w-4 h-4 text-cyan-300" />
              </div>
              <div className="text-xl font-semibold tracking-tight text-slate-100">
                Secure<span className="text-cyan-300">Scope</span>
              </div>
            </div>

            <div className="ss-panel p-6">
              <div className="flex items-center gap-2 mb-1">
                <Fingerprint className="w-4 h-4 text-cyan-400" />
                <span className="text-[10px] uppercase tracking-[0.22em] text-cyan-300">Operator Authentication</span>
              </div>
              <h1 className="text-lg font-semibold text-slate-100">Access SecureScope</h1>
              <p className="text-[11px] text-slate-500 mt-1 mb-5">
                Restricted to authorized operators. All access is audited and bound to MFA.
              </p>

              <form onSubmit={submit} className="space-y-3">
                <div>
                  <label className="block ss-eyebrow mb-1">Operator Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3 py-2 text-sm bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/50 focus:ss-glow-cyan transition-all"
                    placeholder="operator@org.sec"
                    required
                  />
                </div>
                <div>
                  <label className="block ss-eyebrow mb-1">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-3 py-2 text-sm bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/50 focus:ss-glow-cyan transition-all"
                    placeholder="••••••••••••"
                    required
                  />
                </div>
                <div>
                  <label className="flex items-center justify-between ss-eyebrow mb-1">
                    <span>MFA Code</span>
                    <span className="text-slate-600 normal-case tracking-normal text-[10px]">TOTP · 6 digits</span>
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={mfa}
                    onChange={(e) => setMfa(e.target.value.replace(/\D/g, ""))}
                    className="w-full px-3 py-2 text-sm bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/50 focus:ss-glow-cyan transition-all ss-mono tracking-[0.4em] text-center"
                    placeholder="······"
                  />
                </div>
                <div>
                  <label className="block ss-eyebrow mb-1">Organization ID</label>
                  <input
                    type="text"
                    value={orgId}
                    onChange={(e) => { setOrgId(e.target.value); setLocalError(null); }}
                    className="w-full px-3 py-2 text-sm bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/50 focus:ss-glow-cyan transition-all ss-mono"
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                    autoComplete="off"
                    spellCheck={false}
                    required
                  />
                </div>

                {(localError || error) && (
                  <div className="flex items-start gap-2 px-3 py-2 border border-red-500/30 bg-red-500/5 rounded-sm">
                    <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
                    <p className="text-[11px] text-red-300">{localError ?? error}</p>
                  </div>
                )}

                <div className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer select-none">
                    <input type="checkbox" className="accent-cyan-500 w-3 h-3" defaultChecked />
                    Bind session to this device
                  </label>
                  <button
                    type="button"
                    className="text-[10px] uppercase tracking-wider text-slate-500 hover:text-cyan-300"
                  >
                    Forgot?
                  </button>
                </div>

                <CyberButton
                  type="submit"
                  variant="primary"
                  className="w-full mt-2"
                >
                  {submitting ? (
                    <>
                      <span className="w-3 h-3 border-2 border-cyan-300/40 border-t-cyan-300 rounded-full animate-spin" />
                      Establishing secure session…
                    </>
                  ) : (
                    <>
                      Authenticate
                      <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </CyberButton>
              </form>
            </div>

            {DEV_ORG_ID && (
              <div className="mt-3">
                <button
                  type="button"
                  onClick={devLogin}
                  className="w-full px-3 py-2 text-[11px] uppercase tracking-[0.18em] text-amber-300/70 border border-amber-500/20 bg-amber-500/5 rounded-sm hover:bg-amber-500/10 hover:text-amber-300 transition-all"
                >
                  ⚡ Dev Login (bypass)
                </button>
              </div>
            )}

            <div className="mt-4 flex items-start gap-2 px-3 py-2.5 border border-amber-500/20 bg-amber-500/5 rounded-sm">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-[10px] text-amber-200/80 leading-relaxed">
                <strong className="text-amber-300">Access restricted to authorized operators.</strong> Unauthorized access attempts are logged, attributed, and forwarded to the security operations center. By proceeding you accept the operator acceptable-use policy.
              </p>
            </div>

            <div className="mt-4 flex items-center justify-between text-[10px] text-slate-600">
              <span>SecureScope · v3.4.1</span>
              <span className="ss-mono-xs">SOC 2 · ISO 27001</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
