import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";

// Mock the store module before importing the component
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

import { AiProofOfRiskCommandStrip } from "../DashboardAiPanels";

describe("AiProofOfRiskCommandStrip sticky offset", () => {
  beforeEach(() => {
    // Reset env var — component reads process.env directly at render time
    process.env.NEXT_PUBLIC_USE_MOCK_API = "false";
  });

  it("uses top-(--ss-topnav-height) CSS class on the sticky container", () => {
    const { container } = render(<AiProofOfRiskCommandStrip />);

    // The outermost div is the sticky container
    const stickyContainer = container.firstChild as HTMLElement;

    expect(stickyContainer.className).toContain("top-(--ss-topnav-height)");
  });

  it("does NOT use a hardcoded top-[60px] class on the sticky container", () => {
    const { container } = render(<AiProofOfRiskCommandStrip />);

    const stickyContainer = container.firstChild as HTMLElement;

    expect(stickyContainer.className).not.toContain("top-[60px]");
  });

  it("does NOT use any hardcoded pixel top-[ value on the sticky container", () => {
    const { container } = render(<AiProofOfRiskCommandStrip />);

    const stickyContainer = container.firstChild as HTMLElement;

    // Match top-[<anything>px] pattern — should not appear
    expect(stickyContainer.className).not.toMatch(/top-\[\d+px\]/);
  });
});
