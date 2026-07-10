# Design Document — remove-mock-data

## Overview

Menghapus semua data statis/mock dari frontend dan menggantinya dengan state kosong atau data nyata dari store. Tidak ada perubahan backend. Semua perubahan bersifat frontend-only dan minimal.

## Architecture

Perubahan bersifat frontend-only. Tidak ada lapisan baru — hanya modifikasi state init dan conditional rendering pada komponen yang ada.

```
store.ts  →  auditEvents: []  (hapus mockAuditEvents)
           →  addOrg: propagate error, hapus fallback lokal

AuditPage.tsx  →  EmptyState jika auditEvents kosong
               →  openExecution(e.executionId) tanpa hardcode

WorkersPage.tsx  →  EmptyState untuk broker, worker fleet, timeline
                 →  hapus import dari data.ts
```

## Components and Interfaces

| Komponen/Module | Perubahan |
|---|---|
| `store.ts` — `SecureScopeStore` | `auditEvents` init `[]`; `addOrg` tanpa fallback lokal |
| `AuditPage.tsx` | Render `<EmptyState>` kondisional; fix `openExecution` handler |
| `WorkersPage.tsx` | Hapus import `dispatchQueues`, `workers`; render `<EmptyState>` per section |
| `EmptyState` | Digunakan dengan prop `title` — tidak ada perubahan komponen itu sendiri |

## Data Models

Tidak ada perubahan tipe data. Model yang relevan tetap sama:

- `AuditEvent[]` — array tetap, hanya nilai awal berubah dari mock ke `[]`
- `Organization` — tidak ada perubahan; ID format `demo-*` dihilangkan dari runtime
- State `error: string | null` di store — diisi dengan `e.message` saat `addOrg` gagal

## Correctness Properties

Fitur ini adalah penghapusan data dummy dan conditional rendering sederhana — tidak ada logika transformasi data yang memerlukan property-based testing.

Fitur ini adalah penghapusan data dummy — tidak ada transformasi data kompleks yang memerlukan property-based testing. Verifikasi dilakukan melalui unit test sederhana.

### Property 1: Store tidak mengandung mock data saat init

*For any* fresh store initialization, `auditEvents` SHALL be an empty array and SHALL NOT contain any entries originating from `data.ts`.

**Validates: Requirements 1.1, 1.2**

### Property 2: addOrg tidak menghasilkan ID demo

*For any* failed `api.createOrganization` call, the store SHALL NOT contain any organization with an ID matching the pattern `demo-*`.

**Validates: Requirements 2.1, 2.2**

## Affected Files

| File | Perubahan |
|---|---|
| `frontend/src/lib/securescope/store.ts` | Hapus import `auditEvents` dari `data.ts`; init `auditEvents: []`; hapus fallback local org di `addOrg` |
| `frontend/src/components/securescope/pages/AuditPage.tsx` | Tampilkan `EmptyState` ketika `auditEvents` kosong; perbaiki `openExecution` hardcoded |
| `frontend/src/components/securescope/pages/WorkersPage.tsx` | Hapus import `dispatchQueues` dan `workers` dari `data.ts`; ganti section broker/worker/timeline dengan `EmptyState` |

File `data.ts` tidak diubah — mungkin masih dipakai bagian lain.

## Changes per File

### `store.ts`
- Hapus: `import { auditEvents as mockAuditEvents } from "./data";`
- Ubah init: `auditEvents: []` (dari `mockAuditEvents`)
- Di `addOrg`: hapus blok `catch` yang membuat objek org lokal; biarkan error propagate, dan set `error` state dengan `e.message`

### `WorkersPage.tsx`
- Hapus: `import { dispatchQueues, workers } from "@/lib/securescope/data";`
- Section "Broker & queue status": ganti `dispatchQueues.map(...)` dengan `<EmptyState title="Queue data unavailable — no backend endpoint" />`
- Section "Worker fleet": ganti `workers.map(...)` dengan `<EmptyState title="Worker data unavailable — no backend endpoint" />`
- Section "Worker event timeline": ganti `<EventTimeline events={[...hardcoded...]} />` dengan kondisional — jika ada `exec` aktif tampilkan `exec.events`, jika tidak tampilkan `EmptyState`

### `AuditPage.tsx`
- Tambah kondisi: jika `auditEvents.length === 0`, render `<EmptyState title="No audit events available" />`
- Perbaiki handler `onClick` pada `executionId`: gunakan `e.executionId` langsung ke `openExecution`; guard jika tidak ada (`if (e.executionId) openExecution(e.executionId)`)
- Hapus: referensi hardcoded `"exec_002"`

## Data / State Changes

- `auditEvents` di store: `AuditEvent[]` tetap, hanya init dari `mockAuditEvents` → `[]`
- Tidak ada perubahan tipe/schema

## Error Handling

- `addOrg` error: `set({ error: e.message ?? "Failed to create organization" })` lalu `throw` agar caller bisa handle

## Testing Strategy

Tidak ada PBT — semua perubahan adalah code removal dan UI conditional rendering sederhana. Verifikasi manual:

1. Login → buka Audit Trail → pastikan EmptyState muncul (bukan event palsu)
2. Login → buka Workers → pastikan broker/worker/timeline sections menampilkan EmptyState
3. Coba buat org ketika backend down → pastikan error muncul, tidak ada org `demo-*`
4. (Jika ada audit event dengan executionId) klik ID → pastikan navigasi ke eksekusi yang benar
