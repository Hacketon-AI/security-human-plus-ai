"use client";

import * as React from "react";
import { useApp } from "@/lib/securescope/store";
import { Modal } from "../shared/ui";
import { AlertBanner } from "../shared/ui";
import { ShieldAlert, ShieldOff } from "lucide-react";

export function KillSwitchModal() {
  const target = useApp((s) => s.killSwitchTarget);
  const requestKillSwitch = useApp((s) => s.requestKillSwitch);
  const triggerKillSwitch = useApp((s) => s.triggerKillSwitch);
  const engagements = useApp((s) => s.engagements);
  const [confirming, setConfirming] = React.useState(false);
  const [reason, setReason] = React.useState("");

  const eng = engagements.find((e) => e.id === target);

  const close = () => {
    setConfirming(false);
    setReason("");
    requestKillSwitch(null);
  };

  const activate = async () => {
    if (target) {
      await triggerKillSwitch(target, true, reason);
    }
    close();
  };

  return (
    <Modal open={!!target} onClose={close} size="md">
      <div className="px-5 py-4 border-b border-(--ss-hairline-strong) flex items-center gap-2">
        <ShieldAlert className="w-4 h-4 text-amber-400" />
        <span className="text-sm font-semibold text-slate-100">Activate Kill Switch</span>
      </div>

      <div className="p-5 space-y-4">
        {eng && (
          <div className="ss-panel-flat p-3">
            <div className="ss-eyebrow mb-1">Target engagement</div>
            <div className="flex items-center justify-between">
              <code className="ss-mono text-cyan-200 text-sm">{eng.code}</code>
              <span className="text-[11px] text-slate-400">{eng.name}</span>
            </div>
          </div>
        )}

        <AlertBanner tone="warning" title="This action is destructive and audited">
          Activating the kill switch will immediately halt all in-flight executions on this engagement, revoke the active worker credential, and route any pending dispatches to the dead-letter queue.
        </AlertBanner>

        <div>
          <label className="ss-eyebrow block mb-1.5">Reason (required for audit trail)</label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="e.g. ISO review pending on step 4 evidence — staging manual hold."
            className="w-full px-3 py-2 text-xs bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/50 resize-none"
          />
        </div>

        {eng && eng.activeExecutions > 0 && (
          <div>
            <div className="ss-eyebrow mb-1.5">Affected executions ({eng.activeExecutions})</div>
            <div className="flex flex-wrap gap-1.5">
              <code className="ss-mono-xs text-amber-200 border border-amber-500/30 bg-amber-500/5 rounded-sm px-2 py-0.5">
                EXEC-2026-0702-002
              </code>
            </div>
          </div>
        )}

        <label className="flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={confirming}
            onChange={(e) => setConfirming(e.target.checked)}
            className="accent-amber-500 w-3.5 h-3.5"
          />
          I understand this will halt active executions and revoke the worker credential.
        </label>
      </div>

      <div className="px-5 py-3 border-t border-(--ss-hairline-strong) flex items-center justify-end gap-2">
        <button
          onClick={close}
          className="px-3 py-1.5 text-[11px] uppercase tracking-wider text-slate-400 hover:text-slate-200 border border-(--ss-hairline-strong) rounded-sm"
        >
          Cancel
        </button>
        <button
          onClick={activate}
          disabled={!confirming || !reason.trim()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider rounded-sm border border-amber-500/50 bg-amber-500/20 text-amber-200 hover:bg-amber-500/30 transition-all disabled:opacity-40 disabled:pointer-events-none"
        >
          <ShieldOff className="w-3.5 h-3.5" />
          Activate kill switch
        </button>
      </div>
    </Modal>
  );
}
