"use client";

import { create } from "zustand";
import type {
  Organization,
  Project,
  Asset,
  Authorization,
  Engagement,
  ValidationExecution,
  RouteKey,
  AssetType,
  VerificationState,
  AuthorizationState,
  EngagementState,
  RiskTier,
  AuditEvent,
} from "./types";
import * as api from "./api";

interface AppState {
  route: RouteKey;
  selectedOrgId: string | null;
  selectedProjectId: string | null;
  selectedAssetId: string | null;
  selectedAuthorizationId: string | null;
  selectedEngagementId: string | null;
  selectedExecutionId: string | null;
  executionTab?: string;
  inspectorExecutionId: string | null;
  killSwitchTarget: string | null;
  authenticated: boolean;

  organizations: Organization[];
  projects: Project[];
  assets: Asset[];
  authorizations: Authorization[];
  engagements: Engagement[];
  executions: ValidationExecution[];
  auditEvents: AuditEvent[];
  workers: any[];
  dispatchQueues: any[];

  isLoading: boolean;
  error: string | null;
  workspaceWarning: string | null;
  demoWorkspaceMode: "full" | "real_scan_standalone";

  latestDomainSafeScanResult: any | null;
  latestDomainSafeScanDomain: string | null;
  latestDomainSafeScanAt: string | null;

  activeSecurityWorkflow: "manual_validation" | "ai_proof_of_risk" | "domain_safe_scan" | "execution_detail" | null;
  activeAnalysisSource: "manual_execution" | "domain_safe_scan" | "ai_proof_of_risk" | "demo_execution" | null;
  latestManualValidationResult: any | null;
  latestScanMetadata: any | null;

  go: (route: RouteKey) => void;
  openOrg: (id: string) => void;
  openProject: (id: string) => void;
  openAsset: (id: string) => void;
  openAuthorization: (id: string) => void;
  openEngagement: (id: string) => void;
  openExecution: (id: string, tab?: string) => void;
  openInspector: (id: string | null) => void;
  requestKillSwitch: (engagementId: string | null) => void;
  login: (orgId: string) => void;
  logout: () => void;

  initData: () => Promise<void>;
  fetchData: () => Promise<void>;
  addOrg: (name: string, slug?: string) => Promise<void>;
  addProject: (name: string, slug?: string, description?: string) => Promise<void>;
  addAsset: (payload: { name: string; asset_type: string; environment: string; target: string; criticality: string }) => Promise<void>;
  verifyAsset: (assetId: string) => Promise<void>;
  addAuthorization: (payload: any) => Promise<void>;
  submitAuth: (authId: string) => Promise<void>;
  activateAuth: (authId: string) => Promise<void>;
  addEngagement: (payload: any) => Promise<void>;
  scheduleEng: (engId: string) => Promise<void>;
  activateEng: (engId: string) => Promise<void>;
  pauseEng: (engId: string) => Promise<void>;
  resumeEng: (engId: string) => Promise<void>;
  completeEng: (engId: string) => Promise<void>;
  cancelEng: (engId: string) => Promise<void>;
  triggerKillSwitch: (engagementId: string, active: boolean, reason: string) => Promise<void>;
  addExecution: (payload: { asset_id: string; engagement_id: string; template_id: string; risk_tier: string; execution_specification: any }) => Promise<void>;
  cancelExec: (execId: string) => Promise<void>;

  // AI Proof-of-Risk Safe State
  latestAiProofOfRiskAnalysis: any | null;
  latestAiProofOfRiskExecutionId: string | null;
  aiProofOfRiskLastRunAt: string | null;
  setLatestAiProofOfRiskAnalysis: (executionId: string, analysis: any) => void;

  setDomainSafeScanResult: (domain: string, result: any) => void;
  clearDomainSafeScanResult: () => void;
  
