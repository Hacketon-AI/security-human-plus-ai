"use client";

import * as React from "react";
import { useApp } from "@/lib/securescope/store";
import { useLocale, type Locale } from "@/lib/securescope/locale";
import { BrandLogo, LocaleToggle } from "../shared/ui";

// Terminal and code artifacts stay in English in both locales: they mirror
// what the product actually prints. Only the prose around them is translated.
const COPY = {
  en: {
    nav: [
      { href: "#procedure", label: "procedure" },
      { href: "#guarantees", label: "guarantees" },
      { href: "#author", label: "author" },
    ],
    signIn: "sign in",
    docTitle: "Authorized Security Validation",
    name: "NAME",
    tagline: "authorized security testing that refuses to leave its scope",
    title: "Security testing that refuses to leave its scope.",
    description:
      "Double AA verifies that you own an asset, holds you to a written authorization, and runs only safe checks inside the approved scope. Findings arrive as redacted, reviewable proof-of-risk with a fix and a retest plan.",
    openConsole: "open console",
    readProcedure: "read the procedure",
    terminalHint: "Try it. Only api.example-bank.test is authorized in this simulation.",
    terminalLabel: "scope gate simulation · no network requests",
    examples: "examples",
    run: "run",
    targetLabel: "Scan target",
    procedureTitle: "PROCEDURE",
    procedureLead: "Every run follows the same four steps. Nothing is skipped and nothing runs early.",
    steps: [
      { title: "Verify ownership", body: "Publish a one-time DNS TXT record. Until it resolves, the asset cannot be tested." },
      { title: "Authorize in writing", body: "Record the signed authorization: scope, validity window, risk tier, and rate limits." },
      { title: "Validate within scope", body: "An isolated worker runs passive, low-impact checks with a credential valid for this execution only. The kill switch is polled between phases." },
      { title: "Prove and remediate", body: "Evidence is redacted, analysed with AI assistance, and confirmed by a human reviewer before it becomes a finding." },
    ],
    guaranteesTitle: "GUARANTEES",
    guaranteesLead: "Enforced by the platform. None of these depend on operator discipline.",
    guarantees: [
      { title: "Scope-locked", body: "A target outside a verified, authorized scope is refused before any request is sent." },
      { title: "Kill switch", body: "Any engagement can be stopped at once. Workers abort between phases and their credentials are revoked." },
      { title: "Single-execution credentials", body: "Workers receive short-lived, least-privilege credentials scoped to one execution." },
      { title: "Passive by default", body: "Intrusive checks stay disabled unless a recorded policy enables them." },
      { title: "Redacted evidence", body: "Secrets and personal data are masked before evidence reaches an AI model or a report." },
      { title: "Audit trail", body: "Every decision is recorded with who acted, on what, and when." },
    ],
    nonGoalsTitle: "NON-GOALS",
    nonGoalsLead: "Double AA does not, and will not:",
    nonGoals: ["exploit targets autonomously", "perform denial of service", "harvest credentials", "extract data in bulk"],
    authorTitle: "AUTHOR",
    author: "Designed, built, and operated by a solo founder.",
    authorCta: "Access is by invitation. Sign in with the account your administrator created.",
  },
  id: {
    nav: [
      { href: "#procedure", label: "prosedur" },
      { href: "#guarantees", label: "jaminan" },
      { href: "#author", label: "pembuat" },
    ],
    signIn: "masuk",
    docTitle: "Validasi Keamanan Terotorisasi",
    name: "NAMA",
    tagline: "pengujian keamanan terotorisasi yang menolak keluar dari cakupannya",
    title: "Pengujian keamanan yang menolak keluar dari cakupannya.",
    description:
      "Double AA memastikan Anda pemilik aset, mengikat pengujian pada otorisasi tertulis, dan hanya menjalankan pengecekan aman di dalam cakupan yang disetujui. Temuan disajikan sebagai proof-of-risk yang tersamarkan dan dapat ditinjau, lengkap dengan langkah perbaikan dan rencana uji ulang.",
    openConsole: "buka konsol",
    readProcedure: "baca prosedur",
    terminalHint: "Coba sendiri. Dalam simulasi ini hanya api.example-bank.test yang terotorisasi.",
    terminalLabel: "simulasi scope gate · tanpa permintaan jaringan",
    examples: "contoh",
    run: "jalankan",
    targetLabel: "Target pemindaian",
    procedureTitle: "PROSEDUR",
    procedureLead: "Setiap pengujian melewati empat langkah yang sama. Tidak ada yang dilewati dan tidak ada yang berjalan lebih awal.",
    steps: [
      { title: "Verifikasi kepemilikan", body: "Publikasikan record DNS TXT sekali pakai. Sebelum record itu terbaca, aset tidak dapat diuji." },
      { title: "Otorisasi tertulis", body: "Catat otorisasi yang ditandatangani: cakupan, masa berlaku, tingkat risiko, dan batas laju." },
      { title: "Validasi dalam cakupan", body: "Worker terisolasi menjalankan pengecekan pasif berdampak rendah dengan kredensial yang hanya berlaku untuk eksekusi ini. Kill switch dicek di antara setiap fase." },
      { title: "Buktikan dan perbaiki", body: "Bukti disamarkan, dianalisis dengan bantuan AI, dan dikonfirmasi peninjau manusia sebelum menjadi temuan." },
    ],
    guaranteesTitle: "JAMINAN",
    guaranteesLead: "Ditegakkan oleh platform. Tidak ada yang bergantung pada kedisiplinan operator.",
    guarantees: [
      { title: "Terkunci pada cakupan", body: "Target di luar cakupan yang terverifikasi dan terotorisasi ditolak sebelum satu permintaan pun dikirim." },
      { title: "Kill switch", body: "Engagement apa pun dapat dihentikan seketika. Worker berhenti di antara fase dan kredensialnya dicabut." },
      { title: "Kredensial satu eksekusi", body: "Worker menerima kredensial berumur pendek dengan hak minimum yang hanya berlaku untuk satu eksekusi." },
      { title: "Pasif secara default", body: "Pengujian intrusif tetap nonaktif kecuali diaktifkan oleh kebijakan yang tercatat." },
      { title: "Bukti tersamarkan", body: "Rahasia dan data pribadi disamarkan sebelum bukti mencapai model AI atau laporan." },
      { title: "Jejak audit", body: "Setiap keputusan tercatat: siapa yang bertindak, terhadap apa, dan kapan." },
    ],
    nonGoalsTitle: "BATASAN",
    nonGoalsLead: "Double AA tidak, dan tidak akan:",
    nonGoals: ["mengeksploitasi target secara otomatis", "melakukan denial of service", "mengambil kredensial", "mengekstrak data secara massal"],
    authorTitle: "PEMBUAT",
    author: "Dirancang, dibangun, dan dioperasikan oleh seorang founder tunggal.",
    authorCta: "Akses hanya melalui undangan. Masuk dengan akun yang dibuat administrator Anda.",
  },
} satisfies Record<Locale, unknown>;

