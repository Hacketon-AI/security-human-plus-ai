/**
 * Unit tests for ValidationOperationsMap arrow positioning.
 * Requirements: 3.1, 3.2, 3.3
 *
 * Since jsdom doesn't process responsive CSS breakpoints, these tests validate
 * the CSS class structure that enforces correct responsive behaviour.
 */

import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mock the Zustand store so the component renders without a real store
// ---------------------------------------------------------------------------
vi.mock("@/lib/securescope/store", () => ({
  useApp: vi.fn((selector: (s: any) => any) =>
    selector({
      go: vi.fn(),
      openAsset: vi.fn(),
      openExecution: vi.fn(),
      assets: [],
      authorizations: [],
      engagements: [],
      executions: [],
      auditEvents: [],
    })
  ),
}));

// Mock the computeRiskMatrix utility (imported by the same file)
vi.mock("@/lib/securescope/computeRiskMatrix", () => ({
  computeRiskMatrix: vi.fn(() => ({})),
}));

// Import only the component under test — avoids pulling in TopNav, AiPanels, etc.
import { ValidationOperationsMap } from "../DashboardPage";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ValidationOperationsMap — arrow positioning (Req 3.1, 3.2, 3.3)", () => {
  it("no arrow element has an inline style.left percentage attribute", () => {
    const { container } = render(<ValidationOperationsMap />);

    // ArrowRight from lucide-react renders as <svg>. Collect all svg elements.
    const allSvgs = Array.from(container.querySelectorAll("svg"));

    const withPercentLeft = allSvgs.filter((svg) => {
      const left = (svg as unknown as HTMLElement).style?.left;
      return typeof left === "string" && left.includes("%");
    });

    expect(withPercentLeft).toHaveLength(0);
  });

  it("the large-viewport flex row that contains arrows has the 'hidden' class (arrows hidden below lg)", () => {
    const { container } = render(<ValidationOperationsMap />);

    // The large-viewport connector row is `hidden lg:flex items-center gap-0`
    const flexRow = container.querySelector(".hidden.lg\\:flex");
    expect(flexRow).not.toBeNull();

    // Confirm `hidden` class is present — this is what hides it below lg
    expect(flexRow!.classList.contains("hidden")).toBe(true);
  });

  it("the small-viewport grid has 'lg:hidden' class so arrows are absent there", () => {
    const { container } = render(<ValidationOperationsMap />);

    // The small-viewport grid is `grid grid-cols-2 md:grid-cols-3 gap-2 lg:hidden`
    const smallGrid = container.querySelector(".lg\\:hidden.grid");
    expect(smallGrid).not.toBeNull();
    expect(smallGrid!.classList.contains("lg:hidden")).toBe(true);
  });

  it("connector ArrowRight elements (shrink-0 class) are inside the lg:flex row only, not in the small-viewport grid", () => {
    const { container } = render(<ValidationOperationsMap />);

    const flexRow = container.querySelector(".hidden.lg\\:flex") as Element;
    const smallGrid = container.querySelector(".lg\\:hidden.grid") as Element;

    expect(flexRow).not.toBeNull();
    expect(smallGrid).not.toBeNull();

    // Connector arrows rendered by ArrowRight have the `shrink-0` class applied
    const connectorArrowsInFlexRow = Array.from(flexRow.querySelectorAll("svg")).filter(
      (svg) => svg.classList.contains("shrink-0")
    );
    expect(connectorArrowsInFlexRow.length).toBeGreaterThan(0);

    // No shrink-0 connector arrows should exist in the small-viewport grid
    const connectorArrowsInSmallGrid = Array.from(smallGrid.querySelectorAll("svg")).filter(
      (svg) => svg.classList.contains("shrink-0")
    );
    expect(connectorArrowsInSmallGrid).toHaveLength(0);
  });
});