  setScanMetadata: (metadata: any) => void;
  setActiveAnalysisSource: (source: "manual_execution" | "domain_safe_scan" | "ai_proof_of_risk" | "demo_execution" | null) => void;
  setActiveSecurityWorkflow: (workflow: "manual_validation" | "ai_proof_of_risk" | "domain_safe_scan" | "execution_detail" | null) => void;
  setLatestManualValidationResult: (result: any) => void;
}

// --------------------------------------------------
// Mappers
// --------------------------------------------------

const mapRiskTier = (tier: string): RiskTier => {
  if (tier === "tier_0_passive") return "low";
  if (tier === "tier_1_safe") return "moderate";
  if (tier === "tier_2_controlled") return "high";
  if (tier === "tier_3_critical") return "critical";
  return "moderate";
};

const mapRiskTierToBackend = (tier: string): string => {
  if (tier === "low") return "tier_0_passive";
  if (tier === "moderate") return "tier_1_safe";
  if (tier === "high") return "tier_2_controlled";
  if (tier === "critical") return "tier_3_critical";
  return "tier_1_safe";
};

const mapAssetType = (t: string): AssetType => {
  if (t === "web_application") return "web_app";
  if (t === "api") return "web_api";
  return "web_app";
};

const mapVerificationState = (status: string): VerificationState => {
  if (status === "verified") return "verified";
  if (status === "pending_verification") return "pending";
  if (status === "draft") return "pending";
  return "failed";
};

const mapAuthorizationState = (status: string): AuthorizationState => {
  if (status === "active") return "active";
  if (status === "expired") return "expired";
  if (status === "revoked" || status === "rejected") return "blocked";
  return "draft";
};

