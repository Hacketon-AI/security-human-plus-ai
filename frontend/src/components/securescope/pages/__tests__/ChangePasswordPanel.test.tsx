import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChangePasswordPanel } from "../SettingsPage";
import { changePassword } from "@/lib/securescope/authApi";

const logout = vi.fn();
vi.mock("@/lib/securescope/store", () => ({
  useApp: (selector: (s: any) => any) => selector({ logout }),
}));
vi.mock("@/lib/securescope/authApi", () => ({ changePassword: vi.fn() }));

async function fill(current: string, next: string, confirm: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Current password"), current);
  await user.type(screen.getByLabelText("New password"), next);
  await user.type(screen.getByLabelText("Confirm new password"), confirm);
  await user.click(screen.getByRole("button", { name: "Change password" }));
  return user;
}

describe("ChangePasswordPanel", () => {
  beforeEach(() => {
    vi.mocked(changePassword).mockReset();
  });

  it("rejects a mismatched confirmation without calling the API", async () => {
    render(<ChangePasswordPanel />);
    await fill("old-password", "new-password-1", "new-password-2");
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("changes the password and offers to sign in again", async () => {
    vi.mocked(changePassword).mockResolvedValue();
    render(<ChangePasswordPanel />);
    const user = await fill("old-password", "new-password-1", "new-password-1");
    expect(changePassword).toHaveBeenCalledWith("old-password", "new-password-1");
    await user.click(await screen.findByRole("button", { name: "Sign in again" }));
    expect(logout).toHaveBeenCalled();
  });

  it("shows the API error, e.g. a wrong current password", async () => {
    vi.mocked(changePassword).mockImplementation(async () => {
      throw new Error("Current password is incorrect");
    });
    render(<ChangePasswordPanel />);
    await fill("wrong-password", "new-password-1", "new-password-1");
    expect(await screen.findByRole("alert")).toHaveTextContent("Current password is incorrect");
  });
});
