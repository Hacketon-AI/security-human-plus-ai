# Implementation Plan: remove-mock-data

## Overview

Hapus semua data mock/dummy dari frontend. Tiga file yang terpengaruh: `store.ts`, `WorkersPage.tsx`, `AuditPage.tsx`. Tidak ada perubahan backend.

## Tasks

- [ ] 1. Hapus mock auditEvents dari store.ts
  - [ ] 1.1 Hapus `import { auditEvents as mockAuditEvents }` dari `data.ts`
  - [ ] 1.2 Ubah init `auditEvents` dari `mockAuditEvents` menjadi `[]`
  - _Requirements: 1.1, 1.2_

- [ ] 2. Hapus fallback demo org di addOrg (store.ts)
  - [ ] 2.1 Hapus blok `catch` yang membuat objek org lokal dengan ID `demo-${Date.now()}`
  - [ ] 2.2 Set `error` state dengan `e.message ?? "Failed to create organization"`, lalu `throw` error
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. Hapus import mock dan ganti sections di WorkersPage.tsx
  - [ ] 3.1 Hapus `import { dispatchQueues, workers }` dari `@/lib/securescope/data`
  - [ ] 3.2 Ganti `dispatchQueues.map(...)` dengan `<EmptyState title="Queue data unavailable — no backend endpoint" />`
  - [ ] 3.3 Ganti `workers.map(...)` dengan `<EmptyState title="Worker data unavailable — no backend endpoint" />`
  - [ ] 3.4 Ganti hardcoded `<EventTimeline events={[...]} />` — jika ada `exec` aktif tampilkan `exec.events`, jika tidak tampilkan `<EmptyState />`
  - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3_

- [ ] 4. Fix hardcoded openExecution di AuditPage.tsx
  - [ ] 4.1 Tambah kondisi: jika `auditEvents.length === 0`, render `<EmptyState title="No audit events available" />`
  - [ ] 4.2 Ganti `openExecution("exec_002")` dengan `if (e.executionId) openExecution(e.executionId)`
  - _Requirements: 1.3, 5.1, 5.2, 5.3_

- [ ] 5. Final checkpoint — type-check dan unit tests
  - Jalankan `tsc --noEmit` dari root frontend, pastikan tidak ada type error
  - Jalankan `vitest run` untuk memastikan tidak ada test yang rusak akibat penghapusan mock
  - Tanya user jika ada error yang tidak jelas

## Notes

- Task 1 dan 2 sama-sama menyentuh `store.ts` — harus sequential
- Task 3 dan 4 masing-masing menyentuh file berbeda — bisa paralel setelah task 1 selesai
- Task 5 hanya berjalan setelah semua implementasi selesai
- `data.ts` tidak diubah — mungkin masih dipakai bagian lain

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "4.1", "4.2"] }
  ]
}
```
