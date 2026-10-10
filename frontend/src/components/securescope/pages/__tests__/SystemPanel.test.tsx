import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SystemPanel } from "../SettingsPage";

let systemStatus: unknown = null;
vi.mock("@/lib/securescope/store", () => ({
  useApp: (selector: (s: any) => any) => selector({ systemStatus, logout: vi.fn() }),
}));
vi.mock("@/lib/securescope/authApi", () => ({
  changePassword: vi.fn(),
  getStoredUser: vi.fn(),
  listUsers: vi.fn(),
  registerUser: vi.fn(),
  updateUser: vi.fn(),
}));

describe("SystemPanel", () => {
  it("shows the configuration the control plane reports", () => {
    systemStatus = {
      environment: "development",
      dispatcher_backend: "in_memory",
      ai_router_mode: "hybrid",
      claude_configured: true,
      fireworks_configured: false,
    };
    render(<SystemPanel />);
    expect(screen.getByText("development")).toBeInTheDocument();
    expect(screen.getByText("dispatch: in-process (dev)")).toBeInTheDocument();
    expect(screen.getByText(/Claude preferred/)).toBeInTheDocument();
    expect(screen.getByText("configured")).toBeInTheDocument();
    expect(screen.queryByText(/online/i)).not.toBeInTheDocument();
  });

  it("says so when the status is unavailable instead of inventing values", () => {
    systemStatus = null;
    render(<SystemPanel />);
    expect(screen.getByText("Status unavailable")).toBeInTheDocument();
  });
});
