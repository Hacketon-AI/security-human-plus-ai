"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  BrainCircuit,
  ShieldCheck,
  Target,
  Zap,
  Activity,
  AlertTriangle,
  Play,
  Cpu,
  Share2,
  Layers,
  Database,
  Terminal,
  Shield,
  Eye,
  CheckCircle2,
  Lock,
  Route,
  Server
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { Pill, StatusBadge } from "../shared/badges";
import { CyberButton, EmptyState } from "../shared/ui";
import { AIProofOfRiskResponse } from "@/lib/securescope/aiProofOfRiskApi";
import { runDomainSafeScan, DomainSafeScanResponse } from "@/lib/securescope/domainSafeScanApi";

// Helper to safely navigate to AI Proof of Risk tab
function useRunDemoCta() {
  const executions = useApp(s => s.executions);
  const openExecution = useApp(s => s.openExecution);
  const latestAiId = useApp(s => s.latestAiProofOfRiskExecutionId);

  return (tab: string = "AI Proof-of-Risk") => {
    if (latestAiId) {
      openExecution(latestAiId, tab);
      return;
    }
    const running = executions.find(e => e.status === "executing");
    if (running) {
      openExecution(running.id, tab);
      return;
    }
    const anyExec = executions[0];
    if (anyExec) {
      openExecution(anyExec.id, tab);
      return;
    }
    // Fallback to mock execution ID if none exist
    openExecution("00000000-0000-0000-0000-000000000000", tab);
  };
}

