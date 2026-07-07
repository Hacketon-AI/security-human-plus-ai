"use client";

import * as React from "react";
import { BrainCircuit, Play, AlertTriangle, ShieldCheck, FileCheck2, Database, Code, CheckCircle2, Lock, Route, Box, Share2, Eye, Server, Cpu, Layers } from "lucide-react";
import { ValidationExecution } from "@/lib/securescope/types";
import {
  analyzeProofOfRisk,
  AIProofOfRiskRequest,
  AIProofOfRiskResponse,
  AIAnalysisMode
} from "@/lib/securescope/aiProofOfRiskApi";
import { CyberButton, AlertBanner } from "../shared/ui";
import { StatusBadge, Pill } from "../shared/badges";

interface AiProofOfRiskTabProps {
  exec: ValidationExecution;
}

export function AiProofOfRiskTab({ exec }: AiProofOfRiskTabProps) {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<AIProofOfRiskResponse | null>(null);

  // Form State
  const [mode, setMode] = React.useState<AIAnalysisMode>("full_report");
  const [audience, setAudience] = React.useState("security_engineer");
  const [includeSanitizedEvidence, setIncludeSanitizedEvidence] = React.useState(true);
  const [allowSandboxSimulation, setAllowSandboxSimulation] = React.useState(false);
  const [forceRemoteReasoning, setForceRemoteReasoning] = React.useState(false);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const payload: AIProofOfRiskRequest = {
        analysis_mode: mode,
        audience,
        include_sanitized_evidence: includeSanitizedEvidence,
        allow_sandbox_simulation: allowSandboxSimulation,
        force_remote_reasoning: forceRemoteReasoning,
      };
      const data = await analyzeProofOfRisk(exec.id, payload);
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to run AI analysis");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Configuration Panel */}
      <div className="ss-panel p-4">
        <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-3">
          <BrainCircuit className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-semibold text-slate-100">AI Proof-of-Risk Analysis</h2>
        </div>

        <AlertBanner tone="info" title="Security Boundary Notice" className="mb-4">
          SecureScope analyzes validated execution evidence only. It does not accept arbitrary target URLs or raw evidence from the UI.
        </AlertBanner>

        <div className="grid lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Analysis Mode</label>
              <select 
                className="w-full bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm text-sm p-2 text-slate-200 outline-none focus:border-cyan-500/50"
                value={mode} 
                onChange={e => setMode(e.target.value as AIAnalysisMode)}
              >
                <option value="full_report">Full Report</option>
                <option value="quick_summary">Quick Summary</option>
                <option value="tribunal_only">Tribunal Only</option>
                <option value="graph_only">Graph Only</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Target Audience</label>
              <select 
                className="w-full bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm text-sm p-2 text-slate-200 outline-none focus:border-cyan-500/50"
                value={audience} 
                onChange={e => setAudience(e.target.value)}
              >
                <option value="security_engineer">Security Engineer</option>
                <option value="executive">Executive</option>
                <option value="developer">Developer</option>
              </select>
            </div>
          </div>

          <div className="space-y-4">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300 hover:text-white transition-colors">
              <input 
                type="checkbox" 
                checked={includeSanitizedEvidence} 
                onChange={e => setIncludeSanitizedEvidence(e.target.checked)} 
                className="accent-cyan-500 w-4 h-4 bg-(--ss-surface-1) border-(--ss-hairline)"
              />
              Include Sanitized Evidence
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300 hover:text-white transition-colors">
              <input 
                type="checkbox" 
                checked={allowSandboxSimulation} 
                onChange={e => setAllowSandboxSimulation(e.target.checked)} 
                className="accent-cyan-500 w-4 h-4 bg-(--ss-surface-1) border-(--ss-hairline)"
              />
              Allow Sandbox Simulation (Digital Twin)
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300 hover:text-white transition-colors">
              <input 
                type="checkbox" 
                checked={forceRemoteReasoning} 
                onChange={e => setForceRemoteReasoning(e.target.checked)} 
                className="accent-cyan-500 w-4 h-4 bg-(--ss-surface-1) border-(--ss-hairline)"
              />
              Force Remote Reasoning (Bypass Local Mock/AMD)
            </label>
          </div>
        </div>

        <div className="mt-6 flex justify-end border-t border-(--ss-hairline) pt-4">
          <CyberButton variant="primary" onClick={handleAnalyze} disabled={loading || !exec.id}>
            {loading ? <span className="animate-pulse">Analyzing...</span> : <><Play className="w-4 h-4 mr-1" /> Run AI Analysis</>}
          </CyberButton>
        </div>
      </div>

      {error && (
        <AlertBanner tone="danger" title="Analysis Failed">
          {error}
        </AlertBanner>
      )}

      {loading && (
        <div className="ss-panel p-12 flex flex-col items-center justify-center text-slate-400 space-y-4">
          <BrainCircuit className="w-8 h-8 text-cyan-500/50 animate-pulse" />
          <div className="text-sm">Synthesizing execution evidence...</div>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          {process.env.NEXT_PUBLIC_USE_MOCK_API === "true" && (
            <AlertBanner tone="warning" title="Mock Mode Active">
              The AI Proof-of-Risk API is currently running in mock mode. Real analysis is not performed.
            </AlertBanner>
          )}

          {/* Safety Statement Banner */}
          {(result.safety_notes && result.safety_notes.length > 0) && (
            <AlertBanner tone="success" title="Safety Enforcement Active">
              {result.safety_notes[0]}
            </AlertBanner>
          )}

          {/* Summary Panel */}
          <div className="ss-panel p-4">
            <div className="flex items-center justify-between mb-4 border-b border-(--ss-hairline) pb-2">
              <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                <FileCheck2 className="w-4 h-4 text-cyan-400" /> Executive Report
              </h3>
              <div className="flex gap-2">
                <Pill tone="cyan">ID: {result.analysis_id.substring(0, 8)}</Pill>
                <Pill tone="slate">{result.mode}</Pill>
              </div>
            </div>
            {result.executive_summary && (
              <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Executive Summary</div>
                <div className="text-sm text-slate-300 leading-relaxed bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                  {result.executive_summary}
                </div>
              </div>
            )}
            {result.technical_summary && (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Technical Summary</div>
                <div className="text-sm text-slate-300 leading-relaxed bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                  {result.technical_summary}
                </div>
              </div>
            )}
          </div>

          {/* AI Routing Trace Panel */}
          {result.routing_details && (
            <div className="ss-panel p-4 border-l-2 border-indigo-500">
              <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                <Route className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-semibold text-slate-100">AI Routing Trace</h3>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Selected Route</div>
                  <div className="text-xs text-indigo-300 font-mono">{result.routing_details.selected_route}</div>
                </div>
                <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Provider</div>
                  <div className="text-xs text-slate-200">{result.routing_details.provider_name || 'N/A'}</div>
                </div>
                <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Model</div>
                  <div className="text-xs text-slate-200">{result.routing_details.model_name || 'N/A'}</div>
                </div>
                <div className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                  <div className="text-[10px] uppercase tracking-wider text-emerald-500 mb-1">Tokens Saved</div>
                  <div className="text-xs text-emerald-300 font-mono">{result.routing_details.token_saving_estimate || 0}</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <Pill tone={result.routing_details.local_provider_available ? "cyan" : "slate"}>Local Provider: {result.routing_details.local_provider_available ? 'Available' : 'N/A'}</Pill>
                <Pill tone={result.routing_details.remote_provider_available ? "cyan" : "slate"}>Remote Provider: {result.routing_details.remote_provider_available ? 'Available' : 'N/A'}</Pill>
                <Pill tone={result.routing_details.attempted_local_call ? "cyan" : "slate"}>Attempted Local: {result.routing_details.attempted_local_call ? 'Yes' : 'No'}</Pill>
                {result.routing_details.fallback_used && <Pill tone="amber">Fallback Used</Pill>}
              </div>
              
              {/* Visual Routing Rail */}
              <div className="mt-4 pt-4 border-t border-(--ss-hairline) flex items-center justify-between px-8 text-xs text-slate-400 font-mono">
                <div className="flex flex-col items-center">
                  <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center border border-slate-600 mb-2">1</div>
                  <span>Rule Engine</span>
                </div>
                <div className={`h-px flex-1 mx-4 ${result.routing_details.selected_route === 'local_amd_model' || result.routing_details.attempted_local_call ? 'bg-cyan-500' : 'bg-slate-700'}`} />
                <div className="flex flex-col items-center">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center border mb-2 ${result.routing_details.selected_route === 'local_amd_model' ? 'bg-cyan-900 border-cyan-500 text-cyan-300' : 'bg-slate-800 border-slate-600'}`}>2</div>
                  <span>AMD ROCm Local</span>
                </div>
                <div className={`h-px flex-1 mx-4 ${result.routing_details.selected_route === 'fireworks_gemma' || result.routing_details.attempted_remote_call ? 'bg-cyan-500' : 'bg-slate-700'}`} />
                <div className="flex flex-col items-center">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center border mb-2 ${result.routing_details.selected_route === 'fireworks_gemma' ? 'bg-indigo-900 border-indigo-500 text-indigo-300' : 'bg-slate-800 border-slate-600'}`}>3</div>
                  <span>Fireworks/Gemma</span>
                </div>
                <div className={`h-px flex-1 mx-4 ${result.routing_details.fallback_used ? 'bg-amber-500' : 'bg-slate-700'}`} />
                <div className="flex flex-col items-center">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center border mb-2 ${result.routing_details.fallback_used ? 'bg-amber-900 border-amber-500 text-amber-300' : 'bg-slate-800 border-slate-600'}`}>4</div>
                  <span>Fallback</span>
                </div>
              </div>
            </div>
          )}

          {/* Attack Surface Graph Panel */}
          {result.attack_surface_graph && (
            <div className="ss-panel p-4">
              <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                <Share2 className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-slate-100">Attack Surface Graph</h3>
              </div>
              <div className="bg-(--ss-surface-1) p-4 rounded-md border border-(--ss-hairline) overflow-x-auto">
                <div className="flex min-w-max gap-8 items-center py-4 px-2">
                  {result.attack_surface_graph.nodes.map((node, idx) => (
                    <React.Fragment key={node.id}>
                      <div className="flex flex-col items-center max-w-[120px] text-center">
                        <div className="w-12 h-12 bg-slate-800 rounded-lg border border-cyan-500/30 flex items-center justify-center mb-2 shadow-[0_0_10px_rgba(34,211,238,0.1)]">
                          {node.type === 'asset' ? <Server className="w-5 h-5 text-cyan-400" /> : 
                           node.type === 'finding' ? <AlertTriangle className="w-5 h-5 text-amber-400" /> :
                           node.type === 'missing_control' ? <Shield className="w-5 h-5 text-red-400" /> :
                           <Box className="w-5 h-5 text-slate-400" />}
                        </div>
                        <span className="text-[10px] text-slate-400 uppercase tracking-wider">{node.type}</span>
                        <span className="text-xs text-slate-200 mt-1">{node.label}</span>
                      </div>
                      {idx < result.attack_surface_graph!.nodes.length - 1 && (
                        <div className="flex flex-col items-center mx-2 mt-[-30px]">
                          <span className="text-[9px] text-slate-500 mb-1">{result.attack_surface_graph!.edges.find(e => e.source === node.id)?.label || 'connects'}</span>
                          <div className="h-px w-16 bg-slate-600 relative">
                            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2 h-2 border-t border-r border-slate-600 rotate-45" />
                          </div>
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Digital Twin Scenario & Sandbox Proofs */}
          <div className="grid lg:grid-cols-2 gap-6">
            <div className="ss-panel p-4">
              <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                <Layers className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-slate-100">Digital Twin Scenarios</h3>
              </div>
              {result.digital_twin_scenarios && result.digital_twin_scenarios.length > 0 ? (
                <div className="space-y-4">
                  {result.digital_twin_scenarios.map(scenario => (
                    <div key={scenario.scenario_id} className="bg-(--ss-surface-1) p-3 rounded border border-(--ss-hairline)">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs font-mono text-cyan-300">{scenario.scenario_id}</span>
                        <Pill tone="slate">{scenario.scenario_type}</Pill>
                      </div>
                      <div className="space-y-2 text-sm text-slate-300">
                        <div className="flex gap-2"><span className="text-slate-500">Pattern:</span> {scenario.vulnerability_pattern}</div>
                        <div className="flex gap-2"><span className="text-slate-500">Goal:</span> {scenario.safe_proof_goal}</div>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {scenario.sandbox_components.map(c => (
                            <span key={c} className="text-[10px] bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">{c}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-slate-500 italic text-center py-4">No digital twin scenarios generated.</div>
              )}
            </div>

            <div className="ss-panel p-4 border-l-2 border-emerald-500">
              <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-semibold text-slate-100">Sandbox Proof Artifacts</h3>
              </div>
              {result.sandbox_proof_artifacts && result.sandbox_proof_artifacts.length > 0 ? (
                <div className="space-y-4">
                  {result.sandbox_proof_artifacts.map(proof => (
                    <div key={proof.proof_id} className="bg-(--ss-surface-1) p-3 rounded border border-emerald-900/50 relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-2 opacity-10">
                        <ShieldCheck className="w-12 h-12 text-emerald-400" />
                      </div>
                      <div className="flex gap-2 mb-2">
                        <Pill tone={proof.confirmed ? "success" : "warning"}>{proof.confirmed ? 'Confirmed' : 'Unconfirmed'}</Pill>
                        <Pill tone="slate">{proof.proof_type}</Pill>
                      </div>
                      <p className="text-sm text-slate-200 mb-2">{proof.evidence_summary}</p>
                      <div className="text-xs font-mono bg-slate-900 p-2 rounded text-emerald-300 mt-2 break-all">
                        {proof.proof_token || 'No proof token extracted'}
                      </div>
                      <div className="mt-3 flex items-center gap-1 text-[10px] text-emerald-400 uppercase tracking-wider">
                        <Lock className="w-3 h-3" /> Production Target Used: {proof.production_target_used ? 'YES' : 'NO (SAFE)'}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-400 italic text-center py-6 bg-(--ss-surface-1) rounded border border-(--ss-hairline)">
                  Sandbox proof is not generated because sandbox simulation is disabled or not requested.
                </div>
              )}
            </div>
          </div>

          {/* Tribunal Verdict */}
          {result.tribunal_verdict && (
            <div className="ss-panel p-4">
              <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                <Cpu className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-slate-100">Multi-Agent Risk Tribunal</h3>
              </div>
              
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                <div className="bg-(--ss-surface-1) p-3 rounded border border-red-900/30">
                  <div className="flex items-center gap-1.5 mb-2 border-b border-red-900/50 pb-1">
                    <Terminal className="w-3 h-3 text-red-400" />
                    <span className="text-[11px] font-semibold text-red-400 uppercase">Attacker Agent</span>
                  </div>
                  <p className="text-xs text-slate-300">{result.tribunal_verdict.attacker_view || 'No path identified'}</p>
                </div>
                <div className="bg-(--ss-surface-1) p-3 rounded border border-blue-900/30">
                  <div className="flex items-center gap-1.5 mb-2 border-b border-blue-900/50 pb-1">
                    <Shield className="w-3 h-3 text-blue-400" />
                    <span className="text-[11px] font-semibold text-blue-400 uppercase">Defender Agent</span>
                  </div>
                  <p className="text-xs text-slate-300">{result.tribunal_verdict.defender_view || 'No controls identified'}</p>
                </div>
                <div className="bg-(--ss-surface-1) p-3 rounded border border-purple-900/30">
                  <div className="flex items-center gap-1.5 mb-2 border-b border-purple-900/50 pb-1">
                    <Database className="w-3 h-3 text-purple-400" />
                    <span className="text-[11px] font-semibold text-purple-400 uppercase">Exploit Lab Agent</span>
                  </div>
                  <p className="text-xs text-slate-300">Feasibility: {result.tribunal_verdict.lab_view || 'Unknown'}</p>
                </div>
                <div className="bg-slate-800 p-3 rounded border border-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.1)]">
                  <div className="flex items-center gap-1.5 mb-2 border-b border-amber-900/50 pb-1">
                    <Eye className="w-3 h-3 text-amber-400" />
                    <span className="text-[11px] font-semibold text-amber-400 uppercase">Judge Agent Verdict</span>
                  </div>
                  <p className="text-xs font-semibold text-white mb-2">{result.tribunal_verdict.judge_verdict || 'Inconclusive'}</p>
                  <div className="flex gap-2">
                    <Pill tone={result.tribunal_verdict.severity === 'Critical' || result.tribunal_verdict.severity === 'High' ? 'danger' : 'warning'}>Sev: {result.tribunal_verdict.severity}</Pill>
                    <Pill tone="slate">Conf: {result.tribunal_verdict.confidence}</Pill>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Remediation & Retest */}
          <div className="grid lg:grid-cols-2 gap-6">
            {result.remediation_plan && (
              <div className="ss-panel p-4 border-t-2 border-cyan-500">
                <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                  <Code className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-semibold text-slate-100">Remediation Plan</h3>
                </div>
                {result.remediation_plan.immediate_fix && (
                  <div className="mb-3 p-2 bg-emerald-900/20 border border-emerald-900/50 rounded text-sm text-emerald-200">
                    <span className="font-semibold mr-2">Immediate Fix:</span>
                    {result.remediation_plan.immediate_fix}
                  </div>
                )}
                {result.remediation_plan.developer_tasks && result.remediation_plan.developer_tasks.length > 0 && (
                  <div className="mb-3">
                    <span className="text-[11px] uppercase tracking-wider text-slate-500">Developer Tasks</span>
                    <ul className="list-disc pl-4 mt-1 text-sm text-slate-300">
                      {result.remediation_plan.developer_tasks.map((t, i) => <li key={i}>{t}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {result.retest_plan && (
              <div className="ss-panel p-4 border-t-2 border-indigo-500">
                <div className="flex items-center gap-2 mb-4 border-b border-(--ss-hairline) pb-2">
                  <Activity className="w-4 h-4 text-indigo-400" />
                  <h3 className="text-sm font-semibold text-slate-100">Retest Plan</h3>
                </div>
                {result.retest_plan.retest_checklist && result.retest_plan.retest_checklist.length > 0 && (
                  <div className="mb-3">
                    <span className="text-[11px] uppercase tracking-wider text-slate-500">Retest Checklist</span>
                    <div className="mt-2 space-y-1">
                      {result.retest_plan.retest_checklist.map((t, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm text-slate-300">
                          <CheckCircle2 className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                          <span>{t}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {result.retest_plan.risk_delta_if_fixed && (
                  <div className="mt-3 p-2 bg-(--ss-surface-1) border border-(--ss-hairline) rounded text-sm text-slate-300">
                    <span className="font-semibold text-slate-400 mr-2">Risk Delta:</span>
                    {result.retest_plan.risk_delta_if_fixed}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
