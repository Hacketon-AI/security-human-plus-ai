# Design Document — frontend-audit

## Overview

Five targeted fixes to `DashboardPage.tsx` and `DashboardAiPanels.tsx`:

1. Replace hardcoded data in `DispatchStatusStrip`, `ActivityRail`, and `RiskDistributionMatrix` with store-derived values.
2. Fix the peer-checked checkbox pattern in `AuthorizedDomainScanPanel`.
3. Correct arrow overlay positioning in `ValidationOperationsMap`.
4. Synchronise the `AiProofOfRiskCommandStrip` sticky offset with the TopNav height via a shared CSS custom property.
5. Complete the truncated Section B render block in `DashboardPage.tsx`.

No new routes, APIs, or schema changes are required.

---

## Architecture

All changes are confined to the React component layer and one CSS variable definition. The Zustand store (`store.ts`) is read-only from this fix — no new slices or actions are needed. The store already exposes `executions`, `auditEvents`, `engagements`, and `workers` arrays that provide the raw data needed by the three dashboard components.

```
store.ts  (read-only, no changes)
  └─ DashboardPage.tsx       ← fixes 1, 3, 5
       └─ DashboardAiPanels.tsx  ← fixes 2, 4
TopNav.tsx                   ← fix 4 (set CSS var)
globals.css / layout         ← fix 4 (declare CSS var)
```

---

## Components and Interfaces

### Fix 1 — Store-derived data

**DispatchStatusStrip**: Replace the eight hard-coded `items` objects with computed values:

| Cell | Source |
|---|---|
| Environment | literal (static config) |
| Dispatch Backend | literal or future store slice |
| Worker Auth Mode | literal |
| Shared-token Fallback | literal |
| Global Kill Switch | `engagements.some(e => e.killSwitchArmed)` |
| Running Executions | `executions.filter(e => e.status === "executing").length` |
| Failed / Blocked (24h) | `executions.filter(...)` by status + timestamp window |
| Last Dispatch Event | `auditEvents[0]?.at` formatted as relative time |

**ActivityRail**: Remove the internal `events` array. Map over `useApp(s => s.auditEvents).slice(0, 6)` directly, adapting field names (`e.action` → title, `e.entityId` → detail, `e.at` → timestamp). When `auditEvents` is empty, render an `EmptyState` with message "No recent activity."

**RiskDistributionMatrix**: Replace the hard-coded `matrix` object with a computed one:

```ts
const matrix = executions.reduce((acc, e) => {
  acc[e.riskTier] ??= {};
  acc[e.riskTier][e.outcome ?? "inconclusive"] =
    (acc[e.riskTier][e.outcome ?? "inconclusive"] ?? 0) + 1;
  return acc;
}, {} as Record<string, Record<string, number>>);
```

Reads via `useApp(s => s.executions)`. Zero-fills missing cells at render time.

### Fix 2 — Checkbox peer-checked pattern

Current issue: `CheckCircle2` is wrapped inside the `div` that is itself a sibling of `input.peer`. Tailwind's `peer-checked:opacity-100` only works when the `peer-checked` element is a **subsequent sibling** of the `peer` input in the same parent.

Fix: Make `input.peer` and `CheckCircle2` direct siblings inside the same wrapper `div`, with the icon rendered *after* the input:

```tsx
<div className="relative w-4 h-4">
  <input type="checkbox" className="peer sr-only" ... />
  <div className="w-4 h-4 rounded border ...peer-checked:bg-indigo-500 ...">
    {/* box background only */}
  </div>
  <CheckCircle2 className="absolute inset-0 w-3 h-3 m-auto text-white opacity-0 peer-checked:opacity-100 transition-opacity pointer-events-none" />
</div>
```

Both the background `div` and the icon `CheckCircle2` are siblings of `input.peer`, so `peer-checked:*` resolves correctly.

### Fix 3 — Arrow overlay positioning

Current issue: arrows use `style={{ left: \`${((i+1)/nodes.length)*100}%\` }}` with `position: absolute` on elements inside the grid — this makes them overlap cells and drift with viewport width.

Fix: Replace the absolute-positioned arrows with in-flow flex connectors placed as the `(2i+1)`-th item in the grid (i.e., interleaved between node cards in a flex row, not in the grid):

