/**
 * Unit tests for DispatchStatusStrip and ActivityRail
 *
 * Requirements: 1.1, 1.2, 1.5
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AuditEvent, ValidationExecution } from "@/lib/securescope/types";

// ---------------------------------------------------------------------------
// Mock the Zustand store — must be done before importing components that use it
// ---------------------------------------------------------------------------
const mockStoreState: Record<string, unknown> = {
  executions: [] as ValidationExecution[],
  auditEvents: [] as AuditEvent[],
  engagements: [],
  go: vi.fn(),
};

vi.mock("@/lib/securescope/store", () => {
  const useApp = (selector: (s: typeof mockStoreState) => unknown) =>
    selector(mockStoreState);
  useApp.getState = () => mockStoreState;
  return { useApp };
});

// ---------------------------------------------------------------------------
// Mock heavy dependencies that pull in Next.js / DashboardAiPanels
// ---------------------------------------------------------------------------
vi.mock("../shell/TopNav", () => ({
  TopNavCommandBar: () => null,
}));

vi.mock("../DashboardAiPanels", () => ({
  AiProofOfRiskCommandStrip: () => null,
  DashboardQuickActions: () => null,
  AiProofOfRiskWorkflowRail: () => null,
  AiRoutingPipelinePanel: () => null,
  AttackSurfacePreviewPanel: () => null,
  DigitalTwinProofPanel: () => null,
  MultiAgentTribunalPanel: () => null,
  AuthorizedDomainScanPanel: () => null,
}));

// computeRiskMatrix is a pure utility — let it run normally
// (no mock needed)

// ---------------------------------------------------------------------------
// Import components under test AFTER mocks are set up
// ---------------------------------------------------------------------------
import { DispatchStatusStrip, ActivityRail } from "../DashboardPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeExecution(overrides: Partial<ValidationExecution>): ValidationExecution {
  return {
    id: "exec-1",
    code: "EXEC-20260702-001",
    status: "queued",
    outcome: null,
    organizationId: "org-1",
    organizationName: "Test Org",
    projectId: "proj-1",
    projectName: "Test Project",
    assetId: "asset-1",
    assetName: "Test Asset",
    assetTargetMasked: "example.com",
    authorizationId: "auth-1",
    authorizationCode: "AUTH-001",
    engagementId: "eng-1",
    engagementCode: "ENG-001",
    templateId: "template_basic",
    templateName: "Template Basic",
    riskTier: "moderate",
    queuedAt: new Date().toISOString(),
    dispatchingAt: null,
    workerStartedAt: null,
    workerFinishedAt: null,
    scopeSnapshot: {
      allowedPaths: ["/*"],
      excludedPaths: [],
      allowedPorts: [443],
      maxRiskTier: "moderate",
      scopedAssets: [],
    },
    safetySnapshot: {
      assetVerified: true,
      authorizationActive: true,
      engagementActive: true,
      scopeMatch: true,
      windowValid: true,
      killSwitchInactive: true,
      riskTierAllowed: true,
      credentialIssued: true,
      dispatchBackendAvailable: true,
      workerAuthModeReady: true,
    },
    steps: [],
    events: [],
    credential: {
      id: "cred-1",
      organizationId: "org-1",
      executionId: "exec-1",
      allowedActions: [],
      issuedAt: new Date().toISOString(),
      expiresAt: new Date().toISOString(),
      revokedAt: null,
      state: "active",
      source: "per_execution",
      fallbackEnabled: false,
    },
    dispatchMessage: {
      messageId: "msg-1",
      queueName: "validation_executions",
      routingKey: "validation.execute",
      envelopeSchemaVersion: "1",
      payloadHash: "sha256:abc",
      publishStatus: "published",
      workerState: "idle",
      lastHeartbeat: new Date().toISOString(),
    },
    ...overrides,
  };
}

function makeAuditEvent(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    id: "evt-1",
    at: new Date().toISOString(),
    actor: "operator@test.com",
    actorType: "operator",
    action: "execution.dispatched",
    entityType: "execution",
    entityId: "EXEC-001",
    safeMetadata: {},
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests: DispatchStatusStrip
// ---------------------------------------------------------------------------
describe("DispatchStatusStrip", () => {
  beforeEach(() => {
    mockStoreState.executions = [];
    mockStoreState.auditEvents = [];
    mockStoreState.engagements = [];
  });

  it("renders running execution count from store (1 executing)", () => {
    mockStoreState.executions = [
      makeExecution({ status: "executing" }),
    ];

    render(<DispatchStatusStrip />);

    // The "Running Executions" KPI cell should show "1"
    const runningCell = screen.getByText("1");
    expect(runningCell).toBeDefined();
  });

  it("renders 0 running executions when no execution is executing", () => {
    mockStoreState.executions = [
      makeExecution({ status: "queued" }),
      makeExecution({ id: "exec-2", code: "EXEC-002", status: "succeeded" }),
    ];

    render(<DispatchStatusStrip />);

    // Should show "0" for running executions
    const zeroCell = screen.getByText("0");
    expect(zeroCell).toBeDefined();
  });

  it("renders correct count with multiple executing executions", () => {
    mockStoreState.executions = [
      makeExecution({ id: "exec-1", status: "executing" }),
      makeExecution({ id: "exec-2", code: "EXEC-002", status: "executing" }),
      makeExecution({ id: "exec-3", code: "EXEC-003", status: "queued" }),
    ];

    render(<DispatchStatusStrip />);

    const countCell = screen.getByText("2");
    expect(countCell).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Tests: ActivityRail
// ---------------------------------------------------------------------------
describe("ActivityRail", () => {
  beforeEach(() => {
    mockStoreState.auditEvents = [];
    mockStoreState.go = vi.fn();
  });

  it("renders empty state when auditEvents is empty", () => {
    mockStoreState.auditEvents = [];

    render(<ActivityRail />);

    expect(screen.getByText("No recent activity.")).toBeDefined();
  });

  it("renders event actions from store auditEvents", () => {
    mockStoreState.auditEvents = [
      makeAuditEvent({ id: "evt-1", action: "execution.dispatched", entityId: "EXEC-001" }),
      makeAuditEvent({ id: "evt-2", action: "authorization.activated", entityId: "AUTH-042" }),
    ];

    render(<ActivityRail />);

    expect(screen.getByText("execution.dispatched")).toBeDefined();
    expect(screen.getByText("authorization.activated")).toBeDefined();
  });

  it("renders entityId alongside each event", () => {
    mockStoreState.auditEvents = [
      makeAuditEvent({ id: "evt-1", action: "engagement.started", entityId: "ENG-007" }),
    ];

    render(<ActivityRail />);

    expect(screen.getByText("ENG-007")).toBeDefined();
  });

  it("renders at most 6 events from the store", () => {
    mockStoreState.auditEvents = Array.from({ length: 10 }, (_, i) =>
      makeAuditEvent({ id: `evt-${i}`, action: `action.${i}`, entityId: `ENT-${i}` })
    );

    render(<ActivityRail />);

    // Only the first 6 action labels should be visible
    for (let i = 0; i < 6; i++) {
      expect(screen.getByText(`action.${i}`)).toBeDefined();
    }
    // Events beyond index 5 should not be rendered
    expect(screen.queryByText("action.6")).toBeNull();
  });
});
