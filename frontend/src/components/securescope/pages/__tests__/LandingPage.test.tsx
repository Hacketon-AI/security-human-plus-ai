import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("never leaves its scope");

    await user.click(screen.getByRole("button", { name: "Bahasa Indonesia" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("tidak pernah keluar dari cakupannya");
    expect(document.documentElement.lang).toBe("id");

    await user.click(screen.getByRole("button", { name: "English" }));
    expect(document.documentElement.lang).toBe("en");
  });

  it("opens the login page from the hero", async () => {
    render(<LandingPage />);
    await userEvent.setup().click(screen.getAllByRole("button", { name: /open console/i })[0]);
    expect(go).toHaveBeenCalledWith("login");
  });
});