```tsx
<div className="hidden lg:flex items-center gap-0">
  {nodes.map((n, i) => (
    <React.Fragment key={n.key}>
      <div className="flex-1 min-w-0">
        <PipelineNodeCard node={n} onClick={...} />
      </div>
      {i < nodes.length - 1 && (
        <ArrowRight className="w-3 h-3 text-cyan-500/50 shrink-0 mx-1" />
      )}
    </React.Fragment>
  ))}
</div>
```

Arrows become flex children, naturally centred between cards. Below `lg`, the grid retains its 2/3-column layout with no arrows.

### Fix 4 — Sticky offset synchronisation

**Step A** — Declare the CSS custom property in the global stylesheet or layout:

```css
:root {
  --ss-topnav-height: 76px;
}
```

**Step B** — `TopNav.tsx`: The outer `div` already has `h-[76px]` (confirmed from `DashboardPage.tsx` `pt-[76px]`). No structural change needed; the constant just needs to be declared.

**Step C** — `AiProofOfRiskCommandStrip` in `DashboardAiPanels.tsx`: Replace `top-[60px]` with `top-[var(--ss-topnav-height)]`:

```tsx
<div className="... sticky top-[var(--ss-topnav-height)] z-10 ...">
```

Any future change to `--ss-topnav-height` (e.g., from a warning banner) automatically repositions the strip.

### Fix 5 — Complete Section B render block

`DashboardPage.tsx` is truncated mid-expression after `<AiProofOfRiskWork`. The complete Section B block should be:

```tsx
<AiProofOfRiskWorkflowRail />
<div className="grid lg:grid-cols-2 xl:grid-cols-4 gap-4">
  <AiRoutingPipelinePanel />
  <AttackSurfacePreviewPanel />
  <DigitalTwinProofPanel />
  <MultiAgentTribunalPanel />
</div>
```

This matches the six exports listed in `DashboardAiPanels.tsx` (the `AuthorizedDomainScanPanel` is already placed in Section A).

---

## Data Models

No new types or schema changes. Existing types used:

- `ValidationExecution.riskTier: RiskTier` — `"critical" | "high" | "moderate" | "low"`
- `ValidationExecution.outcome: string | null` — `"validated" | "failed_safely" | "blocked_by_control" | "inconclusive" | null`
- `AuditEvent.at: string` (ISO timestamp), `.actor`, `.action`, `.entityId`

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: RiskDistributionMatrix partition invariant

*For any* array of `ValidationExecution` objects, when the `computeRiskMatrix` function cross-tabulates them by `riskTier` and `outcome`, the sum of all cell values SHALL equal the length of the input array, and every execution SHALL appear in exactly one cell.

**Validates: Requirements 1.3, 1.4**

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `store.executions` is empty | `RiskDistributionMatrix` renders all cells as `0`; no throw |
| `store.auditEvents` is empty | `ActivityRail` renders `EmptyState` — "No recent activity" |
| `store.latestAiProofOfRiskAnalysis` is `null` | Section B panels render their existing `EmptyState` fallbacks |
| `NEXT_PUBLIC_USE_MOCK_API` is `false` | No change; store data drives rendering regardless of flag |

---

## Testing Strategy

**Unit / example tests** (Vitest + React Testing Library):

- `DispatchStatusStrip` renders executing-count from store (example)
- `ActivityRail` renders store `auditEvents`; renders empty state on empty array (example × 2)
- `AuthorizedDomainScanPanel` checkbox: icon is hidden when unchecked, visible when checked (example × 2); DOM structure: icon is sibling of input (structural)
- `ValidationOperationsMap` arrows: hidden below `lg`, no `style.left` % attribute on arrow elements (structural example)
- `AiProofOfRiskCommandStrip` uses `var(--ss-topnav-height)` not a hardcoded pixel value (snapshot)
- Section B panels render `EmptyState` when analysis is `null` (example)
- `tsc --noEmit` passes (smoke — TypeScript compilation)

**Property-based test** (fast-check, minimum 100 iterations):

- Property 1: `computeRiskMatrix(executions)` partition invariant — generate random execution arrays, assert cell sum === array length and no duplicate assignment.

Property test tag format: `// Feature: frontend-audit, Property 1: RiskDistributionMatrix partition invariant`
