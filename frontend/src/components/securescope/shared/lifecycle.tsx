"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type {
  ExecutionStatus,
  ExecutionOutcome,
} from "@/lib/securescope/types";

// ============================================================
// ExecutionLifecycleRail — horizontal state machine
// queued → dispatching → executing → succeeded / failed
// ============================================================

const RAIL_STAGES: { key: ExecutionStatus; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "dispatching", label: "Dispatching" },
  { key: "executing", label: "Executing" },
  { key: "succeeded", label: "Finished" },
];

const TERMINAL: ExecutionStatus[] = ["succeeded", "failed", "cancelled", "blocked"];

function stageIndex(status: ExecutionStatus): number {
  if (status === "draft") return -1;
  if (status === "queued") return 0;
  if (status === "dispatching") return 1;
  if (status === "executing") return 2;
  return 3; // terminal
}

export function ExecutionLifecycleRail({
  status,
  outcome,
  timestamps,
  className,
  compact,
}: {
  status: ExecutionStatus;
  outcome?: ExecutionOutcome | null;
  timestamps?: { queuedAt?: string | null; dispatchingAt?: string | null; workerStartedAt?: string | null; workerFinishedAt?: string | null };
  className?: string;
  compact?: boolean;
}) {
  const currentIdx = stageIndex(status);
  const isTerminal = TERMINAL.includes(status);
  const terminalFailed = status === "failed" || status === "blocked" || status === "cancelled";

  const fmt = (iso?: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return iso;
    }
  };

  return (
    <div className={cn("ss-panel-flat p-4", className)}>
      <div className="flex items-center justify-between mb-3">
        <div className="ss-eyebrow">Execution Lifecycle</div>
        {isTerminal && outcome && (
          <div className="text-[10px] text-slate-500">
            Terminal · {outcome.replace(/_/g, " ")}
          </div>
        )}
      </div>
      <div className="relative">
        {/* base line */}
        <div className="absolute left-0 right-0 top-[7px] h-px bg-[var(--ss-hairline-strong)]" />
        {/* progress line */}
        <div
          className={cn(
            "absolute left-0 top-[7px] h-px transition-all duration-500",
            terminalFailed ? "bg-red-500/60" : "bg-cyan-400/70"
          )}
          style={{ width: `${(Math.max(currentIdx, 0) / (RAIL_STAGES.length - 1)) * 100}%` }}
        />
        <div className="relative flex justify-between">
          {RAIL_STAGES.map((stage, i) => {
            const reached = i <= currentIdx;
            const isActive = i === currentIdx && !isTerminal && status === "executing";
            const isCurrent = i === currentIdx;
            const dotColor = !reached
              ? "bg-slate-700 border-slate-600"
              : terminalFailed && isCurrent
              ? "bg-red-500 border-red-400 ss-glow-red"
              : isActive
              ? "bg-cyan-400 border-cyan-300 ss-pulse-cyan"
              : "bg-cyan-500/80 border-cyan-400";
            return (
              <div key={stage.key} className="flex flex-col items-start gap-1.5" style={{ width: `${100 / RAIL_STAGES.length}%` }}>
                <div className={cn("w-3.5 h-3.5 rounded-full border", dotColor)} />
                <div>
                  <div className={cn("text-[11px] font-medium", reached ? "text-slate-200" : "text-slate-500")}>
                    {stage.label}
                  </div>
                  {!compact && (
                    <div className="text-[10px] text-slate-500 ss-mono-xs tnum">
                      {stage.key === "queued" && fmt(timestamps?.queuedAt)}
                      {stage.key === "dispatching" && fmt(timestamps?.dispatchingAt)}
                      {stage.key === "executing" && fmt(timestamps?.workerStartedAt)}
                      {stage.key === "succeeded" && fmt(timestamps?.workerFinishedAt)}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// EventTimeline — vertical event stream (worker events etc.)
// ============================================================

export function EventTimeline({
  events,
  className,
}: {
  events: {
    id: string;
    at: string;
    label: string;
    kind: string;
    safeMeta?: Record<string, string>;
  }[];
  className?: string;
}) {
  if (events.length === 0) {
    return (
      <div className={cn("text-xs text-slate-500 italic py-4 text-center", className)}>
        No events recorded.
      </div>
    );
  }
  const kindTone: Record<string, { dot: string; line: string; text: string }> = {
    worker_started: { dot: "bg-cyan-400", line: "border-cyan-500/40", text: "text-cyan-300" },
    worker_finished: { dot: "bg-emerald-400", line: "border-emerald-500/40", text: "text-emerald-300" },
    failed_safely: { dot: "bg-red-400", line: "border-red-500/40", text: "text-red-300" },
    blocked_by_control: { dot: "bg-amber-400", line: "border-amber-500/40", text: "text-amber-300" },
    credential_revoked: { dot: "bg-slate-400", line: "border-slate-600/40", text: "text-slate-300" },
    dispatch_failed: { dot: "bg-red-400", line: "border-red-500/40", text: "text-red-300" },
    auth_expiry_warning: { dot: "bg-yellow-400", line: "border-yellow-500/40", text: "text-yellow-300" },
  };
  return (
    <div className={cn("relative", className)}>
      <div className="absolute left-[5px] top-1 bottom-1 w-px bg-[var(--ss-hairline-strong)]" />
      <ul className="space-y-3">
        {events.map((e) => {
          const tone = kindTone[e.kind] ?? { dot: "bg-slate-400", line: "border-slate-600/40", text: "text-slate-300" };
          const time = new Date(e.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
          return (
            <li key={e.id} className="relative pl-6">
              <span className={cn("absolute left-0 top-1 w-[11px] h-[11px] rounded-full border-2 border-[#0A111E]", tone.dot)} />
              <div className="flex items-baseline justify-between gap-3">
                <div className={cn("text-xs font-medium", tone.text)}>{e.label}</div>
                <div className="ss-mono-xs text-slate-500 tnum">{time}</div>
              </div>
              {e.safeMeta && Object.keys(e.safeMeta).length > 0 && (
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                  {Object.entries(e.safeMeta).map(([k, v]) => (
                    <span key={k} className="text-[10px] text-slate-500">
                      <span className="text-slate-600">{k}:</span>{" "}
                      <span className="ss-mono-xs text-slate-400">{v}</span>
                    </span>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ============================================================
// SecureCodeBlock — safe technical reference display
// Used for: DNS TXT challenge values, execution IDs, asset targets,
// message IDs, envelope hashes. NEVER for raw tokens.
// ============================================================

export function SecureCodeBlock({
  label,
  value,
  copyable = false,
  masked = false,
  hint,
  className,
}: {
  label?: string;
  value: string;
  copyable?: boolean;
  masked?: boolean;
  hint?: string;
  className?: string;
}) {
  const [copied, setCopied] = React.useState(false);
  const [revealed, setRevealed] = React.useState(!masked);
  const display = revealed ? value : "•".repeat(Math.min(value.length, 48));

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* no-op */
    }
  };

  return (
    <div className={cn("ss-panel-flat", className)}>
      {label && (
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--ss-hairline)]">
          <div className="ss-eyebrow">{label}</div>
          {hint && <div className="text-[10px] text-slate-500">{hint}</div>}
        </div>
      )}
      <div className="flex items-center gap-2 px-3 py-2.5">
        <code className="ss-mono-xs text-cyan-200 flex-1 break-all">{display}</code>
        {copyable && (
          <button
            onClick={copy}
            className="shrink-0 text-[10px] uppercase tracking-wider text-slate-400 hover:text-cyan-300 border border-[var(--ss-hairline-strong)] rounded-sm px-2 py-0.5 transition-colors"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
    </div>
  );
}

