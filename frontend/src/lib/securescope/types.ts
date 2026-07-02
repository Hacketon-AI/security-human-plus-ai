// ============================================================
// SecureScope — Domain Types
// Mirrors backend flow:
// Organization → Project → Asset → Asset Verification →
// Authorization → Engagement → Validation Execution →
// Dispatch Queue → Worker → Result → Audit
// ============================================================

export type ExecutionStatus =
  | "draft"
  | "queued"
  | "dispatching"
  | "executing"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "blocked";

export type ExecutionOutcome =
  | "validated"
  | "failed_safely"
  | "blocked_by_control"
  | "inconclusive"
  | "not_reproduced";

export type RiskTier = "low" | "moderate" | "high" | "critical";

export type AssetType = "web_api" | "web_app" | "host" | "dns" | "network";
export type AssetCriticality = "low" | "medium" | "high" | "critical";
export type VerificationState =
  | "pending"
  | "verified"
  | "expired"
  | "failed"
  | "cancelled";

export type AuthorizationState = "active" | "expired" | "blocked" | "draft";
export type EngagementState =
  | "draft"
  | "scheduled"
  | "active"
  | "paused"
  | "completed"
  | "cancelled";

export type WorkerEventType =
  | "worker_started"
  | "worker_finished"
  | "failed_safely"
  | "blocked_by_control"
  | "credential_revoked"
  | "dispatch_failed"
  | "auth_expiry_warning";

export type CredentialState = "active" | "expired" | "revoked";

export interface Organization {
  id: string;
  name: string;
  code: string;
  status: "healthy" | "warning" | "critical";
  projectsCount: number;
  verifiedAssets: number;
  activeEngagements: number;
  latestExecutionState: ExecutionStatus;
  latestExecutionId: string;
  lastActivity: string;
}

export interface Project {
  id: string;
  name: string;
  code: string;
  organizationId: string;
  organizationName: string;
  status: "healthy" | "warning" | "critical";
  assetsCount: number;
  activeAuthorizations: number;
  activeEngagements: number;
  latestExecutionId: string;
  lastActivity: string;
}

export interface Asset {
  id: string;
  name: string;
  type: AssetType;
  criticality: AssetCriticality;
  target: string;
  verification: VerificationState;
  ownershipVerified: boolean;
  organizationId: string;
  organizationName: string;
  projectId: string;
  projectName: string;
  lastValidation: string | null;
  tags: string[];
}

export interface AssetVerificationAttempt {
  id: string;
  createdAt: string;
  state: VerificationState;
  method: "dns_txt";
  challengeHost: string;
  durationMs: number;
  note: string;
}

export interface ScopeRule {
  allowedPaths: string[];
  excludedPaths: string[];
  allowedPorts: number[];
  allowedHosts: string[];
}

export interface Authorization {
  id: string;
  code: string;
  organizationId: string;
  organizationName: string;
  projectId: string;
  projectName: string;
  state: AuthorizationState;
  validFrom: string;
  validUntil: string;
  maxRiskTier: RiskTier;
  scopedAssets: string[];
  scopedAssetNames: string[];
  scope: ScopeRule;
  supportingDoc: {
    name: string;
    hash: string;
    signedBy: string;
    signedAt: string;
  };
  approvalTimeline: { at: string; actor: string; action: string }[];
  immutableLock: boolean;
}

export interface Engagement {
  id: string;
  code: string;
  name: string;
  organizationId: string;
  organizationName: string;
  projectId: string;
  projectName: string;
  authorizationId: string;
  authorizationCode: string;
  state: EngagementState;
  windowStart: string;
  windowEnd: string;
  maxRiskTier: RiskTier;
  scopedAssetNames: string[];
  activeExecutions: number;
  killSwitch: {
    state: "inactive" | "armed" | "active";
    activatedBy?: string;
    activatedAt?: string;
    reason?: string;
    affectedExecutions?: string[];
  };
  createdAt: string;
}

export interface ExecutionStepResult {
  id: string;
  name: string;
  status: "succeeded" | "failed" | "skipped" | "blocked" | "inconclusive";
  durationMs: number;
  evidencePreview: string;
  safeSummary: string;
}

export interface ExecutionEvent {
  id: string;
  at: string;
  kind: WorkerEventType;
  label: string;
  safeMeta: Record<string, string>;
}

export interface CredentialRecord {
  id: string;
  organizationId: string;
  executionId: string;
  allowedActions: string[];
  issuedAt: string;
  expiresAt: string;
  revokedAt: string | null;
  state: CredentialState;
  source: "per_execution" | "shared_fallback";
  fallbackEnabled: boolean;
}

export interface ValidationExecution {
  id: string;
  code: string;
  status: ExecutionStatus;
  outcome: ExecutionOutcome | null;
  organizationId: string;
  organizationName: string;
  projectId: string;
  projectName: string;
  assetId: string;
  assetName: string;
  assetTargetMasked: string;
  authorizationId: string;
  authorizationCode: string;
  engagementId: string;
  engagementCode: string;
  templateId: string;
  templateName: string;
  riskTier: RiskTier;
  queuedAt: string | null;
  dispatchingAt: string | null;
  workerStartedAt: string | null;
  workerFinishedAt: string | null;
  scopeSnapshot: {
    allowedPaths: string[];
    excludedPaths: string[];
    allowedPorts: number[];
    maxRiskTier: RiskTier;
    scopedAssets: string[];
  };
  safetySnapshot: {
    assetVerified: boolean;
    authorizationActive: boolean;
    engagementActive: boolean;
    scopeMatch: boolean;
    windowValid: boolean;
    killSwitchInactive: boolean;
    riskTierAllowed: boolean;
    credentialIssued: boolean;
    dispatchBackendAvailable: boolean;
    workerAuthModeReady: boolean;
  };
  steps: ExecutionStepResult[];
  events: ExecutionEvent[];
  credential: CredentialRecord;
  dispatchMessage: {
    messageId: string;
    queueName: string;
    routingKey: string;
    envelopeSchemaVersion: string;
    payloadHash: string;
    publishStatus: "published" | "pending" | "failed";
    workerState: "idle" | "running" | "finished" | "error";
    lastHeartbeat: string;
  };
}

export interface AuditEvent {
  id: string;
  at: string;
  actor: string;
  actorType: "operator" | "system" | "worker" | "scheduler";
  action: string;
  entityType:
    | "organization"
    | "project"
    | "asset"
    | "authorization"
    | "engagement"
    | "execution"
    | "credential"
    | "dispatch"
    | "system";
  entityId: string;
  organizationId?: string;
  projectId?: string;
  assetId?: string;
  executionId?: string;
  safeMetadata: Record<string, string>;
}

export interface DispatchWorkerState {
  workerId: string;
  state: "idle" | "running" | "finished" | "error" | "offline";
  lastHeartbeat: string;
  currentExecutionId: string | null;
  region: string;
}

export interface DispatchQueueState {
  queueName: string;
  routingKey: string;
  pending: number;
  active: number;
  failed: number;
  brokerStatus: "online" | "degraded" | "offline";
}

export type RouteKey =
  | "login"
  | "dashboard"
  | "organizations"
  | "organization_detail"
  | "projects"
  | "project_detail"
  | "assets"
  | "asset_detail"
  | "authorizations"
  | "authorization_detail"
  | "engagements"
  | "engagement_detail"
  | "execution_wizard"
  | "execution_detail"
  | "workers"
  | "audit"
  | "settings";
