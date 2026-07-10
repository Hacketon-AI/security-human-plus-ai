# Implementation Plan: frontend-audit

## Overview

Five targeted fixes to `DashboardPage.tsx` and `DashboardAiPanels.tsx`: replace hardcoded data with store-derived values, fix the checkbox peer pattern, correct arrow overlay positioning, sync the sticky offset via CSS variable, and complete the truncated Section B render block.

## Tasks

- [x] 1. Replace hardcoded data with store-derived values in DashboardPage.tsx
  - [x] 1.1 Wire DispatchStatusStrip to store state
    - Read `useApp` to get `executions`, `auditEvents`, `engagements`, `workers`
    - Compute each of the 8 cell values from store (see design Fix 1 table)
    - Remove inline literal strings for dynamic cells
    - _Requirements: 1.1_

  - [x] 1.2 Wire ActivityRail to store auditEvents
    - Replace internal `events` array with `useApp(s => s.auditEvents).slice(0, 6)`
    - Map `e.action` → title, `e.entityId` → detail, `e.at` → timestamp
    - Render `EmptyState` with "No recent activity." when array is empty
    - _Requirements: 1.2, 1.5_

  - [x] 1.3 Wire RiskDistributionMatrix to store executions
    - Extract `computeRiskMatrix` as a pure function in a utility file (e.g., `lib/securescope/computeRiskMatrix.ts`)
    - Replace hardcoded `matrix` object with `computeRiskMatrix(useApp(s => s.executions))`
    - Zero-fill missing cells at render time
    - _Requirements: 1.3, 1.4_

  - [x] 1.4 Write property test for computeRiskMatrix (Property 1)
    - **Property 1: RiskDistributionMatrix partition invariant**
    - Generate random `ValidationExecution` arrays via fast-check; assert cell sum equals input length and no execution appears in more than one cell
    - Tag: `// Feature: frontend-audit, Property 1: RiskDistributionMatrix partition invariant`
    - **Validates: Requirements 1.3, 1.4**

  - [x] 1.5 Write unit tests for ActivityRail and DispatchStatusStrip
    - `DispatchStatusStrip`: renders executing-count from store
    - `ActivityRail`: renders store events; renders empty state on empty array
    - _Requirements: 1.1, 1.2, 1.5_

- [x] 2. Fix AuthorizedDomainScanPanel checkbox visibility
  - [x] 2.1 Restructure peer-checked DOM in AuthorizedDomainScanPanel
    - Make `input.peer` (sr-only), background `div`, and `CheckCircle2` direct siblings inside one wrapper `div`
    - Render `CheckCircle2` *after* the input so `peer-checked:opacity-100` resolves
    - Remove any wrapper that currently encloses the icon as a descendant of a non-peer element
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.2 Write unit tests for checkbox visibility
    - Unchecked: icon has `opacity-0`; checked: icon has `opacity-100`
    - Structural: `CheckCircle2` is a sibling of `input`, not a descendant
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Correct ValidationOperationsMap arrow overlay positioning
  - [x] 3.1 Replace absolute-positioned arrows with interleaved flex connectors
    - Wrap the map in `hidden lg:flex items-center gap-0`
    - Interleave `<ArrowRight>` between node cards using `React.Fragment`; remove the `style.left` percentage calculation
    - Keep the existing `<= lg` grid layout with no arrows via `lg:hidden` on the old grid
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 3.2 Write unit tests for arrow positioning
    - Assert no arrow element has a `style.left` percentage attribute
    - Assert arrows are hidden below `lg` breakpoint
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 4. Synchronise AiProofOfRiskCommandStrip sticky offset
  - [x] 4.1 Declare --ss-topnav-height CSS custom property and update sticky offset
    - Add `--ss-topnav-height: 76px` to `:root` in `globals.css` (or the root layout stylesheet)
    - Replace `top-[60px]` with `top-(--ss-topnav-height)` on `AiProofOfRiskCommandStrip`
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.2 Write snapshot test for AiProofOfRiskCommandStrip sticky class
    - Assert the sticky container uses `top-(--ss-topnav-height)` and not a hardcoded pixel value
    - _Requirements: 4.1_

- [x] 5. Complete Section B render block and fix file truncation
  - [x] 5.1 Complete the truncated DashboardPage.tsx Section B block
    - Complete the mid-expression cut after `<AiProofOfRiskWork`
    - Add the full Section B render: `<AiProofOfRiskWorkflowRail />`, grid with `<AiRoutingPipelinePanel />`, `<AttackSurfacePreviewPanel />`, `<DigitalTwinProofPanel />`, `<MultiAgentTribunalPanel />`
    - Ensure all JSX tags are closed and the file compiles (`tsc --noEmit`)
    - _Requirements: 5.1, 5.2_

  - [x] 5.2 Write unit tests for Section B EmptyState fallbacks
    - When `latestAiProofOfRiskAnalysis` is `null`, each Section B panel renders its `EmptyState`
    - _Requirements: 5.3_

- [x] 6. Final checkpoint — Ensure all tests pass
  - Run `tsc --noEmit` and the test suite; resolve any remaining errors.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster fix pass
- Property test (1.4) requires fast-check; add it as a dev dependency if not present
- All fixes are confined to `DashboardPage.tsx`, `DashboardAiPanels.tsx`, one new utility file, and `globals.css`
- Fix 5 must be done before running TypeScript compilation checks

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.3", "5.1"] },
    { "id": 1, "tasks": ["1.1", "1.2", "2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.2", "3.2", "4.2", "5.2"] }
  ]
}
```
