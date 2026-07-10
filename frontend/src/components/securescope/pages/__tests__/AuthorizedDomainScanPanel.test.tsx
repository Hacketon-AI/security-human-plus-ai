/**
 * Unit tests for AuthorizedDomainScanPanel checkbox visibility
 * Requirements: 2.1, 2.2, 2.3
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthorizedDomainScanPanel } from "../DashboardAiPanels";

// Mock the Zustand store
vi.mock("@/lib/securescope/store", () => ({
  useApp: (selector: (s: any) => any) =>
    selector({
      latestDomainSafeScanResult: null,
      latestDomainSafeScanDomain: null,
      setDomainSafeScanResult: vi.fn(),
      clearDomainSafeScanResult: vi.fn(),
      // Satisfy any other store selectors used in sibling components
      latestAiProofOfRiskAnalysis: null,
      latestAiProofOfRiskExecutionId: null,
      executions: [],
      openExecution: vi.fn(),
    }),
}));

// Mock the domain scan API so submitting the form doesn't hit the network
vi.mock("@/lib/securescope/domainSafeScanApi", () => ({
  runDomainSafeScan: vi.fn(),
}));

describe("AuthorizedDomainScanPanel – checkbox visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("CheckCircle2 icon has opacity-0 when the checkbox is unchecked (initial state)", () => {
    render(<AuthorizedDomainScanPanel />);

    // The CheckCircle2 SVG is rendered immediately after the checkbox input
    // in the peer-checked wrapper. Find the authorization checkbox by its label text.
    const checkbox = screen.getByRole("checkbox", { name: /I confirm I own this domain/i });
    // The icon is the SVG sibling inside the same wrapper div
    const wrapper = checkbox.parentElement!;
    const icon = wrapper.querySelector("svg");

    expect(icon).not.toBeNull();
    // SVG elements use SVGAnimatedString for .className — use getAttribute instead
    const classAttr = icon!.getAttribute("class") ?? "";
    expect(classAttr).toContain("opacity-0");
    // The conditional peer-checked:opacity-100 class is always present as a static
    // string in jsdom (Tailwind doesn't strip it). Assert no standalone opacity-100
    // class token exists (i.e., it's not preceded by a space without a prefix).
    const classes = classAttr.split(/\s+/);
    expect(classes).toContain("opacity-0");
    expect(classes).not.toContain("opacity-100");
  });

  it("CheckCircle2 icon has peer-checked:opacity-100 class after checking the checkbox", async () => {
    const user = userEvent.setup();
    render(<AuthorizedDomainScanPanel />);

    const checkbox = screen.getByRole("checkbox", { name: /I confirm I own this domain/i });
    await user.click(checkbox);

    expect(checkbox).toBeChecked();

    const wrapper = checkbox.parentElement!;
    const icon = wrapper.querySelector("svg");

    expect(icon).not.toBeNull();
    // Tailwind's peer-checked:opacity-100 is a static class string in jsdom
    // (jsdom doesn't compute CSS, so the class is always present in the attribute)
    const classAttr = icon!.getAttribute("class") ?? "";
    expect(classAttr).toContain("peer-checked:opacity-100");
  });

  it("CheckCircle2 icon is a sibling of input, not a descendant (peer-checked DOM structure)", () => {
    render(<AuthorizedDomainScanPanel />);

    const checkbox = screen.getByRole("checkbox", { name: /I confirm I own this domain/i });
    const wrapperDiv = checkbox.parentElement!;

    // Both the input and the SVG icon must be direct children of the same wrapper
    const directChildren = Array.from(wrapperDiv.children);
    const inputIsDirectChild = directChildren.includes(checkbox);

    // Find the CheckCircle2 SVG — it should also be a direct child of wrapperDiv
    const svgChildren = directChildren.filter((el) => el.tagName === "svg");
    expect(svgChildren.length).toBeGreaterThanOrEqual(1);

    expect(inputIsDirectChild).toBe(true);

    // Confirm the SVG is NOT nested inside another element within wrapperDiv
    // i.e. it is not a descendant of any non-wrapper element
    svgChildren.forEach((svg) => {
      expect(svg.parentElement).toBe(wrapperDiv);
    });
  });
});
