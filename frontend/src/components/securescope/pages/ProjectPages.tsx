"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { FolderKanban, Plus, Activity, Shield, Zap, Target, FileCheck2 } from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { Pill, RiskTierBadge, StatusBadge } from "../shared/badges";
import { AlertBanner, CyberButton, EmptyState, KeyValue } from "../shared/ui";
import { EventTimeline } from "../shared/lifecycle";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

export function ProjectsListPage() {
  const openProject = useApp((s) => s.openProject);
  const projects = useApp((s) => s.projects);
  const addProject = useApp((s) => s.addProject);
  const organizations = useApp((s) => s.organizations);
  const [showCreate, setShowCreate] = React.useState(false);
  const [createName, setCreateName] = React.useState('');
  const [createSlug, setCreateSlug] = React.useState('');
  const [createDescription, setCreateDescription] = React.useState('');
  const [createLoading, setCreateLoading] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const handleCreate = async () => {
    if (!createName.trim()) { setCreateError('Project name is required'); return; }
    setCreateLoading(true);
    setCreateError(null);
    try {
      await addProject(createName.trim(), createSlug.trim() || undefined, createDescription.trim() || undefined);
      setShowCreate(false);
      setCreateName('');
      setCreateSlug('');
      setCreateDescription('');
    } catch (e: any) {
      setCreateError(e.message || 'Failed to create project');
    } finally {
      setCreateLoading(false);
    }
  };
  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Projects" }]}
          title="Projects"
          description="Projects group assets, authorizations, and engagements within an organization. Each project carries its own health and execution lineage."
          right={<CyberButton size="sm" variant="primary" onClick={() => setShowCreate(true)}><Plus className="w-3 h-3" /> New project</CyberButton>}
        />
        <div className="px-4 lg:px-6 py-4">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => openProject(p.id)}
                className="ss-panel p-4 text-left hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 transition-all"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-sm border border-cyan-400/30 bg-cyan-500/5 flex items-center justify-center">
                      <FolderKanban className="w-3.5 h-3.5 text-cyan-300" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-slate-100">{p.name}</div>
                      <div className="text-[10px] text-slate-500 ss-mono-xs">{p.code} · {p.organizationName}</div>
                    </div>
                  </div>
                  <Pill tone={p.status === "healthy" ? "green" : "amber"}>{p.status}</Pill>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-(--ss-hairline)">
                  <div>
                    <div className="ss-eyebrow">Assets</div>
                    <div className="text-sm font-semibold text-slate-200 tnum">{p.assetsCount}</div>
                  </div>
                  <div>
                    <div className="ss-eyebrow">Auths</div>
                    <div className="text-sm font-semibold text-slate-200 tnum">{p.activeAuthorizations}</div>
                  </div>
                  <div>
                    <div className="ss-eyebrow">Engs</div>
                    <div className="text-sm font-semibold text-slate-200 tnum">{p.activeEngagements}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {showCreate && (
        <>
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={() => setShowCreate(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div className="ss-panel-raised shadow-2xl w-full max-w-md pointer-events-auto">
              <div className="px-4 py-3 border-b border-(--ss-hairline-strong) flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-100">Create Project</span>
                <button onClick={() => setShowCreate(false)} className="text-slate-500 hover:text-slate-300 text-xs">✕</button>
              </div>
              <div className="p-4 space-y-4">
                <div>
                  <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Organization</label>
                  <div className="text-sm text-slate-300 bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm p-2">
                    {organizations.find(o => o.id === useApp.getState().selectedOrgId)?.name || 'Current organization'}
                  </div>
                </div>
                <div>
                  <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Project Name *</label>
                  <input
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    placeholder="e.g. Web Application Pentest Q3"
                    className="w-full bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm text-sm p-2 text-slate-200 outline-none focus:border-cyan-500/50"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Slug (optional)</label>
                  <input
                    value={createSlug}
                    onChange={(e) => setCreateSlug(e.target.value)}
                    placeholder="auto-generated from name"
                    className="w-full bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm text-sm p-2 text-slate-200 outline-none focus:border-cyan-500/50"
                  />
                </div>
                <div>
                  <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Description (optional)</label>
                  <textarea
                    value={createDescription}
                    onChange={(e) => setCreateDescription(e.target.value)}
                    placeholder="Brief description of the project scope"
                    rows={2}
                    className="w-full bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm text-sm p-2 text-slate-200 outline-none focus:border-cyan-500/50 resize-none"
                  />
                </div>
                {createError && (
                  <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-sm p-2">{createError}</div>
                )}
              </div>
              <div className="px-4 py-3 border-t border-(--ss-hairline-strong) flex justify-end gap-2">
                <CyberButton size="sm" variant="ghost" onClick={() => setShowCreate(false)} disabled={createLoading}>Cancel</CyberButton>
                <CyberButton size="sm" variant="primary" onClick={handleCreate} disabled={createLoading || !createName.trim()}>
                  {createLoading ? <span className="animate-pulse">Creating...</span> : 'Save Project'}
                </CyberButton>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

export function ProjectDetailPage() {
  const projectId = useApp((s) => s.selectedProjectId);
  const go = useApp((s) => s.go);
  const openOrg = useApp((s) => s.openOrg);
  const openAsset = useApp((s) => s.openAsset);
  const openExecution = useApp((s) => s.openExecution);

  const projects = useApp((s) => s.projects);
  const assets = useApp((s) => s.assets);
  const authorizations = useApp((s) => s.authorizations);
  const engagements = useApp((s) => s.engagements);
  const executions = useApp((s) => s.executions);

  const project = projects.find((p) => p.id === projectId) ?? { id: "", name: "Unknown", code: "—", organizationId: "", organizationName: "", status: "critical", assetsCount: 0, activeAuthorizations: 0, activeEngagements: 0, latestExecutionId: "", lastActivity: "" };
  const projectAssets = assets.filter((a) => a.projectId === project.id);
  const projectAuths = authorizations.filter((a) => a.projectId === project.id);
  const projectEngs = engagements.filter((e) => e.projectId === project.id);
  const projectExecs = executions.filter((e) => e.projectId === project.id);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[
            { label: "Projects", onClick: () => go("projects") },
            { label: project.name },
          ]}
          title={
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-sm border border-cyan-400/30 bg-cyan-500/5 flex items-center justify-center">
                <FolderKanban className="w-4 h-4 text-cyan-300" />
              </div>
              {project.name}
              <Pill tone={project.status === "healthy" ? "green" : "amber"}>{project.status}</Pill>
            </div>
          }
          description={
            <button onClick={() => openOrg(project.organizationId)} className="hover:text-cyan-300">
              {project.organizationName} · {project.code}
            </button>
          }
          meta={
            <>
              <Pill tone="slate"><Target className="w-2.5 h-2.5" /> {projectAssets.length} assets</Pill>
              <Pill tone="slate"><Shield className="w-2.5 h-2.5" /> {projectAuths.length} authorizations</Pill>
              <Pill tone="slate"><Zap className="w-2.5 h-2.5" /> {projectEngs.length} engagements</Pill>
              <Pill tone="slate"><FileCheck2 className="w-2.5 h-2.5" /> {projectExecs.length} executions</Pill>
            </>
          }
          right={<CyberButton size="sm" variant="primary" onClick={() => go("execution_wizard")}><Plus className="w-3 h-3" /> Queue execution</CyberButton>}
        />

        <div className="px-4 lg:px-6 py-5">
          {/* Project health strip */}
          <div className="ss-panel p-3 mb-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-(--ss-hairline) rounded-sm overflow-hidden">
              {[
                { l: "Assets verified", v: `${projectAssets.filter((a) => a.verification === "verified").length}/${projectAssets.length}` },
                { l: "Active authorizations", v: projectAuths.filter((a) => a.state === "active").length },
                { l: "Active engagements", v: projectEngs.filter((e) => e.state === "active").length },
                { l: "Running executions", v: projectExecs.filter((e) => e.status === "executing").length },
                { l: "Latest execution", v: project.latestExecutionId },
              ].map((x) => (
                <div key={x.l} className="bg-(--ss-surface-1) px-3 py-2">
                  <div className="ss-eyebrow">{x.l}</div>
                  <div className="text-sm font-semibold text-slate-200 mt-0.5 ss-mono-xs tnum">{x.v}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
            {/* Left split: assets + executions */}
            <div className="space-y-4">
              <div className="ss-panel p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Target className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-100">Related assets</span>
                  </div>
                  <button onClick={() => go("assets")} className="text-[10px] uppercase tracking-wider text-cyan-300 hover:text-cyan-200">View all →</button>
                </div>
                {projectAssets.length === 0 ? (
                  <EmptyState title="No assets" icon={<Target className="w-5 h-5" />} />
                ) : (
                  <ul className="space-y-2">
                    {projectAssets.map((a) => (
                      <li key={a.id} onClick={() => openAsset(a.id)} className="flex items-center justify-between p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 cursor-pointer">
                        <div className="min-w-0">
                          <div className="text-xs font-medium text-slate-200 truncate">{a.name}</div>
                          <code className="ss-mono-xs text-slate-500 truncate block">{a.target}</code>
                        </div>
                        <Pill tone={a.verification === "verified" ? "green" : "amber"}>{a.verification}</Pill>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="ss-panel p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-100">Recent executions</span>
                  </div>
                </div>
                {projectExecs.length === 0 ? (
                  <EmptyState title="No executions yet" icon={<FileCheck2 className="w-5 h-5" />} />
                ) : (
                  <ul className="space-y-2">
                    {projectExecs.slice(0, 6).map((e) => (
                      <li key={e.id} onClick={() => openExecution(e.id)} className="flex items-center justify-between p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 cursor-pointer">
                        <div className="flex items-center gap-2 min-w-0">
                          <code className="ss-mono-xs text-cyan-200">{e.code}</code>
                          <span className="text-[11px] text-slate-400 truncate">{e.templateName}</span>
                        </div>
                        <StatusBadge status={e.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Right split: authorizations + engagements + timeline */}
            <div className="space-y-4">
              <div className="ss-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Shield className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Active authorizations</span>
                </div>
                {projectAuths.length === 0 ? (
                  <EmptyState title="No authorizations" icon={<Shield className="w-5 h-5" />} />
                ) : (
                  <ul className="space-y-2">
                    {projectAuths.map((a) => (
                      <li key={a.id} onClick={() => useApp.getState().openAuthorization(a.id)} className="p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 cursor-pointer">
                        <div className="flex items-center justify-between">
                          <code className="ss-mono-xs text-cyan-200">{a.code}</code>
                          <RiskTierBadge tier={a.maxRiskTier} />
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5 ss-mono-xs">{a.validFrom.slice(0,10)} → {a.validUntil.slice(0,10)}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="ss-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Zap className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Active engagements</span>
                </div>
                {projectEngs.length === 0 ? (
                  <EmptyState title="No engagements" icon={<Zap className="w-5 h-5" />} />
                ) : (
                  <ul className="space-y-2">
                    {projectEngs.map((e) => (
                      <li key={e.id} onClick={() => useApp.getState().openEngagement(e.id)} className="p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 cursor-pointer">
                        <div className="flex items-center justify-between">
                          <code className="ss-mono-xs text-cyan-200">{e.code}</code>
                          <Pill tone={e.state === "active" ? "green" : "slate"}>{e.state}</Pill>
                        </div>
                        <div className="text-[11px] text-slate-300 mt-0.5 truncate">{e.name}</div>
                        {e.killSwitch.state !== "inactive" && (
                          <Pill tone="amber" className="mt-1">kill switch {e.killSwitch.state}</Pill>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="ss-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-100">Activity timeline</span>
                </div>
                <EventTimeline events={[
                  { id: "p1", at: project.lastActivity, kind: "worker_finished", label: "Latest activity", safeMeta: { exec: project.latestExecutionId } },
                  { id: "p2", at: "2026-07-01T22:00:00Z", kind: "worker_started", label: "Engagement created", safeMeta: { eng: "ENG-NSL-001" } },
                  { id: "p3", at: "2026-07-01T00:00:00Z", kind: "auth_expiry_warning", label: "Authorization activated", safeMeta: { auth: "AUTH-NSL-001" } },
                ]} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
