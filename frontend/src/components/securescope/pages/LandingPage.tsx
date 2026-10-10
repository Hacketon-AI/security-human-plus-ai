"use client";

import * as React from "react";
import {
  ArrowRight,
  Ban,
  BadgeCheck,
  BrainCircuit,
  CheckCircle2,
  ClipboardList,
  FileCheck2,
  Fingerprint,
  KeyRound,
  ListChecks,
  OctagonX,
  ScanSearch,
  ShieldCheck,
  Target,
  Waves,
} from "lucide-react";
import { useApp } from "@/lib/securescope/store";
import { useLocale, type Locale } from "@/lib/securescope/locale";
import { LocaleToggle } from "../shared/ui";

const COPY = {
  en: {
    nav: { how: "How it works", safety: "Guardrails", ai: "Human + AI", signIn: "Sign in" },
    hero: {
      eyebrow: "Authorized security validation",
      title: "Security testing that never leaves its scope.",
      body: "SecureScope verifies asset ownership, enforces written authorization, and runs safe, scope-locked checks — then turns redacted evidence into proof-of-risk your team can act on.",
      primary: "Open console",
      secondary: "See how it works",
      audience: "Built for regulated teams: banking, fintech, and critical infrastructure.",
    },
    preview: {
      title: "Validation run",
      example: "Example",
      checks: [
        "Asset ownership verified (DNS TXT)",
        "Written authorization active · 29 days left",
        "Target inside approved scope",
        "Rate limit 60 req/min enforced",
        "Kill switch armed",
      ],
      phases: ["Passive recon", "Header checks", "TLS review", "Report"],
      findings: "2 findings · 0 critical",
      redacted: "Evidence redacted before AI review",
    },
    how: {
      title: "From asset to proof in four controlled steps",
      steps: [
        { title: "Verify ownership", body: "Prove you control the asset with a DNS TXT challenge before anything can run." },
        { title: "Authorize in writing", body: "Attach the signed authorization: scope, testing window, risk tier, and rate limits." },
        { title: "Validate within scope", body: "Isolated workers run passive and low-impact checks. Every target is checked against scope." },
        { title: "Prove and remediate", body: "AI turns redacted evidence into proof-of-risk, fixes, and a retest plan your team reviews." },
      ],
    },
    safety: {
      title: "Guardrails, not promises",
      body: "Safety is enforced by the platform, not left to operator discipline.",
      items: [
        { title: "Scope-locked", body: "Targets outside a verified, authorized scope are refused before a single request is sent." },
        { title: "Instant kill switch", body: "Stop any engagement at once. Workers abort between phases and lose their credentials." },
        { title: "Single-scan credentials", body: "Each worker gets a short-lived, least-privilege credential for exactly one execution." },
        { title: "Passive by default", body: "Intrusive checks stay off unless a recorded policy explicitly enables them." },
        { title: "Redacted evidence", body: "Secrets and personal data are masked before evidence reaches AI models or reports." },
        { title: "Complete audit trail", body: "Every decision is recorded: who acted, on what, when, and why." },
      ],
      neverLabel: "SecureScope never performs",
      never: ["Autonomous exploitation", "Denial of service", "Credential harvesting", "Bulk data extraction"],
    },
    ai: {
      eyebrow: "Human + AI",
      title: "AI proposes. Your team decides.",
      body: "AI accelerates the analysis, but every conclusion stays reviewable and every action stays human-approved.",
      points: [
        "Risk tribunal weighs evidence before a finding is confirmed",
        "Remediation guidance tailored to the affected asset",
        "Retest plan to verify each fix",
        "Audit-ready report with full evidence lineage",
      ],
      card: {
        label: "Finding",
        title: "Strict-Transport-Security header missing",
        severity: "Moderate",
        status: "Confirmed by reviewer",
        fix: "Add HSTS with max-age ≥ 31536000 at the gateway, then run the retest plan.",
      },
    },
    cta: { title: "Validate your security posture — safely.", body: "Sign in to manage assets, authorizations, and validation runs.", button: "Open console" },
    footer: { rights: "© 2026 SecureScope", note: "Only for assets you own or are authorized in writing to test." },
  },
  id: {
    nav: { how: "Cara kerja", safety: "Pengaman", ai: "Manusia + AI", signIn: "Masuk" },
    hero: {
      eyebrow: "Validasi keamanan terotorisasi",
      title: "Pengujian keamanan yang tidak pernah keluar dari cakupannya.",
      body: "SecureScope memverifikasi kepemilikan aset, menegakkan otorisasi tertulis, dan menjalankan pengujian aman yang terkunci pada cakupan — lalu mengubah bukti yang telah disamarkan menjadi proof-of-risk yang siap ditindaklanjuti tim Anda.",
      primary: "Buka konsol",
      secondary: "Lihat cara kerja",
      audience: "Dirancang untuk tim di industri teregulasi: perbankan, fintech, dan infrastruktur kritis.",
    },
    preview: {
      title: "Validation run",
      example: "Contoh",
      checks: [
        "Kepemilikan aset terverifikasi (DNS TXT)",
        "Otorisasi tertulis aktif · sisa 29 hari",
        "Target berada dalam cakupan",
        "Batas 60 permintaan/menit diterapkan",
        "Kill switch siaga",
      ],
      phases: ["Recon pasif", "Cek header", "Tinjau TLS", "Laporan"],
      findings: "2 temuan · 0 kritis",
      redacted: "Bukti disamarkan sebelum ditinjau AI",
    },
    how: {
      title: "Dari aset hingga bukti dalam empat langkah terkendali",
      steps: [
        { title: "Verifikasi kepemilikan", body: "Buktikan Anda menguasai aset melalui tantangan DNS TXT sebelum pengujian apa pun berjalan." },
        { title: "Otorisasi tertulis", body: "Lampirkan otorisasi yang ditandatangani: cakupan, jendela waktu, tingkat risiko, dan batas laju." },
        { title: "Validasi dalam cakupan", body: "Worker terisolasi menjalankan pengecekan pasif berdampak rendah. Setiap target dicek terhadap cakupan." },
        { title: "Buktikan dan perbaiki", body: "AI mengubah bukti tersamarkan menjadi proof-of-risk, langkah perbaikan, dan rencana uji ulang untuk ditinjau tim Anda." },
      ],
    },
    safety: {
      title: "Pengaman nyata, bukan sekadar janji",
      body: "Keamanan ditegakkan oleh platform, tidak bergantung pada kedisiplinan operator.",
      items: [
        { title: "Terkunci pada cakupan", body: "Target di luar cakupan yang terverifikasi dan terotorisasi ditolak sebelum satu permintaan pun dikirim." },
        { title: "Kill switch instan", body: "Hentikan engagement kapan saja. Worker berhenti di antara fase dan kehilangan kredensialnya." },
        { title: "Kredensial sekali pakai", body: "Setiap worker mendapat kredensial berumur pendek dengan hak minimum untuk tepat satu eksekusi." },
        { title: "Pasif secara default", body: "Pengujian intrusif tetap nonaktif kecuali diizinkan secara eksplisit oleh kebijakan yang tercatat." },
        { title: "Bukti tersamarkan", body: "Rahasia dan data pribadi disamarkan sebelum bukti mencapai model AI atau laporan." },
        { title: "Jejak audit lengkap", body: "Setiap keputusan tercatat: siapa, terhadap apa, kapan, dan mengapa." },
      ],
      neverLabel: "SecureScope tidak pernah melakukan",
      never: ["Eksploitasi otomatis", "Serangan denial of service", "Pengambilan kredensial", "Ekstraksi data massal"],
    },
    ai: {
      eyebrow: "Manusia + AI",
      title: "AI mengusulkan. Tim Anda yang memutuskan.",
      body: "AI mempercepat analisis, tetapi setiap kesimpulan tetap dapat ditinjau dan setiap tindakan tetap disetujui manusia.",
      points: [
        "Risk tribunal menimbang bukti sebelum temuan dikonfirmasi",
        "Panduan perbaikan yang disesuaikan dengan aset terdampak",
        "Rencana uji ulang untuk memverifikasi setiap perbaikan",
        "Laporan siap audit dengan riwayat bukti lengkap",
      ],
      card: {
        label: "Temuan",
        title: "Header Strict-Transport-Security tidak ada",
        severity: "Sedang",
        status: "Dikonfirmasi peninjau",
        fix: "Tambahkan HSTS dengan max-age ≥ 31536000 di gateway, lalu jalankan rencana uji ulang.",
      },
    },
    cta: { title: "Validasi postur keamanan Anda — dengan aman.", body: "Masuk untuk mengelola aset, otorisasi, dan validation run.", button: "Buka konsol" },
    footer: { rights: "© 2026 SecureScope", note: "Hanya untuk aset milik Anda atau yang telah diizinkan secara tertulis." },
  },
} satisfies Record<Locale, unknown>;

