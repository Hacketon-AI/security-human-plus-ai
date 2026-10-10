"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  changePassword,
  getStoredUser,
  listUsers,
  registerUser,
  updateUser,
  type UserResponse,
} from "@/lib/securescope/authApi";
import { useApp } from "@/lib/securescope/store";
import {
  Database,
  KeyRound,
  Lock,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Pill } from "../shared/badges";
import { AlertBanner, CyberButton, DispatchBackendPill, KeyValue } from "../shared/ui";
import { TopNavCommandBar, PageHeader } from "../shell/TopNav";

const SECTIONS = [
  { key: "account", label: "Account" },
  { key: "users", label: "Users" },
  { key: "system", label: "System" },
  { key: "secrets", label: "Secrets policy" },
] as const;

export function SettingsPage() {
  const [section, setSection] = React.useState<(typeof SECTIONS)[number]["key"]>("account");
  const [currentUser] = React.useState(getStoredUser);
  const isAdmin = currentUser?.role === "admin";
  const sections = SECTIONS.filter((s) => s.key !== "users" || isAdmin);

  return (
    <>
      <TopNavCommandBar />
      <div className="pt-19 min-h-screen">
        <PageHeader
          breadcrumbs={[{ label: "Settings" }]}
          title="System Configuration"
          description="Non-sensitive operational configuration. Secrets, raw worker tokens, broker credentials, and database URLs are never exposed."
          meta={
            <>
              <Pill tone="green"><ShieldCheck className="w-2.5 h-2.5" /> Policy enforced</Pill>
            </>
          }
        />

        <div className="px-4 lg:px-6 py-5 grid lg:grid-cols-[200px_1fr] gap-5">
          {/* Section nav (contextual, not a global sidebar) */}
          <nav className="ss-panel-flat p-2 h-max lg:sticky lg:top-[68px]">
            <ul className="space-y-0.5">
              {sections.map((s) => (
                <li key={s.key}>
                  <button
                    onClick={() => setSection(s.key)}
                    className={cn(
                      "w-full text-left px-2.5 py-1.5 text-[11px] uppercase tracking-wider rounded-sm transition-colors",
                      section === s.key
                        ? "text-cyan-200 bg-cyan-500/10"
                        : "text-slate-400 hover:text-slate-200 hover:bg-(--ss-surface-3)/40"
                    )}
                  >
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          <div className="space-y-4">
            {section === "account" && <ChangePasswordPanel />}
            {section === "users" && isAdmin && <UsersPanel currentUserId={currentUser?.id} />}

            {section === "system" && <SystemPanel />}

            {section === "secrets" && (
              <div className="ss-panel p-5">
                <div className="flex items-center gap-2 mb-1">
                  <Lock className="w-4 h-4 text-cyan-400" />
                  <div className="ss-eyebrow text-cyan-300">Secrets policy</div>
                </div>
                <h2 className="text-base font-semibold text-slate-100 mb-3">Secrets exposure policy</h2>
                <p className="text-xs text-slate-400 mb-4">
                  Double AA enforces a strict no-exposure policy for sensitive material. The following are never stored client-side, never logged, and never displayed in the UI.
                </p>
                <div className="space-y-2">
                  {[
                    "Raw worker tokens / credentials",
                    "Broker URLs and broker credentials",
                    "Database URLs",
                    "Raw HTTP response bodies",
                    "Cookies (request and Set-Cookie)",
                    "Authorization headers",
                    "Sensitive request payloads",
                    "Private signing keys",
                  ].map((s) => (
                    <div key={s} className="flex items-center justify-between p-2.5 border border-(--ss-hairline) rounded-sm">
                      <span className="text-[11px] text-slate-300">{s}</span>
                      <Pill tone="red"><Lock className="w-2.5 h-2.5" /> Never exposed</Pill>
                    </div>
                  ))}
                </div>
                <AlertBanner tone="success" title="No reveal, no copy, no export" className="mt-3">
                  There is no UI affordance to reveal, copy, or export any of the above. Failures are explained without leaking sensitive internals.
                </AlertBanner>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

const MIN_PASSWORD_LENGTH = 8; // mirrors ChangePasswordRequest.new_password in the API
const INPUT_CLASS =
  "w-full bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm text-sm p-2 text-slate-200 outline-none focus:border-cyan-500/50";

export function ChangePasswordPanel() {
  const logout = useApp((state) => state.logout);
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [changed, setChanged] = React.useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (next.length < MIN_PASSWORD_LENGTH) {
      setError(`New password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (next === current) {
      setError("New password must differ from the current password.");
      return;
    }
    setSaving(true);
    try {
      await changePassword(current, next);
      setChanged(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Password change failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="ss-panel p-5">
      <div className="flex items-center gap-2 mb-1">
        <KeyRound className="w-4 h-4 text-cyan-400" />
        <div className="ss-eyebrow text-cyan-300">Account</div>
      </div>
      <h2 className="text-base font-semibold text-slate-100 mb-3">Change password</h2>
      {changed ? (
        <AlertBanner tone="success" title="Password changed">
          All sessions for this account were signed out.{" "}
          <CyberButton size="sm" variant="primary" onClick={logout} className="ml-2">
            Sign in again
          </CyberButton>
        </AlertBanner>
      ) : (
        <form onSubmit={submit} className="space-y-3 max-w-sm">
          {[
            { id: "current-password", label: "Current password", value: current, set: setCurrent, autoComplete: "current-password" },
            { id: "new-password", label: "New password", value: next, set: setNext, autoComplete: "new-password" },
            { id: "confirm-password", label: "Confirm new password", value: confirm, set: setConfirm, autoComplete: "new-password" },
          ].map((field) => (
            <div key={field.id}>
              <label htmlFor={field.id} className="block text-[11px] uppercase tracking-wider text-slate-400 mb-1">
                {field.label}
              </label>
              <input
                id={field.id}
                type="password"
                value={field.value}
                onChange={(event) => field.set(event.target.value)}
                autoComplete={field.autoComplete}
                required
                className={INPUT_CLASS}
              />
            </div>
          ))}
          {error && (
            <div role="alert" className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-sm p-2">
              {error}
            </div>
          )}
          <CyberButton type="submit" variant="primary" disabled={saving}>
            {saving ? "Saving..." : "Change password"}
          </CyberButton>
        </form>
      )}
    </div>
  );
}

const ROLES = ["admin", "operator", "viewer"] as const;
const EMPTY_NEW_USER = { email: "", username: "", full_name: "", role: "operator", password: "" };

export function UsersPanel({ currentUserId }: { currentUserId: string | undefined }) {
  const [users, setUsers] = React.useState<UserResponse[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [newUser, setNewUser] = React.useState(EMPTY_NEW_USER);
  const [saving, setSaving] = React.useState(false);

  const reload = React.useCallback(async () => {
    try {
      setUsers(await listUsers());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load users");
    }
  }, []);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const change = async (userId: string, changes: { role?: string; is_active?: boolean }) => {
    setError(null);
    try {
      const updated = await updateUser(userId, changes);
      setUsers((list) => list?.map((u) => (u.id === updated.id ? updated : u)) ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Update failed");
    }
  };

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (newUser.password.length < MIN_PASSWORD_LENGTH) {
      setError(`Initial password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setSaving(true);
    try {
      await registerUser({ ...newUser, full_name: newUser.full_name || undefined });
      setNewUser(EMPTY_NEW_USER);
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create user");
    } finally {
      setSaving(false);
    }
  };

  const field = (key: keyof typeof EMPTY_NEW_USER) => ({
    value: newUser[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setNewUser((current) => ({ ...current, [key]: event.target.value })),
  });

  return (
    <div className="ss-panel p-5 space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Users className="w-4 h-4 text-cyan-400" />
          <div className="ss-eyebrow text-cyan-300">Users</div>
        </div>
        <h2 className="text-base font-semibold text-slate-100">Organization users</h2>
      </div>

      {error && (
        <div role="alert" className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-sm p-2">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-left uppercase tracking-wider text-slate-500 border-b border-(--ss-hairline)">
              <th className="py-1.5 pr-3 font-medium">User</th>
              <th className="py-1.5 pr-3 font-medium">Role</th>
              <th className="py-1.5 pr-3 font-medium">Status</th>
              <th className="py-1.5 font-medium">Last login</th>
            </tr>
          </thead>
          <tbody>
            {users === null && (
              <tr><td colSpan={4} className="py-3 text-slate-500">Loading users...</td></tr>
            )}
            {users?.map((u) => {
              const isSelf = u.id === currentUserId;
              return (
                <tr key={u.id} className="border-b border-(--ss-hairline)">
                  <td className="py-2 pr-3">
                    <div className="text-slate-200">{u.full_name || u.username}{isSelf && " (you)"}</div>
                    <div className="text-slate-500">{u.email}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <select
                      aria-label={`Role for ${u.email}`}
                      value={u.role}
                      disabled={isSelf}
                      onChange={(event) => void change(u.id, { role: event.target.value })}
                      className="bg-(--ss-surface-1) border border-(--ss-hairline) rounded-sm p-1 text-slate-200 disabled:opacity-50"
                    >
                      {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
                    </select>
                  </td>
                  <td className="py-2 pr-3">
                    <CyberButton
                      size="sm"
                      variant={u.is_active ? "ghost" : "amber"}
                      disabled={isSelf}
                      onClick={() => void change(u.id, { is_active: !u.is_active })}
                    >
                      {u.is_active ? "Active · disable" : "Disabled · enable"}
                    </CyberButton>
                  </td>
                  <td className="py-2 text-slate-400 font-mono">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <form onSubmit={create} className="grid sm:grid-cols-2 gap-3 pt-2 border-t border-(--ss-hairline)">
        <div className="sm:col-span-2 text-[11px] uppercase tracking-wider text-slate-400">Add user</div>
        <input aria-label="Email" type="email" placeholder="Email" required autoComplete="off" className={INPUT_CLASS} {...field("email")} />
        <input aria-label="Username" placeholder="Username" required minLength={3} autoComplete="off" className={INPUT_CLASS} {...field("username")} />
        <input aria-label="Full name" placeholder="Full name (optional)" className={INPUT_CLASS} {...field("full_name")} />
        <select aria-label="Role" className={INPUT_CLASS} {...field("role")}>
          {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
        </select>
        <input aria-label="Initial password" type="password" placeholder="Initial password" required autoComplete="new-password" className={INPUT_CLASS} {...field("password")} />
        <CyberButton type="submit" variant="primary" disabled={saving}>
          {saving ? "Adding..." : "Add user"}
        </CyberButton>
      </form>
    </div>
  );
}

const ROUTER_MODES: Record<string, string> = {
  deterministic: "deterministic rules only (no AI model calls)",
  hybrid: "hybrid: Claude preferred, then Fireworks, then rules",
  local_only: "local model, then rules",
  fireworks_only: "Fireworks, then rules",
};

export function SystemPanel() {
  const status = useApp((state) => state.systemStatus);

  return (
    <div className="ss-panel p-5">
      <div className="flex items-center gap-2 mb-1">
        <Server className="w-4 h-4 text-cyan-400" />
        <div className="ss-eyebrow text-cyan-300">System</div>
      </div>
      <h2 className="text-base font-semibold text-slate-100 mb-1">Runtime configuration</h2>
      <p className="text-sm text-slate-400 mb-4">Reported by the running control plane. Names and on/off states only; URLs and credentials are never exposed.</p>
      {status === null ? (
        <AlertBanner tone="warning" title="Status unavailable">
          The control plane did not report its configuration. Reload the page or check the API.
        </AlertBanner>
      ) : (
        <div className="grid md:grid-cols-2 gap-x-6 gap-y-0">
          <KeyValue k="Environment" v={status.environment} mono />
          <KeyValue k="Dispatch backend" v={<DispatchBackendPill backend={status.dispatcher_backend} />} />
          <KeyValue k="AI router mode" v={ROUTER_MODES[status.ai_router_mode] ?? status.ai_router_mode} />
          <KeyValue k="Claude (Anthropic API)" v={status.claude_configured ? "configured" : "not configured"} />
          <KeyValue k="Fireworks" v={status.fireworks_configured ? "configured" : "not configured"} />
        </div>
      )}
    </div>
  );
}
