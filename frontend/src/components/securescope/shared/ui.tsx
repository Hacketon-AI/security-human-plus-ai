"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { AlertTriangle, Info, ShieldAlert, ShieldCheck, X } from "lucide-react";

// ============================================================
// Alert banners
// ============================================================

export function AlertBanner({
  tone = "info",
  title,
  children,
  className,
  onClose,
}: {
  tone?: "info" | "warning" | "danger" | "success" | "amber";
  title: string;
  children?: React.ReactNode;
  className?: string;
  onClose?: () => void;
}) {
  const tones = {
    info: {
      border: "border-cyan-500/30",
      bg: "bg-cyan-500/5",
      text: "text-cyan-200",
      icon: <Info className="w-4 h-4 text-cyan-400" />,
    },
    warning: {
      border: "border-amber-500/30",
      bg: "bg-amber-500/5",
      text: "text-amber-200",
      icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
    },
    amber: {
      border: "border-amber-500/30",
      bg: "bg-amber-500/5",
      text: "text-amber-200",
      icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
    },
    danger: {
      border: "border-red-500/30",
      bg: "bg-red-500/5",
      text: "text-red-200",
      icon: <ShieldAlert className="w-4 h-4 text-red-400" />,
    },
    success: {
      border: "border-emerald-500/30",
      bg: "bg-emerald-500/5",
      text: "text-emerald-200",
      icon: <ShieldCheck className="w-4 h-4 text-emerald-400" />,
    },
  } as const;
  const t = tones[tone] ?? tones.info;
  return (
    <div className={cn("flex items-start gap-3 px-3 py-2.5 border rounded-sm", t.border, t.bg, className)}>
      <div className="mt-0.5 shrink-0">{t.icon}</div>
      <div className="flex-1 min-w-0">
        <div className={cn("text-xs font-semibold", t.text)}>{title}</div>
        {children && <div className="text-[11px] text-slate-400 mt-0.5">{children}</div>}
      </div>
      {onClose && (
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

// ============================================================
// Empty state
// ============================================================

export function EmptyState({
  eyebrow,
  title,
  description,
  action,
  className,
  icon,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className={cn("ss-panel-flat p-8 flex flex-col items-center justify-center text-center", className)}>
      {icon && <div className="text-slate-600 mb-3">{icon}</div>}
      {eyebrow && <div className="ss-eyebrow mb-1">{eyebrow}</div>}
      <div className="text-sm font-semibold text-slate-200">{title}</div>
      {description && <div className="text-xs text-slate-500 mt-1 max-w-sm">{description}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ============================================================
// Loading skeleton
// ============================================================

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("bg-(--ss-surface-3)/60 ss-scan rounded-sm", className)} />;
}

export function LoadingPanel({ label = "Initializing subsystem", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("ss-panel-flat p-6 flex items-center gap-3", className)}>
      <div className="w-4 h-4 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
      <div>
        <div className="text-xs text-slate-300 font-medium">{label}</div>
        <div className="text-[10px] text-slate-500 ss-mono-xs">establishing secure channel · awaiting worker heartbeat</div>
      </div>
    </div>
  );
}

// ============================================================
// Modal / Confirmation dialog
// ============================================================

export function Modal({
  open,
  onClose,
  children,
  className,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;
  const sizes = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl" };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-[#040711]/80 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        className={cn(
          "relative ss-panel-raised w-full shadow-2xl",
          sizes[size],
          className
        )}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </div>
    </div>
  );
}

// ============================================================
// MonoRef — small inline mono reference
// ============================================================

export function MonoRef({ children, className }: { children: React.ReactNode; className?: string }) {
  return <code className={cn("ss-mono-xs text-cyan-200", className)}>{children}</code>;
}

// ============================================================
// KeyValue grid
// ============================================================

export function KeyValue({ k, v, mono = false, className }: { k: string; v: React.ReactNode; mono?: boolean; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3 py-1.5 border-b border-(--ss-hairline) last:border-b-0", className)}>
      <span className="text-[11px] text-slate-500 uppercase tracking-wide shrink-0">{k}</span>
      <span className={cn("text-xs text-slate-200 text-right", mono && "ss-mono-xs tnum")}>{v}</span>
    </div>
  );
}

// ============================================================
// Button (cyber variant)
// ============================================================

export function CyberButton({
  children,
  onClick,
  variant = "default",
  size = "md",
  className,
  disabled,
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "danger" | "ghost" | "amber";
  size?: "sm" | "md";
  className?: string;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const variants = {
    default: "bg-(--ss-surface-3) hover:bg-(--ss-surface-4) text-slate-200 border border-(--ss-hairline-strong)",
    primary: "bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-200 border border-cyan-400/40 hover:ss-glow-cyan",
    danger: "bg-red-500/15 hover:bg-red-500/25 text-red-200 border border-red-400/40",
    amber: "bg-amber-500/15 hover:bg-amber-500/25 text-amber-200 border border-amber-400/40",
    ghost: "bg-transparent hover:bg-(--ss-surface-3) text-slate-300 border border-transparent",
  };
  const sizes = { sm: "px-2.5 py-1 text-[11px]", md: "px-3.5 py-1.5 text-xs" };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-sm font-medium uppercase tracking-wider transition-all disabled:opacity-40 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className
      )}
    >
      {children}
    </button>
  );
}

// ============================================================
// MaskedField — for sensitive-looking values that must never be revealed
// ============================================================

export function MaskedField({
  label,
  placeholder = "••••••••••••••••",
  note,
  className,
}: {
  label: string;
  placeholder?: string;
  note?: string;
  className?: string;
}) {
  return (
    <div className={cn("ss-panel-flat", className)}>
      <div className="px-3 py-1.5 border-b border-(--ss-hairline) flex items-center justify-between">
        <div className="ss-eyebrow">{label}</div>
        <span className="text-[10px] text-amber-400/80 uppercase tracking-wider">Restricted</span>
      </div>
      <div className="px-3 py-2.5 flex items-center gap-2">
        <code className="ss-mono-xs text-slate-500 flex-1">{placeholder}</code>
        <span className="shrink-0 text-[10px] uppercase tracking-wider text-slate-500 border border-(--ss-hairline-strong) rounded-sm px-2 py-0.5">
          Hidden
        </span>
      </div>
      {note && <div className="px-3 pb-2.5 text-[10px] text-slate-500">{note}</div>}
    </div>
  );
}