const STEP_ICONS = [Fingerprint, FileCheck2, ScanSearch, ClipboardList];
const SAFETY_ICONS = [Target, OctagonX, KeyRound, Waves, ShieldCheck, ListChecks];

const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400";
const PRIMARY_BUTTON = `inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-cyan-400 px-5 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-300 ${FOCUS_RING}`;
const SECONDARY_BUTTON = `inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-white/15 px-5 text-sm font-semibold text-slate-100 transition-colors hover:bg-white/5 ${FOCUS_RING}`;

export function LandingPage() {
  const go = useApp((state) => state.go);
  const [locale] = useLocale();
  const t = COPY[locale];
  const openConsole = () => go("login");

  return (
    <div className="min-h-screen bg-[#070A12] text-slate-300 antialiased">
      <header className="sticky top-0 z-30 border-b border-white/5 bg-[#070A12]/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <a href="#top" className={`flex items-center gap-2.5 rounded-md ${FOCUS_RING}`}>
            <span className="grid size-8 place-items-center rounded-lg bg-cyan-400/10 ring-1 ring-cyan-400/30">
              <ShieldCheck className="size-4.5 text-cyan-300" aria-hidden />
            </span>
            <span className="text-base font-semibold tracking-tight text-white">SecureScope</span>
          </a>
          <nav aria-label="Primary" className="hidden items-center gap-7 text-sm md:flex">
            <a href="#how" className={`rounded text-slate-400 transition-colors hover:text-white ${FOCUS_RING}`}>{t.nav.how}</a>
            <a href="#safety" className={`rounded text-slate-400 transition-colors hover:text-white ${FOCUS_RING}`}>{t.nav.safety}</a>
            <a href="#ai" className={`rounded text-slate-400 transition-colors hover:text-white ${FOCUS_RING}`}>{t.nav.ai}</a>
          </nav>
          <div className="flex items-center gap-2 sm:gap-3">
            <LocaleToggle />
            <button type="button" onClick={openConsole} className={`${SECONDARY_BUTTON} h-9 px-3.5`}>
              {t.nav.signIn}
            </button>
          </div>
        </div>
      </header>

      <main id="top">
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_45%_at_50%_0%,rgba(34,211,238,0.12),transparent)]" />
          <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pt-24">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-cyan-400/25 bg-cyan-400/5 px-3 py-1 text-xs font-medium text-cyan-200">
                <BadgeCheck className="size-3.5" aria-hidden />
                {t.hero.eyebrow}
              </p>
              <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance text-white sm:text-5xl lg:text-[3.4rem] lg:leading-[1.08]">
                {t.hero.title}
              </h1>
              <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-400 sm:text-lg">{t.hero.body}</p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <button type="button" onClick={openConsole} className={PRIMARY_BUTTON}>
                  {t.hero.primary}
                  <ArrowRight className="size-4" aria-hidden />
                </button>
                <a href="#how" className={SECONDARY_BUTTON}>{t.hero.secondary}</a>
              </div>
              <p className="mt-8 text-sm text-slate-500">{t.hero.audience}</p>
            </div>
            <RunPreview copy={t.preview} />
          </div>
        </section>

        {/* How it works */}
        <section id="how" aria-labelledby="how-title" className="scroll-mt-16 border-t border-white/5 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 id="how-title" className="max-w-2xl text-3xl font-semibold tracking-tight text-balance text-white">{t.how.title}</h2>
            <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {t.how.steps.map((step, index) => {
                const Icon = STEP_ICONS[index];
                return (
                  <li key={step.title} className="rounded-xl border border-white/8 bg-white/[0.02] p-5">
                    <div className="flex items-center justify-between">
                      <Icon className="size-5 text-cyan-300" aria-hidden />
                      <span className="font-mono text-xs text-slate-500">0{index + 1}</span>
                    </div>
                    <h3 className="mt-4 text-base font-semibold text-white">{step.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-slate-400">{step.body}</p>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>

        {/* Guardrails */}
        <section id="safety" aria-labelledby="safety-title" className="scroll-mt-16 border-t border-white/5 bg-white/[0.015] py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 id="safety-title" className="text-3xl font-semibold tracking-tight text-white">{t.safety.title}</h2>
            <p className="mt-3 max-w-2xl text-base text-slate-400">{t.safety.body}</p>
            <ul className="mt-10 grid gap-x-8 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
              {t.safety.items.map((item, index) => {
                const Icon = SAFETY_ICONS[index];
                return (
                  <li key={item.title} className="flex gap-4">
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-400/10 ring-1 ring-emerald-400/25">
                      <Icon className="size-4.5 text-emerald-300" aria-hidden />
                    </span>
                    <div>
                      <h3 className="text-base font-semibold text-white">{item.title}</h3>
                      <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{item.body}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="mt-12 rounded-xl border border-red-400/20 bg-red-400/[0.04] p-5">
              <p className="flex items-center gap-2 text-sm font-semibold text-red-200">
                <Ban className="size-4" aria-hidden />
                {t.safety.neverLabel}
              </p>
              <ul className="mt-3 flex flex-wrap gap-2">
                {t.safety.never.map((item) => (
                  <li key={item} className="rounded-md border border-red-400/20 px-2.5 py-1 text-sm text-red-100/90">{item}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* Human + AI */}
        <section id="ai" aria-labelledby="ai-title" className="scroll-mt-16 border-t border-white/5 py-20">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-2">
            <div>
              <p className="flex items-center gap-2 text-sm font-medium text-cyan-300">
                <BrainCircuit className="size-4" aria-hidden />
                {t.ai.eyebrow}
              </p>
              <h2 id="ai-title" className="mt-3 text-3xl font-semibold tracking-tight text-white">{t.ai.title}</h2>
              <p className="mt-3 text-base leading-relaxed text-slate-400">{t.ai.body}</p>
              <ul className="mt-6 space-y-3">
                {t.ai.points.map((point) => (
                  <li key={point} className="flex gap-3 text-sm text-slate-300">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-cyan-300" aria-hidden />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
            <article className="rounded-2xl border border-white/10 bg-[#0B1120] p-6 shadow-2xl shadow-black/40">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium uppercase tracking-wider text-slate-500">{t.ai.card.label}</span>
                <span className="rounded-full bg-amber-400/10 px-2.5 py-1 font-medium text-amber-200 ring-1 ring-amber-400/25">{t.ai.card.severity}</span>
              </div>
              <h3 className="mt-4 text-lg font-semibold text-white">{t.ai.card.title}</h3>
              <p className="mt-1 font-mono text-xs text-slate-500">api.example-bank.test</p>
              <p className="mt-5 rounded-lg border border-white/8 bg-white/[0.02] p-4 text-sm leading-relaxed text-slate-300">{t.ai.card.fix}</p>
              <p className="mt-5 flex items-center gap-2 text-sm text-emerald-300">
                <BadgeCheck className="size-4" aria-hidden />
                {t.ai.card.status}
              </p>
            </article>
          </div>
        </section>

        {/* Call to action */}
        <section className="border-t border-white/5 py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <div className="rounded-2xl border border-cyan-400/20 bg-[radial-gradient(80%_120%_at_50%_0%,rgba(34,211,238,0.1),transparent)] px-6 py-12 text-center">
              <h2 className="text-3xl font-semibold tracking-tight text-balance text-white">{t.cta.title}</h2>
              <p className="mx-auto mt-3 max-w-lg text-base text-slate-400">{t.cta.body}</p>
              <button type="button" onClick={openConsole} className={`${PRIMARY_BUTTON} mt-8`}>
                {t.cta.button}
                <ArrowRight className="size-4" aria-hidden />
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/5">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>{t.footer.rights}</span>
          <span>{t.footer.note}</span>
        </div>
      </footer>
    </div>
  );
}

function RunPreview({ copy }: { copy: (typeof COPY)[Locale]["preview"] }) {
  return (
    <figure className="rounded-2xl border border-white/10 bg-[#0B1120]/90 p-5 shadow-2xl shadow-cyan-950/30 sm:p-6">
      <figcaption className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{copy.title}</p>
          <p className="mt-0.5 font-mono text-xs text-slate-500">
            <span className="whitespace-nowrap">RUN-0142 ·</span> <span className="whitespace-nowrap">api.example-bank.test</span>
          </p>
        </div>
        <span className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-400">{copy.example}</span>
      </figcaption>
      <ul className="mt-5 space-y-2.5">
        {copy.checks.map((check) => (
          <li key={check} className="flex items-center gap-2.5 text-sm text-slate-300">
            <CheckCircle2 className="size-4 shrink-0 text-emerald-400" aria-hidden />
            {check}
          </li>
        ))}
      </ul>
      <ol className="mt-6 grid grid-cols-4 gap-1.5" aria-label="Phases">
        {copy.phases.map((phase, index) => (
          <li key={phase}>
            <div className={`h-1.5 rounded-full ${index < 3 ? "bg-cyan-400" : "bg-cyan-400/25"}`} />
            <p className="mt-2 text-xs text-slate-500">{phase}</p>
          </li>
        ))}
      </ol>
      <div className="mt-6 flex flex-col gap-2 border-t border-white/8 pt-4 text-sm sm:flex-row sm:items-center sm:justify-between">
        <span className="font-medium text-amber-200">{copy.findings}</span>
        <span className="flex items-center gap-1.5 text-slate-400">
          <ShieldCheck className="size-4 text-emerald-400" aria-hidden />
          {copy.redacted}
        </span>
      </div>
    </figure>
  );
}