export const useApp = create<AppState>((set, get) => ({
  route: "login",
  selectedOrgId: null,
  selectedProjectId: null,
  selectedAssetId: null,
  selectedAuthorizationId: null,
  selectedEngagementId: null,
  selectedExecutionId: null,
  executionTab: "Overview",
  inspectorExecutionId: null,
  killSwitchTarget: null,
  authenticated: false,

  organizations: [],
  projects: [],
  assets: [],
  authorizations: [],
  engagements: [],
  executions: [],
  auditEvents: [],
  workers: [],
  dispatchQueues: [],

  latestAiProofOfRiskAnalysis: null,
  latestAiProofOfRiskExecutionId: null,
  aiProofOfRiskLastRunAt: null,

  latestDomainSafeScanResult: null,
  latestDomainSafeScanDomain: null,
  latestDomainSafeScanAt: null,

  activeSecurityWorkflow: null,
  activeAnalysisSource: null,
  latestManualValidationResult: null,
  latestScanMetadata: null,

  isLoading: false,
  error: null,
  workspaceWarning: null,
  demoWorkspaceMode: "full",

  go: (route) => set({ route }),
  openOrg: (id) => set({ selectedOrgId: id, route: "organization_detail" }),
  openProject: (id) => set({ selectedProjectId: id, route: "project_detail" }),
  openAsset: (id) => set({ selectedAssetId: id, route: "asset_detail" }),
  openAuthorization: (id) => set({ selectedAuthorizationId: id, route: "authorization_detail" }),
  openEngagement: (id) => set({ selectedEngagementId: id, route: "engagement_detail" }),
  openExecution: (id, tab = "Overview") => set({ selectedExecutionId: id, executionTab: tab, route: "execution_detail" }),
  openInspector: (id) => set({ inspectorExecutionId: id }),
  requestKillSwitch: (engagementId) => set({ killSwitchTarget: engagementId }),
  login: (orgId: string) => {
    set({ authenticated: true, route: "dashboard", selectedOrgId: orgId, error: null });
    get().initData();
  },
  logout: () =>
    set({
      authenticated: false,
      route: "login",
      selectedOrgId: null,
      selectedProjectId: null,
      selectedAssetId: null,
      selectedAuthorizationId: null,
      selectedEngagementId: null,
      selectedExecutionId: null,
      inspectorExecutionId: null,
      killSwitchTarget: null,
      organizations: [],
      projects: [],
      assets: [],
      authorizations: [],
      engagements: [],
      executions: [],
      workers: [],
      dispatchQueues: [],
      latestAiProofOfRiskAnalysis: null,
      latestAiProofOfRiskExecutionId: null,
      aiProofOfRiskLastRunAt: null,
      latestDomainSafeScanResult: null,
      latestDomainSafeScanDomain: null,
      latestDomainSafeScanAt: null,
      demoWorkspaceMode: "full",
      error: null,
      workspaceWarning: null,
      activeSecurityWorkflow: null,
      activeAnalysisSource: null,
      latestManualValidationResult: null,
      latestScanMetadata: null,
    }),

  initData: async () => {
    set({ isLoading: true, error: null });
    try {
      // First, fetch organizations — selectedOrgId is set by login()
      const orgId = get().selectedOrgId;
      if (!orgId) throw new Error("No organization selected");
      const rawOrgs = await api.fetchOrganizations(orgId);
      const orgs: Organization[] = rawOrgs.map((o) => ({
        id: o.id,
        name: o.name,
        code: o.slug.toUpperCase(),
        status: o.status === "active" ? "healthy" : "warning",
        projectsCount: 0,
        verifiedAssets: 0,
        activeEngagements: 0,
        latestExecutionState: "succeeded",
        latestExecutionId: "",
        lastActivity: o.updated_at || o.created_at,
      }));

      if (orgs.length === 0) {
        throw new Error("Organization not found. Check the Organization ID and try again.");
      }

      set({ organizations: orgs, selectedOrgId: orgId, demoWorkspaceMode: "full" });
      await get().fetchData();
    } catch (e: any) {
      console.warn("Failed to initialize workspace data. Falling back to real scan standalone mode.", e);
      set({ 
        demoWorkspaceMode: "real_scan_standalone", 
        workspaceWarning: "Optional workspace context failed to load. Workspace seed data unavailable. Real authorized scan mode is still available.",
        organizations: [],
        projects: [],
        assets: [],
        authorizations: [],
        engagements: [],
        executions: []
      });
    } finally {
      set({ isLoading: false });
    }
  },

  fetchData: async () => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;

    set({ isLoading: true, error: null });
    try {
      // 1. Fetch Projects
      const rawPrjs = await api.fetchProjects(orgId);
      // 2. Fetch Assets
      const rawAssets = await api.fetchAssets(orgId);
      const assets: Asset[] = rawAssets.map((a) => {
        const prj = rawPrjs.find((p) => p.id === a.project_id);
        const orgName = get().organizations.find((o) => o.id === orgId)?.name || "Nasari Security Lab";
        return {
          id: a.id,
          name: a.name,
          type: mapAssetType(a.asset_type),
          criticality: a.criticality,
          target: a.target,
          verification: mapVerificationState(a.status),
          ownershipVerified: !!a.ownership_verified_at,
          organizationId: a.organization_id,
          organizationName: orgName,
          projectId: a.project_id,
          projectName: prj ? prj.name : "Unknown",
          lastValidation: null,
          tags: [a.environment],
        };
      });

      const projects: Project[] = rawPrjs.map((p) => {
        const orgName = get().organizations.find((o) => o.id === orgId)?.name || "Nasari Security Lab";
        const projAssets = assets.filter((a) => a.projectId === p.id);
        return {
          id: p.id,
          name: p.name,
          code: p.slug ? p.slug.toUpperCase() : "PROJ",
          organizationId: p.organization_id,
          organizationName: orgName,
          status: p.status === "active" ? "healthy" : "warning",
          assetsCount: projAssets.length,
          activeAuthorizations: 0,
          activeEngagements: 0,
          latestExecutionId: "",
          lastActivity: p.updated_at || p.created_at,
        };
      });

      // 3. Fetch Authorizations (aggregate from all projects)
      const allAuths: Authorization[] = [];
      const allEngs: Engagement[] = [];
      const allExecs: ValidationExecution[] = [];

      for (const prj of rawPrjs) {
        try {
          const rawAuths = await api.fetchAuthorizations(orgId, prj.id);
          const mappedAuths: Authorization[] = rawAuths.map((auth) => {
            const scopedAssetIds = (auth.scopes || []).map((s: any) => s.asset_id);
            const scopedAssets = assets.filter((ast) => scopedAssetIds.includes(ast.id));
            const firstScope = auth.scopes && auth.scopes[0] ? auth.scopes[0] : null;
            return {
              id: auth.id,
              code: auth.reference_number,
              organizationId: auth.organization_id,
              organizationName: projects.find((p) => p.id === prj.id)?.organizationName || "",
              projectId: auth.project_id,
              projectName: prj.name,
              state: mapAuthorizationState(auth.status),
              validFrom: auth.valid_from,
              validUntil: auth.valid_until,
              maxRiskTier: mapRiskTier(auth.maximum_risk_tier),
              scopedAssets: scopedAssetIds,
              scopedAssetNames: scopedAssets.map((ast) => ast.name),
              scope: {
                allowedPaths: firstScope?.allowed_paths ? firstScope.allowed_paths.split(",") : ["/*"],
                excludedPaths: firstScope?.excluded_paths ? firstScope.excluded_paths.split(",") : [],
                allowedPorts: firstScope?.allowed_ports || [443],
                allowedHosts: scopedAssets.map((ast) => ast.target),
              },
              supportingDoc: {
                name: auth.authorization_document_name || "letter.pdf",
                hash: auth.authorization_document_sha256
                  ? `sha256:${auth.authorization_document_sha256.slice(0, 4)}…${auth.authorization_document_sha256.slice(-4)}`
                  : "—",
                signedBy: auth.emergency_contact_name || "—",
                signedAt: auth.activated_at || "—",
              },
              approvalTimeline: [
                { at: auth.created_at, actor: auth.emergency_contact_name || "operator", action: "requested" },
                ...(auth.submitted_at ? [{ at: auth.submitted_at, actor: "operator", action: "submitted" }] : []),
                ...(auth.activated_at ? [{ at: auth.activated_at, actor: "system", action: "activated" }] : []),
                ...(auth.revoked_at ? [{ at: auth.revoked_at, actor: "operator", action: "revoked" }] : []),
              ],
              immutableLock: auth.status === "active",
            };
          });
          allAuths.push(...mappedAuths);

          // 4. Fetch Engagements
          const rawEngs = await api.fetchEngagements(orgId, prj.id);
          const mappedEngs: Engagement[] = rawEngs.map((e) => {
            const auth = mappedAuths.find((a) => a.id === e.authorization_id);
            return {
              id: e.id,
              code: `ENG-${e.name.toUpperCase().replace(/\s+/g, "-").slice(0, 8)}`,
              name: e.name,
              organizationId: e.organization_id,
              organizationName: projects.find((p) => p.id === prj.id)?.organizationName || "",
              projectId: e.project_id,
              projectName: prj.name,
              authorizationId: e.authorization_id,
              authorizationCode: auth ? auth.code : e.authorization_id.slice(0, 8).toUpperCase(),
              state: e.status as EngagementState,
              windowStart: e.starts_at,
              windowEnd: e.ends_at,
              maxRiskTier: mapRiskTier(e.max_risk_tier),
              scopedAssetNames: auth ? auth.scopedAssetNames : [],
              activeExecutions: e.status === "active" ? 1 : 0,
              killSwitch: {
                state: e.kill_switch_active ? "active" : "inactive",
                reason: e.kill_switch_reason || undefined,
              },
              createdAt: e.created_at,
            };
          });
          allEngs.push(...mappedEngs);

          // 5. Fetch Executions
          const rawExecs = await api.fetchExecutions(orgId, prj.id);
          const mappedExecs: ValidationExecution[] = rawExecs.map((ex) => {
            const asset = assets.find((a) => a.id === ex.asset_id);
            const auth = mappedAuths.find((a) => a.id === ex.authorization_id);
            const eng = mappedEngs.find((e) => e.id === ex.engagement_id);
            return {
              id: ex.id,
              code: `EXEC-${ex.created_at ? ex.created_at.slice(0, 10).replace(/-/g, "") : "20260702"}-${ex.id.slice(0, 3).toUpperCase()}`,
              status: ex.status,
              outcome: ex.outcome || null,
              organizationId: ex.organization_id,
              organizationName: projects.find((p) => p.id === prj.id)?.organizationName || "",
              projectId: ex.project_id,
              projectName: prj.name,
              assetId: ex.asset_id,
              assetName: asset ? asset.name : "Unknown Asset",
              assetTargetMasked: asset ? asset.target : "",
              authorizationId: ex.authorization_id,
              authorizationCode: auth ? auth.code : "",
              engagementId: ex.engagement_id,
              engagementCode: eng ? eng.code : "",
              templateId: ex.template_id,
              templateName: ex.template_id.replace(/_/g, " "),
              riskTier: mapRiskTier(ex.risk_tier),
              queuedAt: ex.queued_at || ex.created_at,
              dispatchingAt: ex.started_at,
              workerStartedAt: ex.started_at,
              workerFinishedAt: ex.finished_at,
              scopeSnapshot: {
                allowedPaths: ex.scope_snapshot?.allowedPaths || [],
                excludedPaths: ex.scope_snapshot?.excludedPaths || [],
                allowedPorts: ex.scope_snapshot?.allowedPorts || [],
                maxRiskTier: mapRiskTier(ex.scope_snapshot?.maxRiskTier || "tier_1_safe"),
                scopedAssets: ex.scope_snapshot?.scopedAssets || [],
              },
              safetySnapshot: {
                assetVerified: ex.safety_snapshot?.assetVerified ?? true,
                authorizationActive: ex.safety_snapshot?.authorizationActive ?? true,
                engagementActive: ex.safety_snapshot?.engagementActive ?? true,
                scopeMatch: ex.safety_snapshot?.scopeMatch ?? true,
                windowValid: ex.safety_snapshot?.windowValid ?? true,
                killSwitchInactive: ex.safety_snapshot?.killSwitchInactive ?? true,
                riskTierAllowed: ex.safety_snapshot?.riskTierAllowed ?? true,
                credentialIssued: ex.safety_snapshot?.credentialIssued ?? true,
                dispatchBackendAvailable: ex.safety_snapshot?.dispatchBackendAvailable ?? true,
                workerAuthModeReady: ex.safety_snapshot?.workerAuthModeReady ?? true,
              },
              steps: (ex.step_results || []).map((step: any) => ({
                id: step.id,
                name: step.step_name,
                status: step.status === "passed" ? "succeeded" : step.status,
                durationMs: 1200,
                evidencePreview: JSON.stringify(step.evidence),
                safeSummary: step.step_name,
              })),
              events: [],
              credential: {
                id: "cred_" + ex.id.slice(0, 4),
                organizationId: ex.organization_id,
                executionId: ex.id,
                allowedActions: ["worker_started", "worker_finished"],
                issuedAt: ex.created_at,
                expiresAt: ex.created_at,
                revokedAt: null,
                state: "active",
                source: "per_execution",
                fallbackEnabled: false,
              },
              dispatchMessage: {
                messageId: "msg_" + ex.id.slice(0, 4),
                queueName: "validation_executions",
                routingKey: "validation.execute",
                envelopeSchemaVersion: "1",
                payloadHash: "sha256:...",
                publishStatus: "published",
                workerState: ex.status === "executing" ? "running" : ex.status === "succeeded" ? "finished" : "idle",
                lastHeartbeat: ex.updated_at,
              },
            };
          });
          allExecs.push(...mappedExecs);
        } catch (err) {
          console.error(`Error loading details for project ${prj.name}:`, err);
        }
      }

      // Update aggregates on projects and organizations
      const projectsUpdated = projects.map((p) => {
        const projAuths = allAuths.filter((a) => a.projectId === p.id && a.state === "active");
        const projEngs = allEngs.filter((e) => e.projectId === p.id && e.state === "active");
        const projExecs = allExecs.filter((e) => e.projectId === p.id);
        const latestExec = projExecs.length > 0 ? projExecs[projExecs.length - 1] : null;
        return {
          ...p,
          activeAuthorizations: projAuths.length,
          activeEngagements: projEngs.length,
          latestExecutionId: latestExec ? latestExec.code : "",
          lastActivity: latestExec ? latestExec.queuedAt || p.lastActivity : p.lastActivity,
        };
      });

      const orgsUpdated = get().organizations.map((o) => {
        if (o.id !== orgId) return o;
        const orgProjects = projectsUpdated.filter((p) => p.organizationId === orgId);
        const orgAssets = assets.filter((a) => a.organizationId === orgId);
        const orgEngs = allEngs.filter((e) => e.organizationId === orgId && e.state === "active");
        const orgExecs = allExecs.filter((e) => e.organizationId === orgId);
        const latestExec = orgExecs.length > 0 ? orgExecs[orgExecs.length - 1] : null;
        return {
          ...o,
          projectsCount: orgProjects.length,
          verifiedAssets: orgAssets.filter((a) => a.verification === "verified").length,
          activeEngagements: orgEngs.length,
          latestExecutionState: latestExec ? latestExec.status : "succeeded",
          latestExecutionId: latestExec ? latestExec.code : "",
          lastActivity: latestExec ? latestExec.queuedAt || o.lastActivity : o.lastActivity,
        };
      });

      // Fetch audit events, workers, and dispatch queues
      const [rawAuditEvents, rawWorkers, rawQueues] = await Promise.all([
        api.fetchAuditEvents(orgId, 100).catch(() => []),
        api.fetchWorkers(orgId).catch(() => []),
        api.fetchDispatchQueues(orgId).catch(() => []),
      ]);

      const auditEvents: AuditEvent[] = rawAuditEvents.map((e: any) => ({
        id: e.id,
        at: e.at,
        actor: e.actor,
        actorType: e.actor_type,
        action: e.action,
        entityType: e.entity_type,
        entityId: e.entity_id,
        executionId: e.execution_id ?? null,
        safeMetadata: e.safe_metadata ?? {},
      }));

      set({
        assets,
        projects: projectsUpdated,
        authorizations: allAuths,
        engagements: allEngs,
        executions: allExecs,
        organizations: orgsUpdated,
        auditEvents,
        workers: rawWorkers,
        dispatchQueues: rawQueues,
        demoWorkspaceMode: "full"
      });
    } catch (e: any) {
      console.warn("Failed to fetch project data. Falling back to real scan standalone mode.", e);
      set({ 
        demoWorkspaceMode: "real_scan_standalone",
        workspaceWarning: "Optional workspace context failed to load. Workspace seed data unavailable. Real authorized scan mode is still available.",
      });
    } finally {
      set({ isLoading: false });
    }
  },

  addOrg: async (name, slug) => {
    try {
      await api.createOrganization({ name, slug });
      await get().initData();
    } catch (e: any) {
      set({ error: e.message ?? "Failed to create organization" });
      throw e;
    }
  },

  addProject: async (name, slug, description) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.createProject(orgId, { name, slug, description });
    await get().fetchData();
  },

  addAsset: async (payload) => {
    const orgId = get().selectedOrgId;
    const projectId = get().selectedProjectId;
    if (!orgId || !projectId) return;
    await api.createAsset(orgId, {
      ...payload,
      project_id: projectId,
    });
    await get().fetchData();
  },

  verifyAsset: async (assetId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    // For local convenience, let's request verification and then direct verify it.
    await api.requestAssetVerification(orgId, assetId, { method: "dns_txt_record" });
    await get().fetchData();
  },

  addAuthorization: async (payload) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    const mappedPayload = {
      ...payload,
      maximum_risk_tier: mapRiskTierToBackend(payload.maxRiskTier || "moderate"),
      scopes: (payload.scopes || []).map((s: any) => ({
        ...s,
        maximum_requests_per_minute: s.maximum_requests_per_minute || 60,
        maximum_concurrency: s.maximum_concurrency || 5,
      })),
    };
    await api.createAuthorization(orgId, payload.projectId, mappedPayload);
    await get().fetchData();
  },

  submitAuth: async (authId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.submitAuthorization(orgId, authId);
    await get().fetchData();
  },

  activateAuth: async (authId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.activateAuthorization(orgId, authId);
    await get().fetchData();
  },

  addEngagement: async (payload) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    const mappedPayload = {
      ...payload,
      max_risk_tier: mapRiskTierToBackend(payload.maxRiskTier || "moderate"),
      scopes: (payload.scopes || []).map((s: any) => ({
        ...s,
        allowed_ports: s.allowed_ports || [443],
        allowed_paths: s.allowed_paths || ["/"],
        rate_limit_per_minute: s.rate_limit_per_minute || 30,
        concurrency_limit: s.concurrency_limit || 3,
      })),
    };
    await api.createEngagement(orgId, payload.projectId, mappedPayload);
    await get().fetchData();
  },

  scheduleEng: async (engId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.scheduleEngagement(orgId, engId);
    await get().fetchData();
  },

  activateEng: async (engId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.activateEngagement(orgId, engId);
    await get().fetchData();
  },

  pauseEng: async (engId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.pauseEngagement(orgId, engId);
    await get().fetchData();
  },

  resumeEng: async (engId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.resumeEngagement(orgId, engId);
    await get().fetchData();
  },

  completeEng: async (engId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.completeEngagement(orgId, engId);
    await get().fetchData();
  },

  cancelEng: async (engId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.cancelEngagement(orgId, engId);
    await get().fetchData();
  },

  triggerKillSwitch: async (engagementId, active, reason) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.killSwitchEngagement(orgId, engagementId, { active, reason });
    await get().fetchData();
  },

  addExecution: async (payload) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    const mappedPayload = {
      ...payload,
      risk_tier: mapRiskTierToBackend(payload.risk_tier || "moderate"),
    };
    await api.createExecution(orgId, mappedPayload);
    await get().fetchData();
  },

  cancelExec: async (execId) => {
    const orgId = get().selectedOrgId;
    if (!orgId) return;
    await api.cancelExecution(orgId, execId);
    await get().fetchData();
  },

  setLatestAiProofOfRiskAnalysis: (executionId, analysis) => {
    set({
      latestAiProofOfRiskExecutionId: executionId,
      latestAiProofOfRiskAnalysis: analysis,
      aiProofOfRiskLastRunAt: new Date().toISOString(),
    });
  },

  setDomainSafeScanResult: (domain, result) => {
    set({
      latestDomainSafeScanDomain: domain,
      latestDomainSafeScanResult: result,
      latestDomainSafeScanAt: new Date().toISOString()
    });
  },

  clearDomainSafeScanResult: () => {
    set({
      latestDomainSafeScanDomain: null,
      latestDomainSafeScanResult: null,
      latestDomainSafeScanAt: null,
      latestScanMetadata: null
    });
  },
  
  setScanMetadata: (metadata: any) => set({ latestScanMetadata: metadata }),
  setActiveAnalysisSource: (source: AppState["activeAnalysisSource"]) => set({ activeAnalysisSource: source }),
  setActiveSecurityWorkflow: (workflow: AppState["activeSecurityWorkflow"]) => set({ activeSecurityWorkflow: workflow }),
  setLatestManualValidationResult: (result: any) => set({ latestManualValidationResult: result })
}));

// Convenience helpers
export const NAV_ITEMS: { key: RouteKey; label: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "organizations", label: "Organizations" },
  { key: "projects", label: "Projects" },
  { key: "assets", label: "Assets" },
  { key: "authorizations", label: "Authorizations" },
  { key: "engagements", label: "Engagements" },
  { key: "execution_wizard", label: "Executions" },
  { key: "workers", label: "Workers" },
  { key: "audit", label: "Audit" },
  { key: "settings", label: "Settings" },
];

