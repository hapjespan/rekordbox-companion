// The delivered design's filter row (HANDOFF.md, "1. Match-overzicht" ->
// Filter row), which its own notes list under "Intended but not built": four
// chips and a sort control.
//
// WCAG 2.2 AA is claimed by this project, so the chips are toggle buttons that
// expose their state through `aria-pressed` rather than through the white fill
// alone, and the sort control is a real labelled form control rather than the
// design's static "Sorteer op zekerheid" caption. That the chips and the sort
// actually filter and reorder the rendered groups is pinned one level up, in
// tests/views/MatchOverviewView.test.tsx.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MatchFilters } from "../../../src/features/spotify-sync/MatchFilters";

function renderFilters(overrides: Partial<Parameters<typeof MatchFilters>[0]> = {}) {
  const onFilterChange = vi.fn();
  const onSortChange = vi.fn();
  render(
    <MatchFilters
      filter="all"
      onFilterChange={onFilterChange}
      sort="score"
      onSortChange={onSortChange}
      {...overrides}
    />,
  );
  return { onFilterChange, onSortChange };
}

describe("MatchFilters", () => {
  it("renders the design's four chips in order", () => {
    renderFilters();

    const labels = screen.getAllByRole("button").map((chip) => chip.textContent);
    expect(labels).toEqual(["Alles", "Ontbreekt", "Twijfel", "In collectie"]);
  });

  it("exposes the selected chip through aria-pressed, not colour alone", () => {
    renderFilters({ filter: "missing" });

    expect(screen.getByRole("button", { name: "Ontbreekt" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Alles" })).toHaveAttribute("aria-pressed", "false");
  });

  it("reports the chip the DJ picked", () => {
    const { onFilterChange } = renderFilters();

    fireEvent.click(screen.getByRole("button", { name: "In collectie" }));

    expect(onFilterChange).toHaveBeenCalledWith("collection");
  });

  it("offers the sort as a labelled control, defaulting to the design's zekerheid", () => {
    const { onSortChange } = renderFilters();

    const select = screen.getByLabelText("Sorteer op");
    expect(select).toHaveValue("score");
    expect(screen.getByRole("option", { name: "Zekerheid" })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "title" } });
    expect(onSortChange).toHaveBeenCalledWith("title");
  });
});
