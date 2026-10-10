import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LandingPage } from "../LandingPage";

const go = vi.fn();
vi.mock("@/lib/securescope/store", () => ({
  useApp: (selector: (s: any) => any) => selector({ go }),
}));

describe("LandingPage", () => {
  it("switches copy and the document language between English and Indonesian", async () => {
    const user = userEvent.setup();
    render(<LandingPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("refuses to leave its scope");

    await user.click(screen.getByRole("button", { name: "Bahasa Indonesia" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("menolak keluar dari cakupannya");
    expect(document.documentElement.lang).toBe("id");

    await user.click(screen.getByRole("button", { name: "English" }));
    expect(document.documentElement.lang).toBe("en");
  });

  it("opens the login page from the hero", async () => {
    render(<LandingPage />);
    await userEvent.setup().click(screen.getAllByRole("button", { name: /open console/i })[0]);
    expect(go).toHaveBeenCalledWith("login");
  });

  it("simulates the scope gate: authorized target passes, others are refused", async () => {
    const user = userEvent.setup();
    render(<LandingPage />);
    const log = screen.getByRole("log");

    await user.click(screen.getByRole("button", { name: "admin.example-bank.test" }));
    expect(within(log).getByText(/refused \(403\)/)).toBeInTheDocument();
    expect(within(log).getByText(/no request was sent/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "api.example-bank.test" }));
    expect(within(log).getByText(/done · 2 findings/)).toBeInTheDocument();

    const input = screen.getByLabelText("Scan target");
    await user.clear(input);
    await user.type(input, "not a host{Enter}");
    expect(within(log).getByText(/invalid target/)).toBeInTheDocument();
  });
});