export function AiProofOfRiskCommandStrip() {
  const analysis = useApp(s => s.latestAiProofOfRiskAnalysis) as AIProofOfRiskResponse | null;
  const isMock = process.env.NEXT_PUBLIC_USE_MOCK_API === "true";

  const routing = analysis?.routing_details;
  
  const items = [
    { label: "AI Proof-of-Risk", value: analysis ? "Active" : "Ready", tone: "cyan" as const, hint: analysis ? "latest analysis loaded" : "demo config" },
    { label: "Router Mode", value: "Hybrid", tone: "cyan" as const, hint: routing?.fallback_used ? "fallback engaged" : "dynamic" },
    { label: "AMD ROCm Local", value: routing?.local_provider_available ? "Available" : (isMock ? "Mocked" : "Unconfigured"), tone: routing?.local_provider_available || isMock ? "green" as const : "slate" as const, hint: "gemma-local" },
    { label: "Fireworks/Gemma", value: routing?.remote_provider_available ? "Available" : (isMock ? "Mocked" : "Unconfigured"), tone: routing?.remote_provider_available || isMock ? "green" as const : "slate" as const, hint: "gemma-2-9b-it" },
    { label: "Sandbox Sim", value: analysis?.sandbox_proof_artifacts?.length ? "Active" : "Disabled", tone: analysis?.sandbox_proof_artifacts?.length ? "amber" as const : "slate" as const, hint: "digital twin" },
    { label: "Container Demo", value: isMock ? "Mocked" : "Live", tone: isMock ? "amber" as const : "green" as const, hint: "hackathon" },
  ];

  return (
    <div className="border-b border-(--ss-hairline-strong) bg-[#050810]/80 sticky top-[60px] z-10 backdrop-blur-md">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 divide-x divide-(--ss-hairline)">
        {items.map((it) => (
          <div key={it.label} className="p-3 px-4 relative group overflow-hidden">
            <div className="flex items-start justify-between mb-1 relative z-10">
              <span className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{it.label}</span>
              <span className="text-[9px] ss-mono-xs text-slate-600 truncate ml-2 max-w-[80px] text-right">{it.hint}</span>
            </div>
            <div className="flex items-center gap-2 relative z-10">
              <div className={cn(
                "w-1.5 h-1.5 rounded-full shrink-0",
                it.tone === "green" ? "bg-emerald-400 ss-pulse-green" :
                it.tone === "cyan" ? "bg-cyan-400 ss-pulse-cyan" :
                it.tone === "amber" ? "bg-amber-400" :
                "bg-slate-500"
              )} />
              <span className={cn(
                "text-sm font-semibold tracking-tight",
                it.tone === "green" ? "text-emerald-300" :
                it.tone === "cyan" ? "text-cyan-300" :
                it.tone === "amber" ? "text-amber-300" :
                "text-slate-300"
              )}>{it.value}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DashboardQuickActions() {
  const runDemo = useRunDemoCta();

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <CyberButton size="sm" variant="primary" onClick={() => runDemo("AI Proof-of-Risk")}>
        <Play className="w-3 h-3 mr-1.5" /> AI Proof-of-Risk
      </CyberButton>
      <CyberButton size="sm" variant="ghost" onClick={() => runDemo("AI Proof-of-Risk")}>
        <Share2 className="w-3 h-3 mr-1.5" /> Attack Graph
      </CyberButton>
      <CyberButton size="sm" variant="ghost" onClick={() => runDemo("AI Proof-of-Risk")}>
        <Layers className="w-3 h-3 mr-1.5" /> Digital Twin
      </CyberButton>
      <CyberButton size="sm" variant="ghost" onClick={() => runDemo("AI Proof-of-Risk")}>
        <ShieldCheck className="w-3 h-3 mr-1.5" /> Remediation
      </CyberButton>
    </div>
  );
}

export function AiProofOfRiskWorkflowRail() {
  const runDemo = useRunDemoCta();
  const stages = [
    { label: "Execution Evidence", desc: "Normalized telemetry" },
    { label: "Redaction", desc: "Fail-closed scrub" },
    { label: "AI Router", desc: "Hybrid dispatch" },
    { label: "Attack Graph", desc: "Surface mapping" },
    { label: "Digital Twin", desc: "Sandbox scenario" },
    { label: "Sandbox Proof", desc: "Safe exploitation" },
    { label: "Risk Tribunal", desc: "Multi-agent verdict" },
    { label: "Remediation", desc: "Actionable fix" },
    { label: "Retest", desc: "Validation plan" }
  ];

  return (
    <div className="ss-panel p-4 overflow-x-auto">
      <div className="flex items-center justify-between mb-4 min-w-max">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-slate-100">AI Proof-of-Risk Workflow Pipeline</h2>
        </div>
        <CyberButton size="sm" variant="primary" onClick={runDemo}>
          <Play className="w-3 h-3 mr-1.5" /> Run AI Proof-of-Risk Demo
        </CyberButton>
      </div>
      <div className="flex items-center min-w-max pb-2">
        {stages.map((stage, idx) => (
          <React.Fragment key={stage.label}>
            <button 
              onClick={runDemo}
              className="flex flex-col items-center group text-center w-28 hover:bg-(--ss-surface-2) p-2 rounded transition-colors border border-transparent hover:border-(--ss-hairline)"
            >
              <div className="w-8 h-8 rounded-full bg-(--ss-surface-2) border border-cyan-500/30 flex items-center justify-center mb-2 group-hover:bg-cyan-900/30 group-hover:border-cyan-500 transition-colors">
                <span className="text-xs font-mono text-cyan-400">{idx + 1}</span>
              </div>
              <span className="text-[11px] font-semibold text-slate-200 group-hover:text-cyan-300 mb-1">{stage.label}</span>
              <span className="text-[9px] text-slate-500 leading-tight px-1">{stage.desc}</span>
            </button>
            {idx < stages.length - 1 && (
              <div className="flex-1 h-px bg-slate-700 min-w-[20px] mx-1">
                <div className="w-full h-full bg-cyan-500/50 scale-x-0 group-hover:scale-x-100 transition-transform origin-left" />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

export function AiRoutingPipelinePanel() {
  const analysis = useApp(s => s.latestAiProofOfRiskAnalysis) as AIProofOfRiskResponse | null;
  const routing = analysis?.routing_details;

  if (!routing) {
    return (
      <EmptyState
        eyebrow="AI Routing Pipeline"
        title="No routing telemetry"
        description="Run AI Proof-of-Risk analysis from an execution to populate routing telemetry."
        icon={<Route className="w-6 h-6 text-slate-400" />}
      />
    );
  }

  return (
    <div className="ss-panel p-4 h-full flex flex-col border-t-2 border-indigo-500">
      <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
        <Route className="w-4 h-4 text-indigo-400" />
        <h3 className="text-sm font-semibold text-slate-100">AI Routing Pipeline</h3>
      </div>
      
      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="bg-(--ss-surface-1) p-2 rounded border border-(--ss-hairline)">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Selected Route</div>
          <div className="text-[11px] text-indigo-300 font-mono truncate">{routing.selected_route}</div>
        </div>
        <div className="bg-(--ss-surface-1) p-2 rounded border border-(--ss-hairline)">
          <div className="text-[10px] uppercase tracking-wider text-emerald-500 mb-1">Tokens Saved</div>
          <div className="text-[11px] text-emerald-300 font-mono">{routing.token_saving_estimate || 0}</div>
        </div>
      </div>
      
      <div className="flex flex-col gap-2 flex-1">
        <div className={cn("flex justify-between items-center p-2 rounded border text-xs", routing.attempted_local_call ? "bg-cyan-900/20 border-cyan-500/50 text-cyan-200" : "bg-(--ss-surface-1) border-(--ss-hairline) text-slate-400")}>
          <span>AMD ROCm Local</span>
          <span className="font-mono">{routing.attempted_local_call ? "Attempted" : "Bypassed"}</span>
        </div>
        <div className={cn("flex justify-between items-center p-2 rounded border text-xs", routing.attempted_remote_call ? "bg-indigo-900/20 border-indigo-500/50 text-indigo-200" : "bg-(--ss-surface-1) border-(--ss-hairline) text-slate-400")}>
          <span>Fireworks/Gemma</span>
          <span className="font-mono">{routing.attempted_remote_call ? "Attempted" : (routing.avoided_remote_call ? "Avoided (Saved)" : "Bypassed")}</span>
        </div>
        <div className={cn("flex justify-between items-center p-2 rounded border text-xs", routing.fallback_used ? "bg-amber-900/20 border-amber-500/50 text-amber-200" : "bg-(--ss-surface-1) border-(--ss-hairline) text-slate-400")}>
          <span>Deterministic Fallback</span>
          <span className="font-mono">{routing.fallback_used ? "Engaged" : "Standby"}</span>
        </div>
      </div>
    </div>
  );
}

export function AttackSurfacePreviewPanel() {
  const runDemo = useRunDemoCta();
  const analysis = useApp(s => s.latestAiProofOfRiskAnalysis) as AIProofOfRiskResponse | null;
  const graph = analysis?.attack_surface_graph;

  if (!graph) {
    return (
      <EmptyState
        eyebrow="Attack Surface Graph"
        title="No surface data"
        description="Run an analysis to generate the attack surface graph."
        icon={<Share2 className="w-6 h-6 text-slate-400" />}
        action={<CyberButton size="sm" onClick={runDemo}>Run Analysis</CyberButton>}
      />
    );
  }

  const nodes = graph.nodes.length;
  const edges = graph.edges.length;
  const topFinding = graph.nodes.find(n => n.type === 'finding')?.label || 'N/A';
  const topControl = graph.nodes.find(n => n.type === 'missing_control')?.label || 'N/A';

  return (
    <div className="ss-panel p-4 h-full flex flex-col border-t-2 border-cyan-500">
      <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
        <Share2 className="w-4 h-4 text-cyan-400" />
        <h3 className="text-sm font-semibold text-slate-100">Attack Surface Preview</h3>
      </div>
      
      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline) flex items-center justify-between">
          <span className="text-xs text-slate-400">Nodes</span>
          <span className="text-sm text-cyan-300 font-mono">{nodes}</span>
        </div>
        <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline) flex items-center justify-between">
          <span className="text-xs text-slate-400">Edges</span>
          <span className="text-sm text-cyan-300 font-mono">{edges}</span>
        </div>
      </div>
      
      <div className="space-y-2 flex-1">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Top Finding</div>
        <div className="text-xs text-amber-300 truncate bg-amber-900/10 border border-amber-900/30 p-2 rounded">{topFinding}</div>
        
        <div className="text-[11px] uppercase tracking-wider text-slate-500 mt-2">Missing Control</div>
        <div className="text-xs text-red-300 truncate bg-red-900/10 border border-red-900/30 p-2 rounded">{topControl}</div>
      </div>
      
      <div className="mt-4 pt-2 border-t border-(--ss-hairline)">
        <CyberButton size="sm" variant="ghost" onClick={runDemo} className="w-full justify-center">
          View Full Graph →
        </CyberButton>
      </div>
    </div>
  );
}

export function DigitalTwinProofPanel() {
  const analysis = useApp(s => s.latestAiProofOfRiskAnalysis) as AIProofOfRiskResponse | null;
  const scenarios = analysis?.digital_twin_scenarios || [];
  const artifacts = analysis?.sandbox_proof_artifacts || [];

  if (!analysis) {
    return (
      <EmptyState
        eyebrow="Digital Twin Proof"
        title="Sandbox Proof Disabled"
        description="Sandbox proof is disabled by default. Enable only for controlled demo configuration."
        icon={<Layers className="w-6 h-6 text-slate-400" />}
      />
    );
  }

  return (
    <div className="ss-panel p-4 h-full flex flex-col border-t-2 border-emerald-500">
      <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
        <Layers className="w-4 h-4 text-emerald-400" />
        <h3 className="text-sm font-semibold text-slate-100">Digital Twin Proofs</h3>
      </div>
      
      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline) flex items-center justify-between">
          <span className="text-xs text-slate-400">Scenarios</span>
          <span className="text-sm text-emerald-300 font-mono">{scenarios.length}</span>
        </div>
        <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline) flex items-center justify-between">
          <span className="text-xs text-slate-400">Artifacts</span>
          <span className="text-sm text-emerald-300 font-mono">{artifacts.length}</span>
        </div>
      </div>
      
      <div className="bg-(--ss-surface-1) p-3 rounded border border-emerald-900/30 flex-1">
        <div className="flex items-center gap-2 mb-2">
          <Lock className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold text-emerald-300">Safety Boundaries</span>
        </div>
        <ul className="space-y-2 mt-3">
          <li className="flex justify-between items-center text-[11px]">
            <span className="text-slate-400">Production Exploit Allowed</span>
            <span className="text-emerald-400 font-mono">FALSE</span>
          </li>
          <li className="flex justify-between items-center text-[11px]">
            <span className="text-slate-400">Production Target Used</span>
            <span className="text-emerald-400 font-mono">FALSE</span>
          </li>
          <li className="flex justify-between items-center text-[11px]">
            <span className="text-slate-400">Sandbox Isolation</span>
            <span className="text-emerald-400 font-mono">ENFORCED</span>
          </li>
        </ul>
      </div>
    </div>
  );
}

export function MultiAgentTribunalPanel() {
  const analysis = useApp(s => s.latestAiProofOfRiskAnalysis) as AIProofOfRiskResponse | null;
  const tribunal = analysis?.tribunal_verdict;

  if (!tribunal) {
    return (
      <EmptyState
        eyebrow="Risk Tribunal"
        title="Multi-Agent Risk Tribunal"
        description="Run analysis to see autonomous agent debate."
        icon={<Cpu className="w-6 h-6 text-slate-400" />}
      />
    );
  }

  return (
    <div className="ss-panel p-4 h-full flex flex-col border-t-2 border-amber-500">
      <div className="flex items-center justify-between mb-4 border-b border-(--ss-hairline) pb-2">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-slate-100">Risk Tribunal</h3>
        </div>
        <Pill tone={tribunal.severity === 'Critical' || tribunal.severity === 'High' ? 'danger' : 'warning'}>
          Sev: {tribunal.severity}
        </Pill>
      </div>

      <div className="grid grid-cols-2 gap-2 flex-1">
        <div className="bg-(--ss-surface-1) p-2 rounded border border-red-900/30">
          <div className="flex items-center gap-1 mb-1">
            <Terminal className="w-3 h-3 text-red-400" />
            <span className="text-[10px] font-semibold text-red-400">Attacker</span>
          </div>
          <div className="text-[10px] text-slate-300 line-clamp-2">{tribunal.attacker_view}</div>
        </div>
        <div className="bg-(--ss-surface-1) p-2 rounded border border-blue-900/30">
          <div className="flex items-center gap-1 mb-1">
            <Shield className="w-3 h-3 text-blue-400" />
            <span className="text-[10px] font-semibold text-blue-400">Defender</span>
          </div>
          <div className="text-[10px] text-slate-300 line-clamp-2">{tribunal.defender_view}</div>
        </div>
        <div className="bg-(--ss-surface-1) p-2 rounded border border-purple-900/30">
          <div className="flex items-center gap-1 mb-1">
            <Database className="w-3 h-3 text-purple-400" />
            <span className="text-[10px] font-semibold text-purple-400">Lab</span>
          </div>
          <div className="text-[10px] text-slate-300 line-clamp-2">{tribunal.lab_view}</div>
        </div>
        <div className="bg-slate-800 p-2 rounded border border-amber-500/50 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-1 opacity-20">
            <Eye className="w-6 h-6 text-amber-400" />
          </div>
          <div className="flex items-center gap-1 mb-1">
            <Eye className="w-3 h-3 text-amber-400" />
            <span className="text-[10px] font-semibold text-amber-400">Judge</span>
          </div>
          <div className="text-[10px] font-semibold text-white line-clamp-2">{tribunal.judge_verdict}</div>
        </div>
      </div>
    </div>
  );
}

export function AuthorizedDomainScanPanel() {
  const [domain, setDomain] = React.useState("");
  const [scheme, setScheme] = React.useState("https");
  const [authorized, setAuthorized] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const globalResult = useApp(s => s.latestDomainSafeScanResult);
  const globalDomain = useApp(s => s.latestDomainSafeScanDomain);
  const setDomainSafeScanResult = useApp(s => s.setDomainSafeScanResult);
  const clearDomainSafeScanResult = useApp(s => s.clearDomainSafeScanResult);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!domain || !authorized) return;
    
    setLoading(true);
    setError(null);
    clearDomainSafeScanResult();

    try {
      const res = await runDomainSafeScan({
        domain: domain.trim(),
        scheme,
        confirm_authorized: authorized,
        scan_type: "http_security_headers",
        run_ai_proof_of_risk: true
      });
      setDomainSafeScanResult(domain.trim(), res);
    } catch (err: any) {
      setError(err.message || "Failed to run scan");
    } finally {
      setLoading(false);
    }
  };

  const isButtonDisabled = !domain || !authorized || loading;
  let disabledReason = "";
  if (!domain) disabledReason = "Domain is required.";
  else if (!authorized) disabledReason = "Please confirm you own this domain or have written permission.";

  return (
    <div className="ss-panel p-4 h-full flex flex-col border-t-2 border-indigo-500 overflow-hidden relative">
      <div className="flex items-center gap-2 mb-2 border-b border-(--ss-hairline) pb-2">
        <ShieldCheck className="w-4 h-4 text-indigo-400" />
        <h3 className="text-sm font-semibold text-slate-100">Real Authorized Scan</h3>
      </div>
      <div className="text-[10px] text-indigo-300/80 mb-4 pb-2 border-b border-(--ss-hairline) border-dashed">
        Using live HTTP response headers from the submitted authorized domain.<br />
        <span className="font-semibold text-indigo-300">Non-destructive: headers only, no body, no exploit.</span>
      </div>
      
      <div className="flex-1 overflow-y-auto pr-2">
        {!globalResult ? (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex gap-2">
              <div className="flex flex-col gap-1 w-24 shrink-0">
                <label className="text-[10px] uppercase tracking-wider text-slate-500">Scheme</label>
                <select 
                  value={scheme} 
                  onChange={(e) => setScheme(e.target.value)}
                  className="bg-(--ss-surface-1) border border-(--ss-hairline) rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 h-[34px]"
                >
                  <option value="https">HTTPS</option>
                  <option value="http">HTTP</option>
                </select>
              </div>
              <div className="flex flex-col gap-1 flex-1">
                <label className="text-[10px] uppercase tracking-wider text-slate-500">Domain</label>
                <input 
                  type="text" 
                  value={domain} 
                  onChange={(e) => setDomain(e.target.value)} 
                  placeholder="example.com"
                  className="bg-(--ss-surface-1) border border-(--ss-hairline) rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 h-[34px] font-mono"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-slate-500">Scan Type</label>
              <input 
                type="text" 
                value="HTTP Security Headers Only" 
                disabled 
                className="bg-(--ss-surface-1)/50 border border-(--ss-hairline) rounded px-2 py-1.5 text-xs text-slate-500 cursor-not-allowed h-[34px]"
              />
            </div>

            <label className="flex items-start gap-2 mt-2 cursor-pointer group">
              <div className="relative flex items-center justify-center mt-0.5">
                <input 
                  type="checkbox" 
                  checked={authorized}
                  onChange={(e) => setAuthorized(e.target.checked)}
                  className="peer sr-only"
                />
                <div className="w-4 h-4 rounded border border-slate-600 bg-(--ss-surface-1) peer-checked:bg-indigo-500 peer-checked:border-indigo-500 transition-colors flex items-center justify-center">
                  <CheckCircle2 className="w-3 h-3 text-white opacity-0 peer-checked:opacity-100 transition-opacity" />
                </div>
              </div>
              <span className="text-xs text-slate-400 group-hover:text-slate-300 leading-tight transition-colors">
                I confirm I own this domain or have written permission to test it.
              </span>
            </label>

            <div className="text-[10px] text-slate-500 italic mt-1 pb-2">
              SecureScope performs non-destructive authorized validation only. This demo does not exploit production systems.
            </div>

            {error && (
              <div className="text-xs text-red-400 bg-red-900/10 border border-red-900/30 p-2 rounded flex items-start gap-2">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <div className="mt-auto pt-4 flex items-center justify-between">
              <span className="text-[10px] text-amber-500">{disabledReason && !loading ? disabledReason : ""}</span>
              <CyberButton 
                variant="primary" 
                size="sm" 
                disabled={isButtonDisabled} 
                type="submit"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full border-2 border-slate-300 border-t-indigo-500 animate-spin" />
                    Scanning...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Activity className="w-3.5 h-3.5" />
                    Run Safe Scan
                  </span>
                )}
              </CyberButton>
            </div>
          </form>
        ) : (
          <div className="flex flex-col gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <StatusBadge status={globalResult.scan_result?.status === "completed" ? "succeeded" : "failed"} />
                <span className="text-xs font-mono text-slate-400">{globalDomain}</span>
              </div>
              <CyberButton variant="ghost" size="sm" onClick={() => clearDomainSafeScanResult()}>
                New Scan
              </CyberButton>
            </div>

            <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
              <div className="flex items-center gap-2 mb-2">
                <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-[11px] uppercase tracking-wider text-slate-500">AI Summary</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">{globalResult.ai_analysis_summary || "No AI summary available."}</p>
            </div>

            {globalResult.scan_result?.found_headers && Object.keys(globalResult.scan_result.found_headers).length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-[11px] uppercase tracking-wider text-slate-500">Found Headers</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.keys(globalResult.scan_result.found_headers).map(h => (
                    <div key={h} className="text-[10px] font-mono text-emerald-300 bg-emerald-900/20 border border-emerald-900/40 px-2 py-1 rounded">
                      {h}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {globalResult.scan_result?.missing_headers && globalResult.scan_result.missing_headers.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                  <span className="text-[11px] uppercase tracking-wider text-slate-500">Missing Headers</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {globalResult.scan_result.missing_headers.map((h: string) => (
                    <div key={h} className="text-[10px] font-mono text-amber-300 bg-amber-900/20 border border-amber-900/40 px-2 py-1 rounded">
                      {h}
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {globalResult.scan_result?.missing_headers?.length === 0 && (
              <div className="text-xs text-emerald-400 bg-emerald-900/10 border border-emerald-900/30 p-2 rounded flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5" />
                All standard security headers are present.
              </div>
            )}
            
            {globalResult.attack_graph ? (
              <div className="mt-2 border-t border-(--ss-hairline) pt-4">
                 <div className="flex items-center gap-2 mb-2">
                    <Share2 className="w-3.5 h-3.5 text-indigo-400" />
                    <span className="text-[11px] uppercase tracking-wider text-slate-500">Attack Graph Preview Nodes</span>
                 </div>
                 <div className="text-xs text-indigo-300 font-mono">
                    {globalResult.attack_graph.nodes?.length || 0} nodes generated
                 </div>
              </div>
            ) : (
              <div className="mt-2 border-t border-(--ss-hairline) pt-4">
                <div className="text-xs text-slate-400 bg-slate-900/20 border border-slate-700/50 p-2 rounded flex items-center gap-2">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  AI graph not available yet. Scan findings were still captured successfully.
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
