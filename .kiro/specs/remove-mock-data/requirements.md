# Requirements Document

## Introduction

Fitur ini menghapus semua data dummy/mock dari frontend SecureScope dan menggantinya dengan data nyata dari backend API yang tersedia, atau menampilkan `EmptyState` untuk bagian yang belum memiliki endpoint backend.

## Glossary

- **Store**: Zustand store di `store.ts` yang mengelola state global aplikasi
- **AuditPage**: Halaman audit trail di `AuditPage.tsx`
- **WorkersPage**: Halaman monitoring worker/dispatch di `WorkersPage.tsx`
- **EmptyState**: Komponen UI yang menampilkan pesan kosong ketika data tidak tersedia
- **Mock_Data**: Data statis di `data.ts` yang saat ini digunakan sebagai placeholder

## Requirements

### Requirement 1: Hapus Mock AuditEvents dari Store

**User Story:** Sebagai operator, saya ingin audit trail menampilkan data kosong (bukan data palsu) ketika backend belum menyediakan endpoint audit, sehingga tidak ada data dummy yang muncul seolah-olah nyata.

#### Acceptance Criteria

1. THE Store SHALL initialize `auditEvents` sebagai array kosong `[]`, bukan `mockAuditEvents` dari `data.ts`
2. WHEN `store.ts` di-load, THE Store SHALL NOT import `auditEvents` dari `data.ts`
3. WHILE `auditEvents` kosong, THE AuditPage SHALL menampilkan `EmptyState` dengan pesan "No audit events available"

---

### Requirement 2: Hapus Fallback Demo Org dari addOrg

**User Story:** Sebagai operator, saya ingin pembuatan organisasi selalu memanggil backend API, sehingga tidak ada objek lokal dengan ID `demo-*` yang tidak valid untuk operasi lain.

#### Acceptance Criteria

1. WHEN `addOrg` dipanggil dan backend API gagal, THE Store SHALL propagate error tersebut ke caller tanpa membuat objek organisasi lokal
2. THE Store SHALL NOT menggunakan ID dengan format `demo-${Date.now()}` untuk organisasi apapun
3. IF `api.createOrganization` melempar error, THEN THE Store SHALL set `error` state dengan pesan yang deskriptif

---

### Requirement 3: Hapus Import Mock dispatchQueues dan workers dari WorkersPage

**User Story:** Sebagai operator, saya ingin bagian broker status dan worker fleet tidak menampilkan data palsu, sehingga status yang terlihat mencerminkan kondisi nyata atau kosong.

#### Acceptance Criteria

1. THE WorkersPage SHALL NOT import `dispatchQueues` atau `workers` dari `data.ts`
2. WHILE tidak ada endpoint backend untuk dispatch queues, THE WorkersPage SHALL menampilkan `EmptyState` pada section "Broker & queue status" dengan pesan "Queue data unavailable — no backend endpoint"
3. WHILE tidak ada endpoint backend untuk workers, THE WorkersPage SHALL menampilkan `EmptyState` pada section "Worker fleet" dengan pesan "Worker data unavailable — no backend endpoint"

---

### Requirement 4: Hapus Hardcoded Events dari WorkersPage

**User Story:** Sebagai operator, saya ingin worker event timeline tidak menampilkan event palsu dengan timestamp dan ID yang dikodekan langsung, sehingga timeline hanya menampilkan event nyata dari eksekusi aktual.

#### Acceptance Criteria

1. THE WorkersPage SHALL NOT render `EventTimeline` dengan event hardcoded (ID seperti `wt1`, `wt2`, dll.)
2. WHILE tidak ada eksekusi aktif, THE WorkersPage SHALL menampilkan `EmptyState` pada section "Worker event timeline"
3. WHEN terdapat eksekusi aktif di store, THE WorkersPage SHALL menampilkan events dari `exec.events` array tersebut

---

### Requirement 5: Perbaiki openExecution Hardcoded di AuditPage

**User Story:** Sebagai operator, saya ingin klik pada execution ID di audit trail membuka eksekusi yang benar, bukan selalu membuka `exec_002` yang dikodekan langsung.

#### Acceptance Criteria

1. WHEN operator mengklik `executionId` di baris audit event, THE AuditPage SHALL memanggil `openExecution` dengan ID eksekusi yang sesuai dari field `e.executionId`
2. THE AuditPage SHALL NOT memanggil `openExecution("exec_002")` sebagai nilai hardcoded
3. IF eksekusi dengan `e.executionId` tidak ditemukan di store, THEN THE AuditPage SHALL tidak melakukan navigasi
