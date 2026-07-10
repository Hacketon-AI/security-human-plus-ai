"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Building2, ChevronRight, Plus, Search } from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { Pill, StatusBadge } from "../shared/badges";
import { CyberButton, EmptyState, KeyValue } from "../shared/ui";
import { TopNavCommandBar, PageHeader, SecondaryContextNav } from "../shell/TopNav";

export function OrganizationsListPage() {
  const openOrg = useApp((s) => s.openOrg);
  const organizations = useApp((s) => s.organizations);
  const addOrg = useApp((s) => s.addOrg);
  const [query, setQuery] = React.useState("");
  const [showCreate, setShowCreate] = React.useState(false);
  const [createName, setCreateName] = React.useState('');
  const [createSlug, setCreateSlug] = React.useState('');
  const [createLoading, setCreateLoading] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const handleCreate = async () => {
    if (!createName.trim()) { setCreateError('Name is required'); return; }
    setCreateLoading(true);
    setCreateError(null);
    try {
      await addOrg(createName.trim(), createSlug.trim() || undefined);
      setShowCreate(false);
      setCreateName('');
      setCreateSlug('');
    } catch (e: any) {
      setCreateError(e.message || 'Failed to create organization');
    } finally {
      setCreateLoading(false);
    }
  };

  const filtered = organizations.filter((o) =>
    !query || `${o.name} ${o.code}`.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Organizations" }]}
          title="Organizations"
          description={<><span className="text-amber-400 font-semibold mr-2">Optional workspace context.</span> Tenant-level grouping. Each organization isolates projects, assets, authorizations, engagements, and audit attribution.</>}
          right={<CyberButton size="sm" variant="primary" onClick={() => setShowCreate(true)}><Plus className="w-3 h-3" /> New organization</CyberButton>}
        />
        <SecondaryContextNav
          items={[{ key: "all", label: "All", count: organizations.length }]}
          active="all"
          onSelect={() => {}}
          right={
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-sm border border-(--ss-hairline-strong) bg-(--ss-surface-2)">
              <Search className="w-3 h-3 text-slate-500" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search organizations…"
                className="bg-transparent text-[11px] text-slate-200 placeholder:text-slate-600 outline-none w-44"
              />
            </div>
          }
        />

        <div className="px-4 lg:px-6 py-4">
          <div className="ss-panel overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
                  <th className="text-left px-3 py-2 ss-eyebrow">Organization</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Status</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Projects</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Verified assets</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Active engagements</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Latest execution</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Last activity</th>
                  <th className="text-left px-3 py-2 ss-eyebrow"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((o) => (
                  <tr key={o.id} onClick={() => openOrg(o.id)} className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer">
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-sm border border-cyan-400/30 bg-cyan-500/5 flex items-center justify-center shrink-0">
                          <Building2 className="w-3.5 h-3.5 text-cyan-300" />
                        </div>
                        <div>
                          <div className="font-medium text-slate-200">{o.name}</div>
                          <div className="text-[10px] text-slate-500 ss-mono-xs">{o.code}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <Pill tone={o.status === "healthy" ? "green" : o.status === "warning" ? "amber" : "red"}>
                        <span className={cn("w-1 h-1 rounded-full", o.status === "healthy" ? "bg-emerald-400" : "bg-amber-400")} />
                        {o.status}
                      </Pill>
                    </td>
                    <td className="px-3 py-3 ss-mono-xs text-slate-300 tnum">{o.projectsCount}</td>
                    <td className="px-3 py-3 ss-mono-xs text-slate-300 tnum">{o.verifiedAssets}</td>
                    <td className="px-3 py-3 ss-mono-xs text-slate-300 tnum">{o.activeEngagements}</td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <StatusBadge status={o.latestExecutionState} />
                        <code className="ss-mono-xs text-slate-500">{o.latestExecutionId}</code>
                      </div>
                    </td>
                    <td className="px-3 py-3 ss-mono-xs text-slate-500">{o.lastActivity.slice(0, 16).replace("T", " ")}</td>
                    <td className="px-3 py-3 text-right"><ChevronRight className="w-3.5 h-3.5 text-slate-600 inline" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showCreate && (
        <>
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={() => setShowCreate(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div className="ss-panel-raised shadow-2xl w-full max-w-md pointer-events-auto">
              <div className="px-4 py-3 border-b border-(--ss-hairline-strong) flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-100">Create Organization</span>
                <button onClick={() => setShowCreate(false)} className="text-slate-500 hover:text-slate-300 text-xs">✕</button>
              </div>
              <div className="p-4 space-y-4">
                <div>
                  <label className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">Organization Name *</label>
                  <input
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    placeholder="e.g. Acme Security Lab"
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
                {createError && (
                  <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-sm p-2">{createError}</div>
                )}
                <div className="text-[10px] text-slate-500 bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm p-2">
                  If the backend provisioning endpoint is not available, a local demo organization will be created. Local demo organizations are not persisted to the database.
                </div>
              </div>
              <div className="px-4 py-3 border-t border-(--ss-hairline-strong) flex justify-end gap-2">
                <CyberButton size="sm" variant="ghost" onClick={() => setShowCreate(false)} disabled={createLoading}>Cancel</CyberButton>
                <CyberButton size="sm" variant="primary" onClick={handleCreate} disabled={createLoading || !createName.trim()}>
                  {createLoading ? <span className="animate-pulse">Creating...</span> : 'Save Organization'}
                </CyberButton>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

const ORG_TABS = ["Overview", "Projects", "Assets", "Executions", "Activity", "Settings"] as const;

export function OrganizationDetailPage() {
  const orgId = useApp((s) => s.selectedOrgId);
  const go = useApp((s) => s.go);
  const openProject = useApp((s) => s.openProject);
  const [tab, setTab] = React.useState<(typeof ORG_TABS)[number]>("Overview");

  const organizations = useApp((s) => s.organizations);
  const projects = useApp((s) => s.projects);
  const assets = useApp((s) => s.assets);
  const executions = useApp((s) => s.executions);

  const org = organizations.find((o) => o.id === orgId) ?? { id: "", name: "Unknown", code: "—", status: "critical", projectsCount: 0, verifiedAssets: 0, activeEngagements: 0, latestExecutionState: "failed", latestExecutionId: "", lastActivity: "" };
  const orgProjects = projects.filter((p) => p.organizationId === org.id);
  const orgAssets = assets.filter((a) => a.organizationId === org.id);
  const orgExecs = executions.filter((e) => e.organizationId === org.id);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[
            { label: "Organizations", onClick: () => go("organizations") },
            { label: org.name },
          ]}
          title={
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-sm border border-cyan-400/30 bg-cyan-500/5 flex items-center justify-center">
                <Building2 className="w-4 h-4 text-cyan-300" />
              </div>
              {org.name}
              <Pill tone={org.status === "healthy" ? "green" : "amber"}>{org.status}</Pill>
            </div>
          }
          description={`Code ${org.code} · ${org.projectsCount} projects · ${org.verifiedAssets} verified assets · ${org.activeEngagements} active engagements`}
        />
        <SecondaryContextNav
          items={ORG_TABS.map((t) => ({ key: t, label: t }))}
          active={tab}
          onSelect={(k) => setTab(k as typeof tab)}
          right={<CyberButton size="sm" variant="ghost">Export audit</CyberButton>}
        />

        <div className="px-4 lg:px-6 py-5">
          {tab === "Overview" && (
            <div className="grid lg:grid-cols-3 gap-4">
              <div className="ss-panel p-4 lg:col-span-2">
                <div className="ss-eyebrow mb-2">Organization health</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-(--ss-hairline) border border-(--ss-hairline) rounded-sm overflow-hidden">
                  {[
                    { l: "Projects", v: org.projectsCount },
                    { l: "Verified assets", v: org.verifiedAssets },
                    { l: "Active engagements", v: org.activeEngagements },
                    { l: "Executions (24h)", v: orgExecs.length },
                  ].map((x) => (
                    <div key={x.l} className="bg-(--ss-surface-1) px-3 py-3">
                      <div className="ss-eyebrow">{x.l}</div>
                      <div className="text-2xl font-semibold tnum text-slate-100 mt-1">{x.v}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-4">
                  <div className="ss-eyebrow mb-2">Latest execution</div>
                  <div className="flex items-center justify-between p-3 ss-panel-flat">
                    <code className="ss-mono-xs text-cyan-200">{org.latestExecutionId}</code>
                    <StatusBadge status={org.latestExecutionState} />
                  </div>
                </div>
              </div>
              <div className="ss-panel p-4">
                <div className="ss-eyebrow mb-2">Metadata</div>
                <KeyValue k="Organization ID" v={org.id} mono />
                <KeyValue k="Code" v={org.code} mono />
                <KeyValue k="Status" v={org.status} />
                <KeyValue k="Last activity" v={org.lastActivity.slice(0, 16).replace("T", " ")} mono />
              </div>
            </div>
          )}

          {tab === "Projects" && (
            <div className="grid md:grid-cols-2 gap-3">
              {orgProjects.map((p) => (
                <button key={p.id} onClick={() => openProject(p.id)} className="ss-panel p-4 text-left hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-slate-100">{p.name}</span>
                    <Pill tone={p.status === "healthy" ? "green" : "amber"}>{p.status}</Pill>
                  </div>
                  <div className="text-[10px] text-slate-500 ss-mono-xs">{p.code} · {p.assetsCount} assets · {p.activeEngagements} engagements</div>
                </button>
              ))}
            </div>
          )}

          {tab === "Assets" && (
            <div className="ss-panel overflow-hidden">
              <table className="w-full text-xs">
                <thead><tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
                  <th className="text-left px-3 py-2 ss-eyebrow">Asset</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Target</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Criticality</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Verification</th>
                </tr></thead>
                <tbody>
                  {orgAssets.map((a) => (
                    <tr key={a.id} onClick={() => useApp.getState().openAsset(a.id)} className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer">
                      <td className="px-3 py-2.5 text-slate-200">{a.name}</td>
                      <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{a.target}</code></td>
                      <td className="px-3 py-2.5"><Pill tone={a.criticality === "critical" ? "red" : "slate"}>{a.criticality}</Pill></td>
                      <td className="px-3 py-2.5"><Pill tone={a.verification === "verified" ? "green" : "amber"}>{a.verification}</Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === "Executions" && (
            <div className="ss-panel overflow-hidden">
              <table className="w-full text-xs">
                <thead><tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
                  <th className="text-left px-3 py-2 ss-eyebrow">Execution</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Asset</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Template</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Status</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Queued</th>
                </tr></thead>
                <tbody>
                  {orgExecs.map((e) => (
                    <tr key={e.id} onClick={() => useApp.getState().openExecution(e.id)} className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer">
                      <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{e.code}</code></td>
                      <td className="px-3 py-2.5 text-slate-300">{e.assetName}</td>
                      <td className="px-3 py-2.5 text-slate-400">{e.templateName}</td>
                      <td className="px-3 py-2.5"><StatusBadge status={e.status} /></td>
                      <td className="px-3 py-2.5 ss-mono-xs text-slate-500">{e.queuedAt?.slice(0, 16).replace("T", " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === "Activity" && (
            <EmptyState eyebrow="Activity" title="Activity stream" description="Per-organization activity stream surfaces here." />
          )}

          {tab === "Settings" && (
            <div className="ss-panel p-4 max-w-2xl">
              <div className="ss-eyebrow mb-3">Organization settings</div>
              <div className="space-y-3 text-[11px] text-slate-400">
                <p>This panel would expose organization-level configuration: default risk tier caps, allowed regions, operator roster, and SSO bindings. No secrets are exposed.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