const ARTIFACTS = [
  `; publish this record, then press "Verify" in the console
_doubleaa-verification.api.example-bank.test.  300  IN  TXT
  "doubleaa-verification=k3J9wQ…x2Lm"`,
  `authorization: AUTH-0142
valid: 2026-10-01 → 2026-11-01  (Asia/Jakarta)
maximum_risk_tier: tier_1_safe
production_testing_allowed: false
scope:
  - asset: api.example-bank.test
    maximum_requests_per_minute: 60
    maximum_concurrency: 5
authorization_document_sha256: 9f2c…e41a`,
  `09:41:02  gate    api.example-bank.test in scope (AUTH-0142)
09:41:02  worker  credential issued · single execution
09:41:05  check   http security headers ....... 1 finding
09:41:09  check   tls configuration ........... ok
09:41:09  gate    kill switch polled .......... clear
09:41:10  worker  credential revoked · run finished`,
  `finding   F-01 · moderate · confirmed by reviewer
title     Strict-Transport-Security header missing
target    api.example-bank.test
fix       add HSTS (max-age >= 31536000) at the gateway
retest    scheduled after fix
evidence  redacted · audit trail attached`,
];

const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7EE787]";
const PRIMARY_BUTTON = `inline-flex h-11 items-center justify-center gap-2 rounded-md bg-[#7EE787] px-5 font-mono text-sm font-bold text-[#0B0D10] transition-colors hover:bg-[#9BEFA2] ${FOCUS_RING}`;
const LINK_BUTTON = `inline-flex h-11 items-center justify-center gap-2 rounded-md border border-dashed border-white/20 px-5 font-mono text-sm text-[#C8CDD3] transition-colors hover:border-white/40 hover:text-white ${FOCUS_RING}`;

