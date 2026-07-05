"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Lock, ShieldOff, ShieldAlert, Clock, RotateCcw, KeyRound } from "lucide-react";
import type { CredentialRecord } from "@/lib/securescope/types";
import { CredentialStateBadge } from "./badges";
import { KeyValue, AlertBanner, MaskedField } from "./ui";
import { EventTimeline } from "./lifecycle";

// ============================================================
// CredentialStateCard — visibility-only, never exposes raw token
// ============================================================

export function CredentialStateCard({
  credential,
  className,
}: {
  credential: CredentialRecord;
  className?: string;
}) {
  const fmt = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("en-GB", {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: "UTC",
      }) + " UTC";
    } catch {
      return iso;
    }
  };

  const lifecycle: {
    id: string;
    at: string;
    kind: string;
    label: string;
    safeMeta?: Record<string, string>;
  }[] = [
    { id: "ev_iss", at: credential.issuedAt, kind: "worker_started", label: "Credential issued", safeMeta: { source: credential.source, exec_id: credential.executionId } },
    credential.revokedAt
      ? { id: "ev_rev", at: credential.revokedAt, kind: "credential_revoked", label: "Credential revoked", safeMeta: { reason: "execution_finished" } }
      : { id: "ev_exp", at: credential.expiresAt, kind: "auth_expiry_warning", label: "Scheduled expiry", safeMeta: { expires_at: credential.expiresAt } },
  ];

  return (
    <div className={cn("ss-panel", className)}>
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-(--ss-hairline-strong)">
        <div className="flex items-center gap-2">
          <KeyRound className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs font-semibold text-slate-100">Worker Credential</span>
        </div>
        <CredentialStateBadge state={credential.state} />
      </div>

      <div className="p-4 space-y-3">
        <AlertBanner tone="info" title="Credential is issued per-execution and never displayed.">
          SecureScope does not expose raw tokens. Revocation is automatic on execution finish, manual kill switch, or expiry.
        </AlertBanner>

        <div className="grid grid-cols-2 gap-x-6 gap-y-0">
          <KeyValue k="Credential ID" v={credential.id} mono />
          <KeyValue k="State" v={<CredentialStateBadge state={credential.state} />} />
          <KeyValue k="Execution ID" v={credential.executionId} mono />
          <KeyValue k="Source" v={credential.source === "per_execution" ? "Per-execution" : "Shared fallback"} />
          <KeyValue k="Issued at" v={fmt(credential.issuedAt)} mono />
          <KeyValue k="Expires at" v={fmt(credential.expiresAt)} mono />
          <KeyValue k="Revoked at" v={fmt(credential.revokedAt)} mono />
          <KeyValue k="Fallback" v={credential.fallbackEnabled ? "Enabled" : "Disabled"} />
        </div>

        <div>
          <div className="ss-eyebrow mb-1.5">Allowed Actions</div>
          <div className="flex flex-wrap gap-1.5">
            {credential.allowedActions.map((a) => (
              <span
                key={a}
                className="ss-mono-xs text-cyan-200 border border-cyan-500/30 bg-cyan-500/5 rounded-sm px-2 py-0.5"
              >
                {a}
              </span>
            ))}
          </div>
        </div>

        <MaskedField
          label="Raw Token"
          note="SecureScope policy: raw worker token is never stored client-side, never logged, never displayed. Revocation is enforced server-side via credential state."
        />

        <div>
          <div className="ss-eyebrow mb-2">Lifecycle</div>
          <EventTimeline events={lifecycle} />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// KillSwitchControl — amber by default, red only when active
// ============================================================

export function KillSwitchControl({
  state,
  activatedBy,
  activatedAt,
  reason,
  affectedExecutions = [],
  onActivate,
  onDisarm,
  className,
}: {
  state: "inactive" | "armed" | "active";
  activatedBy?: string;
  activatedAt?: string;
  reason?: string;
  affectedExecutions?: string[];
  onActivate?: () => void;
  onDisarm?: () => void;
  className?: string;
}) {
  const tone =
    state === "active"
      ? { border: "border-red-500/40", bg: "bg-red-500/5", glow: "ss-glow-red", text: "text-red-300", Icon: ShieldOff }
      : state === "armed"
      ? { border: "border-amber-500/40", bg: "bg-amber-500/5", glow: "ss-glow-amber", text: "text-amber-300", Icon: ShieldAlert }
      : { border: "border-(--ss-hairline-strong)", bg: "bg-transparent", glow: "", text: "text-slate-300", Icon: Lock };

  const Icon = tone.Icon;

  const fmt = (iso?: string) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("en-GB", {
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: "UTC",
      }) + " UTC";
    } catch {
      return iso;
    }
  };

  return (
    <div className={cn("ss-panel border", tone.border, tone.bg, tone.glow, className)}>
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-(--ss-hairline-strong)">
        <div className="flex items-center gap-2">
          <Icon className={cn("w-3.5 h-3.5", tone.text)} />
          <span className="text-xs font-semibold text-slate-100">Kill Switch</span>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider",
            state === "active" && "text-red-300 border-red-500/40 bg-red-500/10",
            state === "armed" && "text-amber-300 border-amber-500/40 bg-amber-500/10",
            state === "inactive" && "text-slate-400 border-slate-600/40 bg-slate-500/5"
          )}
        >
          {state === "active" ? "Active" : state === "armed" ? "Armed" : "Inactive"}
        </span>
      </div>
      <div className="p-4 space-y-3">
        <p className="text-[11px] text-slate-400 leading-relaxed">
          The kill switch immediately halts all in-flight executions on this engagement, revokes the active
          worker credential, and routes any pending dispatches to the dead-letter queue. Activation is audited.
        </p>

        {(state === "armed" || state === "active") && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-0">
            <KeyValue k="Activated by" v={activatedBy ?? "—"} />
            <KeyValue k="Activated at" v={fmt(activatedAt)} mono />
            <div className="col-span-2">
              <KeyValue k="Reason" v={reason ?? "—"} />
            </div>
          </div>
        )}

        {affectedExecutions.length > 0 && (
          <div>
            <div className="ss-eyebrow mb-1.5">Affected Executions</div>
            <div className="flex flex-wrap gap-1.5">
              {affectedExecutions.map((ex) => (
                <span
                  key={ex}
                  className="ss-mono-xs text-amber-200 border border-amber-500/30 bg-amber-500/5 rounded-sm px-2 py-0.5"
                >
                  {ex}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          {state === "inactive" ? (
            <button
              onClick={onActivate}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm border border-amber-500/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20 hover:ss-glow-amber transition-all"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              Arm Kill Switch
            </button>
          ) : (
            <>
              <button
                onClick={onActivate}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm border border-red-500/40 bg-red-500/15 text-red-200 hover:bg-red-500/25 transition-all"
              >
                <ShieldOff className="w-3.5 h-3.5" />
                Activate Now
              </button>
              <button
                onClick={onDisarm}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-3) text-slate-300 hover:bg-(--ss-surface-4) transition-all"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Disarm
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
