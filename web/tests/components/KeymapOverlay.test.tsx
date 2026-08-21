// T100: an on-screen, always-visible key map (WCAG discoverability
// criterion for US2 -- documented externally is not enough).
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KeymapOverlay } from "../../src/components/KeymapOverlay";

describe("KeymapOverlay", () => {
  it("shows every documented review key and its action as visible text", () => {
    render(<KeymapOverlay />);

    const overlay = screen.getByRole("note", { name: "Toetsenbordbediening" });
    expect(overlay).toBeVisible();
    expect(screen.getByText("↑ / ↓")).toBeInTheDocument();
    expect(screen.getByText("Wissel van nummer")).toBeInTheDocument();
    expect(screen.getByText("← / →")).toBeInTheDocument();
    expect(screen.getByText("Wissel van kandidaat")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("Accepteer kandidaat")).toBeInTheDocument();
    expect(screen.getByText("R")).toBeInTheDocument();
    expect(screen.getByText("Wijs af")).toBeInTheDocument();
    expect(screen.getByText("Spatie")).toBeInTheDocument();
    expect(screen.getByText("Beluister")).toBeInTheDocument();
  });
});
