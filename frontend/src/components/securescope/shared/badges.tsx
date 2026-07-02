"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type {
  AuthorizationState,
  CredentialState,
  EngagementState,
  ExecutionOutcome,
  ExecutionStatus,
  RiskTier,
  VerificationState,
} from "@/lib/securescope/types";

// ============================================================
// SecureScope — Shared design-system primitives
// ============================================================

const dotBase = "inline-block w-1.5 h-1.5 rounded-full";

/* ---------------- Execution status ---------------- */
const STATUS_MAP: Record<
  ExecutionStatus,
  { label: string; text: string; bg: string; border: string; dot: string; glow?: string }
> = {
  draft: { label: "Draft", text: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/30", dot: "bg-slate-400" },
  queued: { label: "Queued", text: "text-blue-300", bg: "bg-blue-500/10", border: "border-blue-500/30", dot: "bg-blue-400" },
  dispatching: { label: "Dispatching", text: "text-cyan-300", bg: "bg-cyan-500/10", border: "border-cyan-500/30", dot: "bg-cyan-400" },
  executing: { label: "Executing", text: "text-cyan-200", bg: "bg-cyan-500/15", border: "border-cyan-400/40", dot: "bg-cyan-300", glow: "ss-glow-cyan" },
  succeeded: { label: "Succeeded", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30", dot: "bg-emerald-400" },
  failed: { label: "Failed", text: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30", dot: "bg-red-400" },
  cancelled: { label: "Cancelled", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-600/30", dot: "bg-slate-500" },
  blocked: { label: "Blocked", text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/30", dot: "bg-amber-400" },
};

export function StatusBadge({
  status,
  className,
  pulse,
}: {
  status: ExecutionStatus;
  className?: string;
  pulse?: boolean;
}) {
  const s = STATUS_MAP[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[11px] font-medium tracking-wide tnum",
        s.text,
        s.bg,
        s.border,
        s.glow,
        className
      )}
    >
      <span className={cn(dotBase, s.dot, status === "executing" && pulse !== false && "ss-pulse-cyan")} />
      {s.label}
    </span>
  );
}

/* ---------------- Outcome ---------------- */
const OUTCOME_MAP: Record<ExecutionOutcome, { label: string; text: string; bg: string; border: string; dot: string }> = {
  validated: { label: "Validated", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30", dot: "bg-emerald-400" },
  failed_safely: { label: "Failed Safely", text: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30", dot: "bg-red-400" },
  blocked_by_control: { label: "Blocked by Control", text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/30", dot: "bg-amber-400" },
  inconclusive: { label: "Inconclusive", text: "text-yellow-300", bg: "bg-yellow-500/10", border: "border-yellow-500/30", dot: "bg-yellow-400" },
  not_reproduced: { label: "Not Reproduced", text: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/30", dot: "bg-slate-400" },
};

export function OutcomeBadge({
  outcome,
  className,
}: {
  outcome: ExecutionOutcome;
  className?: string;
}) {
  const s = OUTCOME_MAP[outcome];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[11px] font-medium tracking-wide tnum",
        s.text,
        s.bg,
        s.border,
        className
      )}
    >
      <span className={cn(dotBase, s.dot)} />
      {s.label}
    </span>
  );
}

/* ---------------- Risk tier ---------------- */
const RISK_MAP: Record<RiskTier, { label: string; text: string; bg: string; border: string }> = {
  low: { label: "Low Risk", text: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/30" },
  moderate: { label: "Moderate Risk", text: "text-blue-300", bg: "bg-blue-500/10", border: "border-blue-500/30" },
  high: { label: "High Risk", text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/30" },
  critical: { label: "Critical Risk", text: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30" },
};

export function RiskTierBadge({ tier, className }: { tier: RiskTier; className?: string }) {
  const s = RISK_MAP[tier];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium tracking-wide",
        s.text,
        s.bg,
        s.border,
        className
      )}
    >
      {s.label}
    </span>
  );
}

/* ---------------- Verification state ---------------- */
const VERIF_MAP: Record<VerificationState, { label: string; text: string; bg: string; border: string; dot: string }> = {
  pending: { label: "Pending", text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/30", dot: "bg-amber-400" },
  verified: { label: "Verified", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30", dot: "bg-emerald-400" },
  expired: { label: "Expired", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-600/30", dot: "bg-slate-500" },
  failed: { label: "Failed", text: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30", dot: "bg-red-400" },
  cancelled: { label: "Cancelled", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-600/30", dot: "bg-slate-500" },
};

export function VerificationBadge({ state, className }: { state: VerificationState; className?: string }) {
  const s = VERIF_MAP[state];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[11px] font-medium tnum", s.text, s.bg, s.border, className)}>
      <span className={cn(dotBase, s.dot)} />
      {s.label}
    </span>
  );
}

/* ---------------- Authorization / Engagement / Credential states ---------------- */
const AUTH_STATE_MAP: Record<AuthorizationState, { label: string; text: string; bg: string; border: string }> = {
  active: { label: "Active", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  expired: { label: "Expired", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-600/30" },
  blocked: { label: "Blocked", text: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30" },
  draft: { label: "Draft", text: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/30" },
};

export function AuthorizationStateBadge({ state, className }: { state: AuthorizationState; className?: string }) {
  const s = AUTH_STATE_MAP[state];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium", s.text, s.bg, s.border, className)}>
      {s.label}
    </span>
  );
}

const ENG_STATE_MAP: Record<EngagementState, { label: string; text: string; bg: string; border: string }> = {
  draft: { label: "Draft", text: "text-slate-300", bg: "bg-slate-500/10", border: "border-slate-500/30" },
  scheduled: { label: "Scheduled", text: "text-blue-300", bg: "bg-blue-500/10", border: "border-blue-500/30" },
  active: { label: "Active", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  paused: { label: "Paused", text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/30" },
  completed: { label: "Completed", text: "text-cyan-300", bg: "bg-cyan-500/10", border: "border-cyan-500/30" },
  cancelled: { label: "Cancelled", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-600/30" },
};

export function EngagementStateBadge({ state, className }: { state: EngagementState; className?: string }) {
  const s = ENG_STATE_MAP[state];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium", s.text, s.bg, s.border, className)}>
      {s.label}
    </span>
  );
}

const CRED_STATE_MAP: Record<CredentialState, { label: string; text: string; bg: string; border: string }> = {
  active: { label: "Active", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  expired: { label: "Expired", text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-600/30" },
  revoked: { label: "Revoked", text: "text-red-300", bg: "bg-red-500/10", border: "border-red-500/30" },
};

export function CredentialStateBadge({ state, className }: { state: CredentialState; className?: string }) {
  const s = CRED_STATE_MAP[state];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] font-medium", s.text, s.bg, s.border, className)}>
      {s.label}
    </span>
  );
}

/* ---------------- Generic pill ---------------- */
export function Pill({
  children,
  tone = "slate",
  className,
}: {
  children: React.ReactNode;
  tone?: "slate" | "cyan" | "green" | "amber" | "red" | "blue";
  className?: string;
}) {
  const tones: Record<string, string> = {
    slate: "text-slate-300 bg-slate-500/10 border-slate-500/30",
    cyan: "text-cyan-300 bg-cyan-500/10 border-cyan-500/30",
    green: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
    amber: "text-amber-300 bg-amber-500/10 border-amber-500/30",
    red: "text-red-300 bg-red-500/10 border-red-500/30",
    blue: "text-blue-300 bg-blue-500/10 border-blue-500/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[10px] font-medium tracking-wide",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

/* ---------------- Eyebrow label ---------------- */
export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("ss-eyebrow", className)}>{children}</div>;
}

/* ---------------- Section header ---------------- */
export function SectionHeader({
  eyebrow,
  title,
  right,
  className,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-end justify-between gap-4 mb-3", className)}>
      <div>
        {eyebrow && <Eyebrow className="mb-1">{eyebrow}</Eyebrow>}
        <h3 className="text-sm font-semibold text-slate-100 tracking-tight">{title}</h3>
      </div>
      {right}
    </div>
  );
}

/* ---------------- KPI cell ---------------- */
export function KpiCell({
  label,
  value,
  tone = "default",
  hint,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "cyan" | "green" | "amber" | "red" | "blue";
  hint?: string;
}) {
  const toneText: Record<string, string> = {
    default: "text-slate-100",
    cyan: "text-cyan-300",
    green: "text-emerald-300",
    amber: "text-amber-300",
    red: "text-red-300",
    blue: "text-blue-300",
  };
  return (
    <div className="px-4 py-2.5">
      <div className="ss-eyebrow mb-1">{label}</div>
      <div className={cn("text-lg font-semibold tnum", toneText[tone])}>{value}</div>
      {hint && <div className="text-[10px] text-slate-500 mt-0.5">{hint}</div>}
    </div>
  );
}
