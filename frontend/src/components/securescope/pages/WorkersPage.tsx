"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Activity,
  ArrowRight,
  Cpu,
  GitBranch,
  Hash,
  Layers,
  Radio,
  Server,
  ServerCog,
  Shield,
  Workflow,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { Pill, StatusBadge } from "../shared/badges";
import { EmptyState, KeyValue, MaskedField } from "../shared/ui";
import { EventTimeline, SecureCodeBlock } from "../shared/lifecycle";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

export function WorkersPage() {
  const openExecution = useApp((s) => s.openExecution);
  const executions = useApp((s) => s.executions);
  const workers = useApp((s) => s.workers);
  const dispatchQueues = useApp((s) => s.dispatchQueues);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Workers · Dispatch Monitoring" }]}
          title="Dispatch & Worker Monitoring"
          description="Real-time view of the dispatch pipeline, broker state, queue depths, message lifecycle, and worker heartbeats. Sensitive internals (broker URL, raw credentials, envelope secrets) are never exposed."
          meta={
            <>
              <Pill tone="green"><span className="w-1 h-1 rounded-full bg-emerald-400 ss-pulse-green" /> Broker online</Pill>
              <Pill tone="cyan">eu-1 region</Pill>
              <Pill tone="slate">schema v1.4.0</Pill>
            </>
          }
        />

        <div className="px-4 lg:px-6 py-5 space-y-5">
          {/* Dispatch pipeline diagram */}
          <div className="ss-panel p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Workflow className="w-4 h-4 text-cyan-400" />
                <span className="text-sm font-semibold text-slate-100">Dispatch Pipeline</span>
              </div>
              <Pill tone="cyan">live</Pill>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {[
                { label: "Execution queued", icon: <Layers className="w-3.5 h-3.5" />, tone: "blue", value: "1 pending" },
                { label: "Dispatch message published", icon: <GitBranch className="w-3.5 h-3.5" />, tone: "cyan", value: "envelope v1.4.0" },
                { label: "Broker routed", icon: <Server className="w-3.5 h-3.5" />, tone: "green", value: "queue: securescope.exec.v1" },
                { label: "Worker consumed", icon: <Cpu className="w-3.5 h-3.5" />, tone: "cyan", value: "wkr-eu-1-a07" },
                { label: "Result emitted", icon: <Activity className="w-3.5 h-3.5" />, tone: "slate", value: "awaiting finish" },
              ].map((n, i) => {
                const toneMap: Record<string, string> = {
                  blue: "border-blue-500/40 text-blue-300 bg-blue-500/5",
                  cyan: "border-cyan-500/40 text-cyan-300 bg-cyan-500/5",
                  green: "border-emerald-500/40 text-emerald-300 bg-emerald-500/5",
                  slate: "border-slate-600/40 text-slate-300 bg-slate-500/5",
                };
                return (
                  <React.Fragment key={n.label}>
                    <div className={cn("ss-panel border p-3", toneMap[n.tone])}>
                      <div className="flex items-center justify-between mb-2">
                        <div className={cn("w-7 h-7 rounded-sm border flex items-center justify-center", toneMap[n.tone])}>
                          {n.icon}
                        </div>
                        <span className="ss-mono-xs text-slate-500">{i + 1}/5</span>
                      </div>
                      <div className="ss-eyebrow mb-1">Stage {i + 1}</div>
                      <div className="text-xs font-medium text-slate-200">{n.label}</div>
                      <div className="text-[10px] text-slate-500 mt-1 ss-mono-xs">{n.value}</div>
                    </div>
                    {i < 4 && (
                      <div className="hidden md:flex absolute items-center justify-center pointer-events-none">
                        <ArrowRight className="w-3 h-3 text-cyan-500/50" />
                      </div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
            <div className="mt-3 h-px relative overflow-hidden">
              <div className="absolute inset-0 bg-(--ss-hairline)" />
              <div className="absolute inset-0 ss-flow-line opacity-60" />
            </div>
          </div>

          <div className="grid lg:grid-cols-[1.3fr_1fr] gap-4">
            {/* Left: queues + workers */}
            <div className="space-y-4">
              {/* Broker status */}
              <div className="ss-panel p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <ServerCog className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-100">Broker & queue status</span>
                  </div>
                  <Pill tone="green">online</Pill>
                </div>
                <div className="space-y-2">
                  {dispatchQueues.length === 0 ? (
                    <EmptyState title="No queue data" icon={<ServerCog className="w-5 h-5" />} />
                  ) : (
                    dispatchQueues.map((q, i) => (
                    <div key={i} className="ss-panel-flat p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <code className="ss-mono-xs text-cyan-200">{q.queue_name}</code>
                          <Pill tone="slate">{q.routing_key}</Pill>
                        </div>
                        <Pill tone={q.broker_status === "online" ? "green" : "red"}>{q.broker_status}</Pill>
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <div className="ss-eyebrow">Pending</div>
                          <div className="text-lg font-semibold tnum text-blue-300">{q.pending}</div>
                        </div>
                        <div>
                          <div className="ss-eyebrow">Active</div>
                          <div className="text-lg font-semibold tnum text-cyan-300">{q.active}</div>
                        </div>
                        <div>
                          <div className="ss-eyebrow">Failed</div>
                          <div className="text-lg font-semibold tnum text-red-300">{q.failed}</div>
                        </div>
                      </div>
                    </div>
                    ))
                  )}
                </div>
                <MaskedField
                  label="Broker URL"
                  placeholder="amqp://••••••••@••••••••"
                  note="Broker connection details are never exposed. Workers authenticate via per-execution credentials."
                  className="mt-3"
                />
              </div>

              {/* Workers */}
              <div className="ss-panel p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-100">Worker fleet</span>
                  </div>
                  <Pill tone="slate">{workers.length} workers</Pill>
                </div>
                <div className="overflow-hidden border border-(--ss-hairline) rounded-sm">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-(--ss-surface-2)">
                        <th className="text-left px-3 py-2 ss-eyebrow">Worker ID</th>
                        <th className="text-left px-3 py-2 ss-eyebrow">Region</th>
                        <th className="text-left px-3 py-2 ss-eyebrow">State</th>
                        <th className="text-left px-3 py-2 ss-eyebrow">Current execution</th>
                        <th className="text-left px-3 py-2 ss-eyebrow">Last heartbeat</th>
                      </tr>
                    </thead>
                    <tbody>
                      {workers.length === 0 ? (
                        <tr><td colSpan={5} className="px-3 py-4 text-center text-slate-500 text-xs">No workers registered</td></tr>
                      ) : (
                        workers.map((w) => (
                        <tr key={w.worker_id} className={cn("border-t border-(--ss-hairline)", w.state === "running" && "bg-cyan-500/5")}>
                          <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{w.worker_id}</code></td>
                          <td className="px-3 py-2.5 ss-mono-xs text-slate-400">{w.region}</td>
                          <td className="px-3 py-2.5">
                            <Pill tone={w.state === "running" ? "cyan" : w.state === "idle" ? "slate" : w.state === "finished" ? "green" : "red"}>
                              <span className={cn("w-1 h-1 rounded-full", w.state === "running" && "bg-cyan-400 ss-pulse-cyan")} />
                              {w.state}
                            </Pill>
                          </td>
                          <td className="px-3 py-2.5">
                            {w.current_execution_id ? (
                              <button onClick={() => {
                                const exec = executions.find((e) => e.id === w.current_execution_id || e.code === w.current_execution_id);
                                if (exec) openExecution(exec.id);
                              }} className="ss-mono-xs text-cyan-200 hover:underline">
                                {w.current_execution_id}
                              </button>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5 ss-mono-xs text-slate-500">{w.last_heartbeat ? w.last_heartbeat.slice(11, 19) : "—"}</td>
                        </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Right: message lifecycle + correlation */}
            <div className="space-y-4">
              <div className="ss-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Radio className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Message lifecycle (latest)</span>
                </div>
                {(() => {
                  const exec = executions.find((e) => e.status === "executing");
                  if (!exec) return <EmptyState title="No active dispatch" icon={<Radio className="w-5 h-5" />} />;
                  return (
                    <div className="space-y-2">
                      <SecureCodeBlock label="Message ID" value={exec.dispatchMessage.messageId} copyable />
                      <div className="grid grid-cols-1 gap-y-0">
                        <KeyValue k="Queue" v={<code className="ss-mono-xs text-cyan-200">{exec.dispatchMessage.queueName}</code>} />
                        <KeyValue k="Routing key" v={exec.dispatchMessage.routingKey} mono />
                        <KeyValue k="Envelope schema" v={exec.dispatchMessage.envelopeSchemaVersion} mono />
                        <KeyValue k="Payload hash" v={<code className="ss-mono-xs text-cyan-200">{exec.dispatchMessage.payloadHash}</code>} />
                        <KeyValue k="Publish status" v={<Pill tone={exec.dispatchMessage.publishStatus === "published" ? "green" : "amber"}>{exec.dispatchMessage.publishStatus}</Pill>} />
                        <KeyValue k="Worker state" v={<Pill tone={exec.dispatchMessage.workerState === "running" ? "cyan" : "slate"}>{exec.dispatchMessage.workerState}</Pill>} />
                        <KeyValue k="Last heartbeat" v={exec.dispatchMessage.lastHeartbeat} mono />
                      </div>
                      <MaskedField
                        label="Envelope secrets"
                        placeholder="broker credentials · worker token · payload body"
                        note="All sensitive envelope fields are encrypted in transit and never logged or displayed."
                      />
                    </div>
                  );
                })()}
              </div>

              <div className="ss-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Hash className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Correlation by execution ID</span>
                </div>
                <ul className="space-y-2">
                  {executions.slice(0, 5).map((e) => (
                    <li key={e.id} onClick={() => openExecution(e.id)} className="flex items-center justify-between p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 cursor-pointer">
                      <div className="flex items-center gap-2 min-w-0">
                        <code className="ss-mono-xs text-cyan-200">{e.code}</code>
                        <span className="text-[10px] text-slate-500">→</span>
                        <code className="ss-mono-xs text-slate-500">msg_{e.id.slice(-6)}</code>
                      </div>
                      <StatusBadge status={e.status} />
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Worker event timeline */}
          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
            <div className="ss-panel p-4">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-xs font-semibold text-slate-100">Worker event timeline</span>
              </div>
              {(() => {
                const exec = executions.find((e) => e.status === "executing");
                if (!exec || exec.events.length === 0) {
                  return <EmptyState title="No worker events" icon={<Activity className="w-5 h-5" />} />;
                }
                return <EventTimeline events={exec.events} />;
              })()}
            </div>

            <div className="ss-panel p-4">
              <div className="flex items-center gap-2 mb-3">
                <Shield className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-semibold text-slate-100">Failed dispatch alerts</span>
              </div>
              {dispatchQueues.length === 0 ? (
                <EmptyState title="No dispatch data" icon={<Shield className="w-5 h-5" />} />
              ) : (
                <div className="mt-3 ss-panel-flat p-3">
                  <div className="ss-eyebrow mb-1.5">Dispatch outcomes (24h)</div>
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div>
                      <div className="text-lg font-semibold tnum text-emerald-300">{(dispatchQueues[0].active ?? 0) + (dispatchQueues[0].pending ?? 0)}</div>
                      <div className="ss-eyebrow">published</div>
                    </div>
                    <div>
                      <div className="text-lg font-semibold tnum text-cyan-300">{dispatchQueues[0].active ?? 0}</div>
                      <div className="ss-eyebrow">consumed</div>
                    </div>
                    <div>
                      <div className="text-lg font-semibold tnum text-amber-300">{dispatchQueues[0].failed ?? 0}</div>
                      <div className="ss-eyebrow">dead-lettered</div>
                    </div>
                    <div>
                      <div className="text-lg font-semibold tnum text-slate-400">0</div>
                      <div className="ss-eyebrow">lost</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
