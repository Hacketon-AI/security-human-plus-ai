import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock the store — latestAiProofOfRiskAnalysis is null (no analysis loaded)
vi.mock("@/lib/securescope/store", () => ({
  useApp: vi.fn((selector: (s: any) => any) =>
    selector({
      latestAiProofOfRiskAnalysis: null,
      executions: [],
      latestAiProofOfRiskExecutionId: null,
      openExecution: vi.fn(),
    })
  ),
}));

// Mock next/navigation used transitively
vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  usePathname: vi.fn(() => "/"),
}));

import {
  AiRoutingPipelinePanel,
  AttackSurfacePreviewPanel,
  DigitalTwinProofPanel,
  MultiAgentTribunalPanel,
} from "../DashboardAiPanels";

// Requirements: 5.3 — When latestAiProofOfRiskAnalysis is null, each Section B panel
// renders its EmptyState fallback rather than crashing.

describe("Section B panels — EmptyState fallbacks when latestAiProofOfRiskAnalysis is null", () => {
  it("AiRoutingPipelinePanel renders EmptyState when analysis is null", () => {
    render(<AiRoutingPipelinePanel />);
    expect(screen.getByText("AI Routing Pipeline")).toBeInTheDocument();
    expect(screen.getByText("No routing telemetry")).toBeInTheDocument();
  });

  it("AttackSurfacePreviewPanel renders EmptyState when analysis is null", () => {
    render(<AttackSurfacePreviewPanel />);
    expect(screen.getByText("Attack Surface Graph")).toBeInTheDocument();
    expect(screen.getByText("No surface data")).toBeInTheDocument();
  });

  it("DigitalTwinProofPanel renders EmptyState when analysis is null", () => {
    render(<DigitalTwinProofPanel />);
    expect(screen.getByText("Digital Twin Proof")).toBeInTheDocument();
    expect(screen.getByText("Sandbox Proof Disabled")).toBeInTheDocument();
  });

  it("MultiAgentTribunalPanel renders EmptyState when analysis is null", () => {
    render(<MultiAgentTribunalPanel />);
    expect(screen.getByText("Risk Tribunal")).toBeInTheDocument();
    expect(screen.getByText("Multi-Agent Risk Tribunal")).toBeInTheDocument();
  });
});
