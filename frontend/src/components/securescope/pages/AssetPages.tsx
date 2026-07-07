"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Copy,
  Globe,
  Hash,
  Info,
  Lock,
  Network,
  RefreshCw,
  Server,
  Shield,
  ShieldCheck,
  Tag,
  Target,
  XCircle,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { verificationAttempts } from "@/lib/securescope/data";
import type { Asset, VerificationState, Authorization, Engagement, ValidationExecution } from "@/lib/securescope/types";
import { Pill, RiskTierBadge, StatusBadge, VerificationBadge } from "../shared/badges";
import { AlertBanner, CyberButton, EmptyState, KeyValue, MaskedField } from "../shared/ui";
import { EventTimeline, SecureCodeBlock } from "../shared/lifecycle";
import { TopNavCommandBar, PageHeader, SecondaryContextNav } from "../shell/TopNav";

// ============================================================
// Asset list page
// ============================================================

export function AssetsListPage() {
  const go = useApp((s) => s.go);
  const openAsset = useApp((s) => s.openAsset);
  const assets = useApp((s) => s.assets);
  const [filter, setFilter] = React.useState<"all" | "verified" | "pending" | "failed">("all");
  const [query, setQuery] = React.useState("");

  const { counts, filtered } = React.useMemo(() => {
    let verified = 0;
    let pending = 0;
    let failed = 0;

    assets.forEach((a) => {
      if (a.verification === "verified") verified++;
      else if (a.verification === "pending") pending++;
      else if (a.verification === "failed") failed++;
    });

    const filteredList = assets.filter((a) => {
      if (filter !== "all" && a.verification !== filter) return false;
      if (query && !`${a.name} ${a.target} ${a.tags.join(" ")}`.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });

    return {
      counts: {
        all: assets.length,
        verified,
        pending,
        failed,
      },
      filtered: filteredList,
    };
  }, [assets, filter, query]);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Assets" }]}
          title="Assets"
          description="Verified targets eligible for validation. Each asset must prove ownership via DNS TXT challenge before it can be authorized for testing."
          right={<CyberButton size="sm" variant="primary"><Network className="w-3 h-3" /> Register asset</CyberButton>}
        />
        <SecondaryContextNav
          items={[
            { key: "all", label: "All", count: counts.all },
            { key: "verified", label: "Verified", count: counts.verified },
            { key: "pending", label: "Pending", count: counts.pending },
            { key: "failed", label: "Failed", count: counts.failed },
          ]}
          active={filter}
          onSelect={(k) => setFilter(k as typeof filter)}
          right={
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter assets…"
              className="px-2.5 py-1 text-[11px] bg-(--ss-surface-2) border border-(--ss-hairline-strong) rounded-sm text-slate-200 placeholder:text-slate-600 outline-none focus:border-cyan-400/50 w-48"
            />
          }
        />

        <div className="px-4 lg:px-6 py-4">
          <div className="ss-panel overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
                  <th className="text-left px-3 py-2 ss-eyebrow">Asset</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Target</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Type</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Criticality</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Verification</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Project</th>
                  <th className="text-left px-3 py-2 ss-eyebrow">Last validation</th>
                  <th className="text-left px-3 py-2 ss-eyebrow"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr
                    key={a.id}
                    onClick={() => openAsset(a.id)}
                    className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer transition-colors"
                  >
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className={cn("w-1.5 h-1.5 rounded-full", a.verification === "verified" ? "bg-emerald-400" : a.verification === "pending" ? "bg-amber-400" : "bg-red-400")} />
                        <span className="font-medium text-slate-200">{a.name}</span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {a.tags.slice(0, 2).map((t) => (
                          <span key={t} className="text-[9px] ss-mono-xs text-slate-500 border border-(--ss-hairline) rounded-sm px-1 py-0.5">{t}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{a.target}</code></td>
                    <td className="px-3 py-2.5 text-slate-400">{a.type.replace(/_/g, " ")}</td>
                    <td className="px-3 py-2.5"><Pill tone={a.criticality === "critical" ? "red" : a.criticality === "high" ? "amber" : "slate"}>{a.criticality}</Pill></td>
                    <td className="px-3 py-2.5"><VerificationBadge state={a.verification} /></td>
                    <td className="px-3 py-2.5 text-slate-400">{a.projectName}</td>
                    <td className="px-3 py-2.5 text-slate-500 ss-mono-xs">{a.lastValidation ? a.lastValidation.slice(0, 16).replace("T", " ") : "—"}</td>
                    <td className="px-3 py-2.5 text-right"><span className="text-cyan-300 text-[10px] uppercase tracking-wider">Open →</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

// ============================================================
// Asset detail page
// ============================================================

const ASSET_TABS = ["Overview", "Verification", "Authorizations", "Engagements", "Validation History", "Audit"] as const;
type AssetTab = (typeof ASSET_TABS)[number];

export function AssetDetailPage() {
  const assetId = useApp((s) => s.selectedAssetId);
  const go = useApp((s) => s.go);
  const openExecution = useApp((s) => s.openExecution);
  const [tab, setTab] = React.useState<AssetTab>("Overview");

  const assets = useApp((s) => s.assets);
  const authorizations = useApp((s) => s.authorizations);
  const engagements = useApp((s) => s.engagements);
  const executions = useApp((s) => s.executions);

  const asset = assets.find((a) => a.id === assetId) ?? { id: "", name: "Unknown", type: "web_app", criticality: "low", target: "—", verification: "pending", ownershipVerified: false, organizationId: "", organizationName: "", projectId: "", projectName: "", lastValidation: null, tags: [] };
  const assetAuths = authorizations.filter((a) => a.scopedAssets.includes(asset.id));
  const assetEngs = engagements.filter((e) => e.scopedAssetNames.includes(asset.name));
  const assetExecs = executions.filter((e) => e.assetId === asset.id);

  const attempts = React.useMemo(() => {
    if (!asset.target || asset.target === "—") return [];
    const parts = asset.target.split(".");
    const domainPart = parts.length >= 2 ? parts.slice(-2).join(".") : asset.target;
    return verificationAttempts.filter(
      (v) => v.challengeHost.includes(domainPart) || v.challengeHost.includes(asset.target)
    );
  }, [asset.target]);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-[76px] min-h-screen">
        {/* Identity header */}
        <div className="px-4 lg:px-6 pt-4 pb-4 border-b border-(--ss-hairline-strong) bg-linear-to-b from-(--ss-surface-2)/30 to-transparent">
          <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-2">
            <button onClick={() => go("assets")} className="hover:text-slate-300 uppercase tracking-wider">Assets</button>
            <span className="text-slate-700">/</span>
            <span className="uppercase tracking-wider">{asset.name}</span>
          </div>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-start gap-4 min-w-0 flex-1">
              <div className="w-12 h-12 rounded-sm border border-cyan-400/40 bg-cyan-500/10 flex items-center justify-center shrink-0 ss-glow-cyan">
                <Network className="w-5 h-5 text-cyan-300" />
              </div>
              <div className="min-w-0">
                <h1 className="text-xl lg:text-2xl font-semibold tracking-tight text-slate-100">{asset.name}</h1>
                <div className="flex items-center gap-2 mt-1">
                  <code className="ss-mono text-cyan-200 text-sm">{asset.target}</code>
                  <button className="text-slate-500 hover:text-cyan-300">
                    <Copy className="w-3 h-3" />
                  </button>
                </div>
                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  <VerificationBadge state={asset.verification} />
                  <Pill tone={asset.criticality === "critical" ? "red" : asset.criticality === "high" ? "amber" : "slate"}>
                    {asset.criticality} criticality
                  </Pill>
                  <Pill tone="slate">{asset.type.replace(/_/g, " ")}</Pill>
                  {asset.tags.map((t) => (
                    <Pill key={t} tone="cyan"><Tag className="w-2.5 h-2.5" /> {t}</Pill>
                  ))}
                </div>
              </div>
            </div>
            <div className="shrink-0 flex items-center gap-2">
              {asset.verification !== "verified" && (
                <CyberButton size="sm" variant="primary" onClick={() => setTab("Verification")}>
                  <Shield className="w-3 h-3" /> Start verification
                </CyberButton>
              )}
              <CyberButton size="sm" variant="ghost" onClick={() => go("execution_wizard")}>
                <Target className="w-3 h-3" /> Queue validation
              </CyberButton>
            </div>
          </div>

          {/* Identity strip */}
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-px bg-(--ss-hairline) border border-(--ss-hairline) rounded-sm overflow-hidden">
            <div className="bg-(--ss-surface-1) px-3 py-2">
              <div className="ss-eyebrow">Organization</div>
              <div className="text-[11px] text-slate-200 mt-0.5">{asset.organizationName}</div>
            </div>
            <div className="bg-(--ss-surface-1) px-3 py-2">
              <div className="ss-eyebrow">Project</div>
              <div className="text-[11px] text-slate-200 mt-0.5">{asset.projectName}</div>
            </div>
            <div className="bg-(--ss-surface-1) px-3 py-2">
              <div className="ss-eyebrow">Ownership</div>
              <div className="text-[11px] text-slate-200 mt-0.5">{asset.ownershipVerified ? "Verified" : "Unverified"}</div>
            </div>
            <div className="bg-(--ss-surface-1) px-3 py-2">
              <div className="ss-eyebrow">Authorizations</div>
              <div className="text-[11px] text-slate-200 mt-0.5 ss-mono-xs">{assetAuths.length}</div>
            </div>
            <div className="bg-(--ss-surface-1) px-3 py-2">
              <div className="ss-eyebrow">Engagements</div>
              <div className="text-[11px] text-slate-200 mt-0.5 ss-mono-xs">{assetEngs.length}</div>
            </div>
            <div className="bg-(--ss-surface-1) px-3 py-2">
              <div className="ss-eyebrow">Last validation</div>
              <div className="text-[11px] text-slate-200 mt-0.5 ss-mono-xs">{asset.lastValidation ? asset.lastValidation.slice(0, 16).replace("T", " ") : "—"}</div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="px-4 lg:px-6 border-b border-(--ss-hairline-strong) sticky top-[76px] bg-[#070B14]/80 backdrop-blur-sm z-20">
          <div className="flex items-center gap-0.5 overflow-x-auto ss-scroll">
            {ASSET_TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "px-3 py-2 text-[11px] uppercase tracking-wider border-b-2 -mb-px transition-colors whitespace-nowrap",
                  tab === t ? "text-cyan-200 border-cyan-400" : "text-slate-500 border-transparent hover:text-slate-300"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div className="px-4 lg:px-6 py-5">
          {tab === "Overview" && <AssetOverview asset={asset} assetAuths={assetAuths} assetEngs={assetEngs} assetExecs={assetExecs} />}
          {tab === "Verification" && <AssetVerification key={asset.id} asset={asset} attempts={attempts.length > 0 ? attempts : verificationAttempts} />}
          {tab === "Authorizations" && <AssetAuthorizations assetAuths={assetAuths} />}
          {tab === "Engagements" && <AssetEngagements assetEngs={assetEngs} />}
          {tab === "Validation History" && <AssetValidationHistory assetExecs={assetExecs} />}
          {tab === "Audit" && <AssetAudit asset={asset} />}
        </div>
      </div>
    </>
  );
}

function AssetOverview({ asset, assetAuths, assetEngs, assetExecs }: {
  asset: Asset;
  assetAuths: Authorization[];
  assetEngs: Engagement[];
  assetExecs: ValidationExecution[];
}) {
  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-4">
      <div className="space-y-4">
        <div className="ss-panel p-4">
          <div className="ss-eyebrow mb-2">Technical profile</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0">
            <KeyValue k="Asset ID" v={asset.id} mono />
            <KeyValue k="Type" v={asset.type.replace(/_/g, " ")} />
            <KeyValue k="Target host" v={<code className="ss-mono-xs text-cyan-200">{asset.target}</code>} />
            <KeyValue k="Criticality" v={<Pill tone={asset.criticality === "critical" ? "red" : "slate"}>{asset.criticality}</Pill>} />
            <KeyValue k="Verification" v={<VerificationBadge state={asset.verification} />} />
            <KeyValue k="Ownership" v={asset.ownershipVerified ? "Verified" : "Unverified"} />
          </div>
        </div>

        <div className="ss-panel p-4">
          <div className="ss-eyebrow mb-2">Recent validation history</div>
          {assetExecs.length === 0 ? (
            <EmptyState title="No executions yet" description="Queue a validation to populate history." icon={<Target className="w-5 h-5" />} />
          ) : (
            <ul className="space-y-2">
              {assetExecs.slice(0, 5).map((e) => (
                <li key={e.id} className="flex items-center justify-between p-2 rounded-sm border border-(--ss-hairline) hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 cursor-pointer"
                    onClick={() => useApp.getState().openExecution(e.id)}>
                  <code className="ss-mono-xs text-cyan-200">{e.code}</code>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={e.status} />
                    <span className="ss-mono-xs text-slate-500">{e.templateName}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <div className="ss-panel p-4">
          <div className="ss-eyebrow mb-2">Active authorizations</div>
          {assetAuths.length === 0 ? (
            <div className="text-[11px] text-slate-500 italic py-3">No active authorizations scope this asset.</div>
          ) : (
            <ul className="space-y-2">
              {assetAuths.map((a) => (
                <li key={a.id} className="p-2 rounded-sm border border-(--ss-hairline)">
                  <div className="flex items-center justify-between">
                    <code className="ss-mono-xs text-cyan-200">{a.code}</code>
                    <RiskTierBadge tier={a.maxRiskTier} />
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1 ss-mono-xs">{a.validFrom.slice(0,10)} → {a.validUntil.slice(0,10)}</div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ss-panel p-4">
          <div className="ss-eyebrow mb-2">Tags</div>
          <div className="flex flex-wrap gap-1.5">
            {asset.tags.map((t) => (
              <Pill key={t} tone="cyan"><Tag className="w-2.5 h-2.5" /> {t}</Pill>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Asset verification — DNS TXT challenge UI
// ============================================================

function AssetVerification({ asset, attempts }: { asset: Asset; attempts: typeof verificationAttempts }) {
  const verifyAsset = useApp((s) => s.verifyAsset);
  const isLoading = useApp((s) => s.isLoading);
  const [isVerifying, setIsVerifying] = React.useState(false);
  const [challengeToken, setChallengeToken] = React.useState(
    `ss-verify-${asset.id.replace(/_/g, "")}-${Math.random().toString(36).slice(2, 14)}`
  );

  const challengeHost = `_securescope-verify.${asset.target}`;
  const ttl = 300;

  const handleVerify = async () => {
    setIsVerifying(true);
    try {
      await verifyAsset(asset.id);
    } catch (err) {
      console.error(err);
    } finally {
      setIsVerifying(false);
    }
  };

  const handleReissue = () => {
    setChallengeToken(`ss-verify-${asset.id.replace(/_/g, "")}-${Math.random().toString(36).slice(2, 14)}`);
  };

  return (
    <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4">
      <div className="space-y-4">
        {/* Challenge card */}
        <div className="ss-panel">
          <div className="px-4 py-2.5 border-b border-(--ss-hairline-strong) flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs font-semibold text-slate-100">DNS TXT Challenge</span>
            </div>
            <VerificationBadge state={asset.verification} />
          </div>
          <div className="p-4 space-y-3">
            <AlertBanner tone="info" title="Ownership verification via DNS TXT">
              SecureScope issues a one-time challenge token. Publish it as a TXT record at the challenge host below. Once DNS propagates, we verify ownership and lock the asset to your organization.
            </AlertBanner>

            <SecureCodeBlock label="Challenge host" value={challengeHost} copyable hint="publish TXT record here" />
            <SecureCodeBlock label="TXT record value" value={challengeToken} copyable hint="one-time token · TTL 300s" />
            <MaskedField
              label="Operator signature key"
              placeholder="ed25519:••••••••••••••••"
              note="Used to sign the challenge token. The private key never leaves SecureScope."
            />

            <div className="grid grid-cols-3 gap-2">
              <div className="ss-panel-flat p-2 text-center">
                <div className="ss-eyebrow">Algorithm</div>
                <div className="text-[11px] text-slate-200 mt-0.5 ss-mono-xs">ed25519</div>
              </div>
              <div className="ss-panel-flat p-2 text-center">
                <div className="ss-eyebrow">TTL</div>
                <div className="text-[11px] text-slate-200 mt-0.5 ss-mono-xs">{ttl}s</div>
              </div>
              <div className="ss-panel-flat p-2 text-center">
                <div className="ss-eyebrow">Expires in</div>
                <div className="text-[11px] text-amber-300 mt-0.5 ss-mono-xs">14m 22s</div>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <CyberButton size="md" variant="primary" onClick={handleVerify} disabled={isVerifying || isLoading}>
                <RefreshCw className={cn("w-3.5 h-3.5", (isVerifying || isLoading) && "animate-spin")} />
                {isVerifying || isLoading ? "Verifying..." : "Verify now"}
              </CyberButton>
              <CyberButton size="md" variant="ghost" onClick={handleReissue} disabled={isVerifying || isLoading}>
                <RefreshCw className="w-3.5 h-3.5" /> Re-issue challenge
              </CyberButton>
            </div>
          </div>
        </div>

        {/* Verification status timeline */}
        <div className="ss-panel p-4">
          <div className="ss-eyebrow mb-3">Verification status timeline</div>
          <div className="relative">
            <div className="absolute left-[5px] top-1 bottom-1 w-px bg-(--ss-hairline-strong)" />
            <ul className="space-y-3">
              {([
                { state: "pending", label: "Pending", desc: "Challenge issued, awaiting DNS propagation.", reached: true },
                { state: "verified", label: "Verified", desc: "TXT record matched the issued token.", reached: asset.verification === "verified" },
                { state: "expired", label: "Expired", desc: "Challenge TTL elapsed without verification.", reached: ["expired"].includes(asset.verification) },
                { state: "failed", label: "Failed", desc: "TXT record missing or mismatched after retries.", reached: asset.verification === "failed" },
                { state: "cancelled", label: "Cancelled", desc: "Operator cancelled the challenge.", reached: asset.verification === "cancelled" },
              ] as { state: VerificationState; label: string; desc: string; reached: boolean }[]).map((s) => {
                const tone = s.reached
                  ? s.state === "verified" ? "bg-emerald-400" : s.state === "pending" ? "bg-amber-400 ss-pulse-amber" : s.state === "failed" ? "bg-red-400" : "bg-slate-500"
                  : "bg-slate-700 border border-slate-600";
                return (
                  <li key={s.state} className="relative pl-6">
                    <span className={cn("absolute left-0 top-1 w-[11px] h-[11px] rounded-full border-2 border-[#0A111E]", tone)} />
                    <div className={cn("text-xs font-medium", s.reached ? "text-slate-200" : "text-slate-600")}>{s.label}</div>
                    <div className={cn("text-[10px]", s.reached ? "text-slate-500" : "text-slate-700")}>{s.desc}</div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <div className="ss-panel p-4">
          <div className="ss-eyebrow mb-3">Verification attempt history</div>
          {attempts.length === 0 ? (
            <div className="text-[11px] text-slate-500 italic py-3 text-center">No attempts yet.</div>
          ) : (
            <ul className="space-y-2.5">
              {attempts.map((a) => (
                <li key={a.id} className="ss-panel-flat p-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <VerificationBadge state={a.state} />
                    <span className="ss-mono-xs text-slate-500">{new Date(a.createdAt).toLocaleString("en-GB", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                  </div>
                  <div className="text-[10px] text-slate-500 ss-mono-xs truncate">{a.challengeHost}</div>
                  <div className="text-[11px] text-slate-400 mt-1">{a.note}</div>
                  {a.durationMs > 0 && <div className="text-[10px] text-slate-500 mt-0.5 ss-mono-xs">resolved in {a.durationMs}ms</div>}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ss-panel-flat p-4">
          <div className="ss-eyebrow mb-2 flex items-center gap-1.5"><Info className="w-3 h-3" /> Safe troubleshooting</div>
          <ul className="space-y-2 text-[11px] text-slate-400">
            <li className="flex gap-2"><CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" /> Wait at least 2× TTL after publishing the TXT record.</li>
            <li className="flex gap-2"><CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" /> Use <code className="ss-mono-xs text-cyan-200">dig TXT _securescope-verify.{asset.target}</code> to confirm propagation.</li>
            <li className="flex gap-2"><CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" /> Ensure the record is at the exact challenge host — not the apex.</li>
            <li className="flex gap-2"><AlertTriangle className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" /> If using a CNAME chain, verify the final TXT resolves correctly.</li>
            <li className="flex gap-2"><XCircle className="w-3 h-3 text-red-400 shrink-0 mt-0.5" /> Do not reuse a token from a previous attempt — re-issue a fresh challenge.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function AssetAuthorizations({ assetAuths }: { assetAuths: Authorization[] }) {
  const openAuthorization = useApp((s) => s.openAuthorization);
  if (assetAuths.length === 0) {
    return <EmptyState eyebrow="Authorizations" title="No authorizations scope this asset" description="Create an authorization and add this asset to its scope." icon={<Shield className="w-5 h-5" />} />;
  }
  return (
    <div className="ss-panel overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
            <th className="text-left px-3 py-2 ss-eyebrow">Code</th>
            <th className="text-left px-3 py-2 ss-eyebrow">State</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Max risk</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Valid window</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Allowed paths</th>
            <th className="text-left px-3 py-2 ss-eyebrow"></th>
          </tr>
        </thead>
        <tbody>
          {assetAuths.map((a) => (
            <tr key={a.id} onClick={() => openAuthorization(a.id)} className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer">
              <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{a.code}</code></td>
              <td className="px-3 py-2.5"><Pill tone={a.state === "active" ? "green" : "slate"}>{a.state}</Pill></td>
              <td className="px-3 py-2.5"><RiskTierBadge tier={a.maxRiskTier} /></td>
              <td className="px-3 py-2.5 ss-mono-xs text-slate-400">{a.validFrom.slice(0,10)} → {a.validUntil.slice(0,10)}</td>
              <td className="px-3 py-2.5 text-slate-400">{a.scope.allowedPaths.length}</td>
              <td className="px-3 py-2.5 text-right text-cyan-300 text-[10px] uppercase tracking-wider">Open →</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssetEngagements({ assetEngs }: { assetEngs: Engagement[] }) {
  const openEngagement = useApp((s) => s.openEngagement);
  if (assetEngs.length === 0) {
    return <EmptyState eyebrow="Engagements" title="No engagements reference this asset" icon={<Target className="w-5 h-5" />} />;
  }
  return (
    <div className="grid md:grid-cols-2 gap-3">
      {assetEngs.map((e) => (
        <button key={e.id} onClick={() => openEngagement(e.id)} className="ss-panel p-3 text-left hover:border-cyan-500/40 hover:bg-(--ss-surface-3)/40 transition-colors">
          <div className="flex items-center justify-between mb-1">
            <code className="ss-mono-xs text-cyan-200">{e.code}</code>
            <Pill tone={e.state === "active" ? "green" : "slate"}>{e.state}</Pill>
          </div>
          <div className="text-xs font-medium text-slate-200">{e.name}</div>
          <div className="text-[10px] text-slate-500 mt-1 ss-mono-xs">{e.windowStart.slice(0,16).replace("T"," ")} → {e.windowEnd.slice(0,16).replace("T"," ")}</div>
        </button>
      ))}
    </div>
  );
}

function AssetValidationHistory({ assetExecs }: { assetExecs: ValidationExecution[] }) {
  const openExecution = useApp((s) => s.openExecution);
  if (assetExecs.length === 0) {
    return <EmptyState eyebrow="Validation History" title="No executions yet" icon={<Target className="w-5 h-5" />} />;
  }
  return (
    <div className="ss-panel overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-(--ss-surface-2) border-b border-(--ss-hairline-strong)">
            <th className="text-left px-3 py-2 ss-eyebrow">Execution</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Template</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Status</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Outcome</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Engagement</th>
            <th className="text-left px-3 py-2 ss-eyebrow">Finished</th>
          </tr>
        </thead>
        <tbody>
          {assetExecs.map((e) => (
            <tr key={e.id} onClick={() => openExecution(e.id)} className="border-b border-(--ss-hairline) hover:bg-(--ss-surface-3)/40 cursor-pointer">
              <td className="px-3 py-2.5"><code className="ss-mono-xs text-cyan-200">{e.code}</code></td>
              <td className="px-3 py-2.5 text-slate-400">{e.templateName}</td>
              <td className="px-3 py-2.5"><StatusBadge status={e.status} /></td>
              <td className="px-3 py-2.5">{e.outcome ? <Pill tone={e.outcome === "validated" ? "green" : e.outcome === "failed_safely" ? "red" : "amber"}>{e.outcome.replace(/_/g, " ")}</Pill> : <span className="text-slate-600">—</span>}</td>
              <td className="px-3 py-2.5 ss-mono-xs text-slate-400">{e.engagementCode}</td>
              <td className="px-3 py-2.5 ss-mono-xs text-slate-500">{e.workerFinishedAt ? e.workerFinishedAt.slice(0, 16).replace("T", " ") : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssetAudit({ asset }: { asset: Asset }) {
  const go = useApp((s) => s.go);
  const events: {
    id: string;
    at: string;
    label: string;
    kind: string;
    safeMeta?: Record<string, string>;
  }[] = [
    { id: "aa1", at: asset.lastValidation ?? "2026-07-02T06:42:11Z", label: "Validation executed", kind: "worker_finished", safeMeta: { exec: "EXEC-2026-0702-003", outcome: "validated" } },
    { id: "aa2", at: "2026-07-01T18:44:11Z", label: "Verification renewed", kind: "worker_started", safeMeta: { method: "dns_txt", duration_ms: "5230" } },
    { id: "aa3", at: "2026-06-30T11:22:00Z", label: "Asset registered", kind: "auth_expiry_warning", safeMeta: { org: asset.organizationName, project: asset.projectName } },
  ];
  return (
    <div className="ss-panel p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="ss-eyebrow">Asset audit stream</div>
        <button onClick={() => go("audit")} className="text-[10px] uppercase tracking-wider text-cyan-300 hover:text-cyan-200">Open global audit →</button>
      </div>
      <EventTimeline events={events} />
    </div>
  );
}
