"use client";

import * as React from "react";
import { AlertCircle, ArrowLeft, Eye, EyeOff, Loader2, OctagonX, ShieldCheck, Target } from "lucide-react";
import { loginUser, saveToken, saveUser } from "@/lib/securescope/authApi";
import { useLocale, type Locale } from "@/lib/securescope/locale";
import { useApp } from "@/lib/securescope/store";
import { LocaleToggle } from "../shared/ui";

const COPY = {
  en: {
    back: "Back to home",
    title: "Sign in to SecureScope",
    subtitle: "Use the account your administrator created for you.",
    email: "Email",
    password: "Password",
    showPassword: "Show password",
    hidePassword: "Hide password",
    submit: "Sign in",
    submitting: "Signing in...",
    required: "Email and password are required.",
    noOrganization: "This account is not assigned to an organization. Contact an administrator.",
    failed: "Sign-in failed",
    notice: "Access is restricted to authorized personnel and every action is audited.",
    asideTitle: "Authorized security validation, under control.",
    aside: ["Every target is checked against an authorized scope", "Kill switch available on every engagement", "Full audit trail of every decision"],
  },
  id: {
    back: "Kembali ke beranda",
    title: "Masuk ke SecureScope",
    subtitle: "Gunakan akun yang dibuatkan oleh administrator Anda.",
    email: "Email",
    password: "Kata sandi",
    showPassword: "Tampilkan kata sandi",
    hidePassword: "Sembunyikan kata sandi",
    submit: "Masuk",
    submitting: "Sedang masuk...",
    required: "Email dan kata sandi wajib diisi.",
    noOrganization: "Akun ini belum terhubung ke organisasi. Hubungi administrator.",
    failed: "Gagal masuk",
    notice: "Akses terbatas untuk personel berwenang dan setiap tindakan diaudit.",
    asideTitle: "Validasi keamanan terotorisasi, tetap terkendali.",
    aside: ["Setiap target dicek terhadap cakupan yang diizinkan", "Kill switch tersedia di setiap engagement", "Jejak audit lengkap untuk setiap keputusan"],
  },
} satisfies Record<Locale, unknown>;

const ASIDE_ICONS = [Target, OctagonX, ShieldCheck];
const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400";
const INPUT =
  "h-11 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3.5 text-[15px] text-white placeholder:text-slate-600 transition-colors hover:border-white/20 focus:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-400/25";

export function LoginPage() {
  const login = useApp((state) => state.login);
  const go = useApp((state) => state.go);
  const [locale] = useLocale();
  const t = COPY[locale];
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!email.trim() || !password) {
      setError(t.required);
      return;
    }
    setSubmitting(true);
    try {
      const response = await loginUser({ email: email.trim(), password });
      if (!response.user.organization_id) {
        setError(t.noOrganization);
        return;
      }
      saveToken(response.access_token);
      saveUser(response.user);
      login(response.user.organization_id);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : t.failed);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-[#070A12] text-slate-300 antialiased lg:grid-cols-2">
      <aside className="relative hidden overflow-hidden border-r border-white/5 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_50%_at_20%_0%,rgba(34,211,238,0.12),transparent)]" />
        <div className="relative flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-cyan-400/10 ring-1 ring-cyan-400/30">
            <ShieldCheck className="size-4.5 text-cyan-300" aria-hidden />
          </span>
          <span className="text-base font-semibold tracking-tight text-white">SecureScope</span>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold tracking-tight text-balance text-white">{t.asideTitle}</h2>
          <ul className="mt-8 space-y-4">
            {t.aside.map((item, index) => {
              const Icon = ASIDE_ICONS[index];
              return (
                <li key={item} className="flex items-center gap-3 text-sm text-slate-300">
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-emerald-400/10 ring-1 ring-emerald-400/25">
                    <Icon className="size-4 text-emerald-300" aria-hidden />
                  </span>
                  {item}
                </li>
              );
            })}
          </ul>
        </div>
        <p className="relative text-sm text-slate-500">© 2026 SecureScope</p>
      </aside>

      <main className="flex flex-col px-4 py-6 sm:px-8">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => go("landing")}
            className={`inline-flex h-9 items-center gap-1.5 rounded-lg px-2 text-sm text-slate-400 transition-colors hover:text-white ${FOCUS_RING}`}
          >
            <ArrowLeft className="size-4" aria-hidden />
            {t.back}
          </button>
          <LocaleToggle />
        </div>

        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12">
          <h1 className="text-2xl font-semibold tracking-tight text-white">{t.title}</h1>
          <p className="mt-2 text-sm text-slate-400">{t.subtitle}</p>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <div>
              <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium text-slate-200">{t.email}</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                inputMode="email"
                placeholder="name@company.com"
                required
                aria-invalid={error !== null && !email.trim()}
                className={INPUT}
              />
            </div>
            <div>
              <label htmlFor="login-password" className="mb-1.5 block text-sm font-medium text-slate-200">{t.password}</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  aria-invalid={error !== null && !password}
                  className={`${INPUT} pr-11`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((shown) => !shown)}
                  aria-label={showPassword ? t.hidePassword : t.showPassword}
                  aria-pressed={showPassword}
                  className={`absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-slate-400 transition-colors hover:text-white ${FOCUS_RING}`}
                >
                  {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                </button>
              </div>
            </div>

            {error && (
              <p role="alert" className="flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-400/[0.06] p-3 text-sm text-red-200">
                <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className={`inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-cyan-400 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60 ${FOCUS_RING}`}
            >
              {submitting && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />}
              {submitting ? t.submitting : t.submit}
            </button>
          </form>

          <p className="mt-8 text-xs leading-relaxed text-slate-500">{t.notice}</p>
        </div>
      </main>
    </div>
  );
}
