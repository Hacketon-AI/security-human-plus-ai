"use client";

import * as React from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { loginUser, saveToken, saveUser } from "@/lib/securescope/authApi";
import { useLocale, type Locale } from "@/lib/securescope/locale";
import { useApp } from "@/lib/securescope/store";
import { BrandLogo, LocaleToggle } from "../shared/ui";

const COPY = {
  en: {
    back: "Back to home",
    title: "double-aa login",
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
  },
  id: {
    back: "Kembali ke beranda",
    title: "double-aa login",
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
  },
} satisfies Record<Locale, unknown>;

const FOCUS_RING = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7EE787]";
const INPUT =
  "h-11 w-full rounded-md border border-white/10 bg-[#0F1216] px-3.5 font-mono text-sm text-white placeholder:text-[#5A626C] caret-[#7EE787] transition-colors hover:border-white/20 focus:border-[#7EE787] focus:outline-none focus:ring-2 focus:ring-[#7EE787]/20";

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
    <div className="flex min-h-screen flex-col bg-[#0B0D10] font-sans text-[#C8CDD3] antialiased">
      <header className="border-b border-dashed border-white/10">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <button type="button" onClick={() => go("landing")} className={`rounded-md ${FOCUS_RING}`} aria-label={t.back}>
            <BrandLogo />
          </button>
          <LocaleToggle />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="rounded-md border border-white/10 bg-[#0F1216]">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-2.5 font-mono text-xs text-[#8B949E]">
              <span>{t.title}</span>
              <span aria-hidden>tty1</span>
            </div>
            <div className="p-5 sm:p-6">
              <h1 className="font-mono text-lg font-bold text-white">
                <span className="text-[#7EE787]">$</span> {t.title}
              </h1>
              <p className="mt-2 text-sm text-[#8B949E]">{t.subtitle}</p>

              <form onSubmit={submit} className="mt-6 space-y-5" noValidate>
                <div>
                  <label htmlFor="login-email" className="mb-1.5 block font-mono text-xs font-bold tracking-wide text-[#C8CDD3]">{t.email.toLowerCase()}:</label>
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
                  <label htmlFor="login-password" className="mb-1.5 block font-mono text-xs font-bold tracking-wide text-[#C8CDD3]">{t.password.toLowerCase()}:</label>
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
                      className={`absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-md text-[#8B949E] transition-colors hover:text-white ${FOCUS_RING}`}
                    >
                      {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                    </button>
                  </div>
                </div>

                {error && (
                  <p role="alert" className="font-mono text-[13px] leading-relaxed text-[#FF7B72]">
                    ✗ {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={submitting}
                  className={`inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[#7EE787] font-mono text-sm font-bold text-[#0B0D10] transition-colors hover:bg-[#9BEFA2] disabled:cursor-not-allowed disabled:opacity-60 ${FOCUS_RING}`}
                >
                  {submitting && <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />}
                  {submitting ? t.submitting : t.submit}
                </button>
              </form>
            </div>
          </div>
          <p className="mt-4 font-mono text-xs leading-relaxed text-[#8B949E]">{t.notice}</p>
          <button
            type="button"
            onClick={() => go("landing")}
            className={`mt-6 rounded font-mono text-sm text-[#8B949E] transition-colors hover:text-white ${FOCUS_RING}`}
          >
            ← {t.back}
          </button>
        </div>
      </main>
    </div>
  );
}