export function LandingPage() {
  const go = useApp((state) => state.go);
  const [locale] = useLocale();
  const t = COPY[locale];
  const openConsole = () => go("login");

  return (
    <div className="min-h-screen bg-[#0B0D10] font-sans text-[#C8CDD3] antialiased selection:bg-[#7EE787]/25">
      <header className="sticky top-0 z-30 border-b border-dashed border-white/10 bg-[#0B0D10]/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <a href="#top" className={`rounded-md ${FOCUS_RING}`} aria-label="Double AA">
            <BrandLogo />
          </a>
          <nav aria-label="Primary" className="hidden items-center gap-6 font-mono text-sm md:flex">
            {t.nav.map((item, index) => (
              <a key={item.href} href={item.href} className={`rounded text-[#8B949E] transition-colors hover:text-white ${FOCUS_RING}`}>
                <span className="text-[#7EE787]/70">§{index + 1}</span> {item.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2 sm:gap-3">
            <LocaleToggle />
            <button type="button" onClick={openConsole} className={`${LINK_BUTTON} h-9 whitespace-nowrap px-3`}>
              {t.signIn} <span aria-hidden className="hidden sm:inline">→</span>
            </button>
          </div>
        </div>
      </header>

      <main id="top" className="mx-auto max-w-5xl px-4 sm:px-6">
        {/* Man-page header line */}
        <div className="flex justify-between border-b border-dashed border-white/10 py-3 font-mono text-xs text-[#8B949E]" aria-hidden>
          <span>DOUBLE-AA(1)</span>
          <span className="hidden sm:inline">{t.docTitle}</span>
          <span>DOUBLE-AA(1)</span>
        </div>

        <section className="py-14 sm:py-20" aria-labelledby="hero-title">
          <p className="font-mono text-xs font-bold tracking-widest text-[#8B949E]">{t.name}</p>
          <p className="mt-2 font-mono text-sm text-[#C8CDD3]">
            <span className="text-white">double-aa</span> - {t.tagline}
          </p>
          <h1 id="hero-title" className="mt-8 max-w-3xl font-mono text-3xl font-bold leading-tight tracking-tight text-balance text-white sm:text-5xl">
            {t.title}
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-relaxed sm:text-lg">{t.description}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <button type="button" onClick={openConsole} className={PRIMARY_BUTTON}>
              $ {t.openConsole}
            </button>
            <a href="#procedure" className={LINK_BUTTON}>{t.readProcedure} ↓</a>
          </div>

          <ScopeTerminal copy={t} />
        </section>

        <DocSection id="procedure" index={1} title={t.procedureTitle} lead={t.procedureLead}>
          <ol className="space-y-12">
            {t.steps.map((step, index) => (
              <li key={step.title} className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-10">
                <div>
                  <h3 className="font-mono text-base font-bold text-white">
                    <span className="text-[#7EE787]">1.{index + 1}</span> {step.title}
                  </h3>
                  <p className="mt-2 text-[15px] leading-relaxed">{step.body}</p>
                </div>
                <pre className="overflow-x-auto rounded-md [font-variant-ligatures:none] border border-white/10 bg-[#0F1216] p-4 font-mono text-[13px] leading-relaxed text-[#C8CDD3]">
                  <code>{ARTIFACTS[index]}</code>
                </pre>
              </li>
            ))}
          </ol>
        </DocSection>

        <DocSection id="guarantees" index={2} title={t.guaranteesTitle} lead={t.guaranteesLead}>
          <dl className="grid gap-x-10 gap-y-6 sm:grid-cols-2">
            {t.guarantees.map((item, index) => (
              <div key={item.title} className="border-l-2 border-[#7EE787]/40 pl-4">
                <dt className="font-mono text-[15px] font-bold text-white">
                  <span className="text-[#7EE787]">G{index + 1}</span> {item.title}
                </dt>
                <dd className="mt-1.5 text-[15px] leading-relaxed">{item.body}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-12">
            <h3 className="font-mono text-xs font-bold tracking-widest text-[#8B949E]">{t.nonGoalsTitle}</h3>
            <p className="mt-2 text-[15px]">{t.nonGoalsLead}</p>
            <ul className="mt-3 space-y-1.5 font-mono text-sm">
              {t.nonGoals.map((item) => (
                <li key={item}>
                  <span className="text-[#FF7B72]" aria-hidden>✗ </span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </DocSection>

        <DocSection id="author" index={3} title={t.authorTitle}>
          <p className="text-base">{t.author}</p>
          <p className="mt-2 text-[15px] text-[#8B949E]">{t.authorCta}</p>
          <button type="button" onClick={openConsole} className={`${PRIMARY_BUTTON} mt-8`}>
            $ {t.openConsole}
          </button>
        </DocSection>

        <footer className="flex justify-between border-t border-dashed border-white/10 py-6 font-mono text-xs text-[#8B949E]">
          <span>double-aa 2026.10</span>
          <span className="hidden sm:inline">© 2026 Double AA</span>
          <span>DOUBLE-AA(1)</span>
        </footer>
      </main>
    </div>
  );
}

function DocSection({
  id,
  index,
  title,
  lead,
  children,
}: {
  id: string;
  index: number;
  title: string;
  lead?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-16 border-t border-dashed border-white/10 py-16">
      <h2 id={`${id}-title`} className="font-mono text-sm font-bold tracking-widest text-white">
        <span className="text-[#7EE787]">§{index}</span> {title}
      </h2>
      {lead && <p className="mt-3 max-w-2xl text-[15px] text-[#8B949E]">{lead}</p>}
      <div className="mt-10">{children}</div>
    </section>
  );
}

// Client-side simulation of the real scope gate. It never sends a request;
// the refusal text mirrors the backend's 403 detail for out-of-scope targets.
const AUTHORIZED_DEMO_TARGET = "api.example-bank.test";
const EXAMPLE_TARGETS = [AUTHORIZED_DEMO_TARGET, "admin.example-bank.test", "api.unknown-corp.test"];
const HOSTNAME = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/;

type TerminalLine = { tone: "info" | "ok" | "fail" | "dim"; text: string };

function simulateScan(rawTarget: string): TerminalLine[] {
  const target = rawTarget.trim().toLowerCase();
  if (!HOSTNAME.test(target)) {
    return [{ tone: "fail", text: `✗ invalid target: ${rawTarget.trim() || "(empty)"}` }];
  }
  const lines: TerminalLine[] = [{ tone: "info", text: `→ resolving scope for ${target}` }];
  if (target !== AUTHORIZED_DEMO_TARGET) {
    return [
      ...lines,
      { tone: "fail", text: "✗ refused (403): target is not a verified non-production asset under an active authorization for this organization" },
      { tone: "dim", text: "  no request was sent to the target." },
    ];
  }
  return [
    ...lines,
    { tone: "ok", text: "✓ asset ownership verified (dns txt)" },
    { tone: "ok", text: "✓ authorization AUTH-0142 active · 29 days left" },
    { tone: "ok", text: "✓ target inside approved scope · 60 req/min · kill switch armed" },
    { tone: "info", text: "● passive checks: http headers, tls configuration" },
    { tone: "ok", text: "✓ done · 2 findings (0 critical) · evidence redacted" },
  ];
}

const LINE_TONE: Record<TerminalLine["tone"], string> = {
  info: "text-[#79C0FF]",
  ok: "text-[#7EE787]",
  fail: "text-[#FF7B72]",
  dim: "text-[#8B949E]",
};

function ScopeTerminal({ copy }: { copy: (typeof COPY)[Locale] }) {
  const [target, setTarget] = React.useState("api.unknown-corp.test");
  const [history, setHistory] = React.useState<{ command: string; lines: TerminalLine[] }[]>([]);

  const run = (value: string) => {
    setTarget(value);
    // Keep the last few runs so the panel never grows without bound.
    setHistory((previous) => [...previous, { command: value.trim(), lines: simulateScan(value) }].slice(-3));
  };

  return (
    <div className="mt-14">
      <p className="mb-3 text-[15px] text-[#8B949E]">{copy.terminalHint}</p>
      <div className="overflow-hidden rounded-md border border-white/10 bg-[#0F1216]">
        <div className="flex min-w-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-2 font-mono text-xs text-[#8B949E]">
          <span className="shrink-0">aa · zsh</span>
          <span className="truncate">{copy.terminalLabel}</span>
        </div>
        <div role="log" aria-live="polite" className="space-y-3 px-4 pt-4 font-mono text-[13px] leading-relaxed">
          {history.map((entry, index) => (
            <div key={index}>
              <p className="text-white">
                <span className="text-[#7EE787]">$</span> aa scan {entry.command}
              </p>
              {entry.lines.map((line) => (
                <p key={line.text} className={`break-words ${LINE_TONE[line.tone]}`}>{line.text}</p>
              ))}
            </div>
          ))}
        </div>
        <form
          className="flex items-center gap-2 px-4 py-4 font-mono text-[13px]"
          onSubmit={(event) => {
            event.preventDefault();
            run(target);
          }}
        >
          <span className="text-[#7EE787]" aria-hidden>$</span>
          <span className="shrink-0 text-white" aria-hidden>aa scan</span>
          <label htmlFor="scan-target" className="sr-only">{copy.targetLabel}</label>
          <input
            id="scan-target"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            spellCheck={false}
            autoCapitalize="none"
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-white caret-[#7EE787] outline-none"
          />
          <button type="submit" className={`rounded border border-white/15 px-2.5 py-1 text-xs text-[#C8CDD3] hover:border-white/40 ${FOCUS_RING}`}>
            {copy.run} ⏎
          </button>
        </form>
        <div className="flex flex-wrap items-center gap-2 border-t border-dashed border-white/10 px-4 py-3 font-mono text-xs">
          <span className="text-[#8B949E]">{copy.examples}:</span>
          {EXAMPLE_TARGETS.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => run(example)}
              className={`rounded border border-white/10 px-2 py-1 text-[#C8CDD3] transition-colors hover:border-white/30 hover:text-white ${FOCUS_RING}`}
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
