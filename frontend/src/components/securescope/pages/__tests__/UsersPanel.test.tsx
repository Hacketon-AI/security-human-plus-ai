import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UsersPanel } from "../SettingsPage";
import { listUsers, registerUser, updateUser, type UserResponse } from "@/lib/securescope/authApi";

vi.mock("@/lib/securescope/store", () => ({
  useApp: (selector: (s: any) => any) => selector({ logout: vi.fn() }),
}));
vi.mock("@/lib/securescope/authApi", () => ({
  changePassword: vi.fn(),
  getStoredUser: vi.fn(),
  listUsers: vi.fn(),
  registerUser: vi.fn(),
  updateUser: vi.fn(),
}));

const user = (id: string, overrides: Partial<UserResponse> = {}): UserResponse => ({
  id,
  email: `${id}@example.com`,
  username: id,
  full_name: null,
  role: "operator",
  is_active: true,
  organization_id: "org",
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

describe("UsersPanel", () => {
  beforeEach(() => {
    vi.mocked(listUsers).mockReset();
    vi.mocked(updateUser).mockReset();
    vi.mocked(registerUser).mockReset();
    vi.mocked(listUsers).mockResolvedValue([user("me", { role: "admin" }), user("ops")]);
  });

  it("locks the current admin's own role and status", async () => {
    render(<UsersPanel currentUserId="me" />);
    expect(await screen.findByLabelText("Role for me@example.com")).toBeDisabled();
    expect(screen.getByLabelText("Role for ops@example.com")).toBeEnabled();
  });

  it("disables another user", async () => {
    vi.mocked(updateUser).mockResolvedValue(user("ops", { is_active: false }));
    render(<UsersPanel currentUserId="me" />);
    const buttons = await screen.findAllByRole("button", { name: "Active · disable" });
    await userEvent.setup().click(buttons[1]);
    expect(updateUser).toHaveBeenCalledWith("ops", { is_active: false });
    expect(await screen.findByRole("button", { name: "Disabled · enable" })).toBeInTheDocument();
  });

  it("adds a user and reloads the list", async () => {
    vi.mocked(registerUser).mockResolvedValue(user("new"));
    render(<UsersPanel currentUserId="me" />);
    const ui = userEvent.setup();
    await ui.type(screen.getByLabelText("Email"), "new@example.com");
    await ui.type(screen.getByLabelText("Username"), "new");
    await ui.type(screen.getByLabelText("Initial password"), "long-enough-pw");
    await ui.click(screen.getByRole("button", { name: "Add user" }));
    expect(registerUser).toHaveBeenCalledWith({
      email: "new@example.com",
      username: "new",
      full_name: undefined,
      role: "operator",
      password: "long-enough-pw",
    });
    expect(listUsers).toHaveBeenCalledTimes(2);
  });
});
