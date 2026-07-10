# Requirements Document

## Introduction

Audit findings for the SecureScope frontend (Next.js 14 / App Router, TypeScript, Tailwind CSS). The codebase uses a single-page route-switch in `page.tsx`, a Zustand store for global state, and two primary dashboard files (`DashboardPage.tsx`, `DashboardAiPanels.tsx`). Six categories of quality issues were identified: hardcoded mock data leaking into production views, a broken CSS checkbox interaction, misaligned arrow overlays in the pipeline grid, an unverified sticky-bar offset, an incomplete file truncation, and the absence of any Next.js router integration.

## Glossary

- **Dashboard**: The primary view rendered by `DashboardPage.tsx` and its sub-components from `DashboardAiPanels.tsx`.
- **Store**: The Zustand store in `frontend/src/lib/securescope/store.ts` that holds all live application state.
- **DispatchStatusStrip**: The 8-cell KPI bar at the top of Section A of the Dashboard.
- **ActivityRail**: The right-side live event feed in Section A of the Dashboard.
- **RiskDistributionMatrix**: The risk-tier × outcome matrix table in the intelligence layer of Section A.
- **AiProofOfRiskCommandStrip**: The sticky 6-cell status bar rendered below the TopNav in Section B.
- **ValidationOperationsMap**: The 6-node pipeline visualization in Section A.
- **AuthorizedDomainScanPanel**: The authorized domain scan form in Section A.
- **TopNav**: The top navigation bar rendered by `TopNavCommandBar` in `shell/TopNav`.
- **Router**: The Next.js App Router (`next/navigation`).
- **go()**: The custom Zustand action used for all in-app navigation (`store.go(routeKey)`).
- **NEXT_PUBLIC_USE_MOCK_API**: Environment flag that gates mock vs. live API calls.

---

## Requirements

### Requirement 1: Replace Hardcoded Dashboard Data with Store-Derived Data

**User Story:** As a SecureScope operator, I want the Dashboard to display live data from the store, so that the metrics I see accurately reflect the current state of operations.

#### Acceptance Criteria

1. WHEN the Dashboard renders the DispatchStatusStrip, THE Dashboard SHALL derive each cell's value from store state (executions, engagements, auditEvents, workers) rather than from inline literal strings.
2. WHEN the Dashboard renders the ActivityRail, THE ActivityRail SHALL map over store `auditEvents` (or a dedicated `activityEvents` slice) instead of the hardcoded `events` array defined inside the component.
3. WHEN the Dashboard renders the RiskDistributionMatrix, THE RiskDistributionMatrix SHALL compute cell counts by cross-tabulating `store.executions` by `riskTier` and `outcome` rather than using the hardcoded `matrix` object.
4. IF `store.executions` is empty, THEN THE RiskDistributionMatrix SHALL render all cells as zero without throwing.
5. IF `store.auditEvents` is empty, THEN THE ActivityRail SHALL render an empty list with an appropriate empty-state message instead of rendering no items.

---

### Requirement 2: Fix AuthorizedDomainScanPanel Checkbox Visibility

**User Story:** As an operator using the domain scan form, I want the authorization checkbox to display a visible checkmark when checked, so that I can confirm my authorization intent without ambiguity.

#### Acceptance Criteria

1. WHEN the authorization checkbox is checked, THE AuthorizedDomainScanPanel SHALL display the `CheckCircle2` icon as visible (opacity 1).
2. WHEN the authorization checkbox is unchecked, THE AuthorizedDomainScanPanel SHALL display the `CheckCircle2` icon as hidden (opacity 0).
3. THE AuthorizedDomainScanPanel SHALL implement the peer-checked pattern by placing the `CheckCircle2` icon as a sibling element to the `peer` input, not as a descendant, so that the Tailwind `peer-checked:opacity-100` class resolves correctly.

---

### Requirement 3: Correct ValidationOperationsMap Arrow Overlay Positioning

**User Story:** As an operator viewing the pipeline map, I want the connector arrows between pipeline nodes to be visually aligned with the nodes they connect, so that the flow is unambiguous.

#### Acceptance Criteria

1. WHEN the Dashboard renders the ValidationOperationsMap at `lg` breakpoint or wider, THE ValidationOperationsMap SHALL position each connector arrow between its left-adjacent node card and its right-adjacent node card using a layout method that is not dependent on percentage-of-parent-width calculations.
2. THE ValidationOperationsMap SHALL use CSS Grid or Flexbox gap-aware connector elements (e.g., absolute children of each grid cell, or a dedicated connector row) so that arrow positions remain correct when the viewport is resized.
3. IF the viewport is narrower than the `lg` breakpoint, THEN THE ValidationOperationsMap SHALL hide all connector arrows.

---

### Requirement 4: Verify and Stabilize AiProofOfRiskCommandStrip Sticky Offset

**User Story:** As an operator, I want the AI command strip to appear flush below the TopNav without overlapping or leaving a gap, so that the layout remains consistent as the TopNav height changes.

#### Acceptance Criteria

1. THE AiProofOfRiskCommandStrip SHALL read the TopNav's rendered height from a shared CSS custom property (e.g., `--ss-topnav-height`) or a shared constant, and apply that value as its `top` offset rather than the hardcoded `top-[60px]`.
2. THE TopNav component SHALL expose or set the same height value so that AiProofOfRiskCommandStrip and any other sticky children remain synchronized.
3. WHEN the TopNav height changes (e.g., due to a warning banner or responsive reflow), THE AiProofOfRiskCommandStrip SHALL reposition itself without manual intervention.

---

### Requirement 5: Complete DashboardPage Section B Render Block and Resolve File Truncation

**User Story:** As a developer maintaining the Dashboard, I want `DashboardPage.tsx` to be complete and syntactically valid, so that the Section B AI Intelligence panels render correctly and the file can be read and edited without truncation issues.

#### Acceptance Criteria

1. THE DashboardPage SHALL include a complete, valid render block for Section B that mounts `AiProofOfRiskWorkflowRail`, `AiRoutingPipelinePanel`, `AttackSurfacePreviewPanel`, `DigitalTwinProofPanel`, `MultiAgentTribunalPanel`, and `AuthorizedDomainScanPanel` as documented in `DashboardAiPanels.tsx`.
2. THE DashboardPage file SHALL be syntactically complete — no unclosed JSX tags, no trailing mid-expression cuts — so that TypeScript compilation succeeds without errors in this file.
3. WHEN `NEXT_PUBLIC_USE_MOCK_API` is `false` and no AI analysis is present in the store, THE Section B panels SHALL render their respective `EmptyState` fallbacks rather than crashing.
