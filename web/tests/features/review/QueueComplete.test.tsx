// T041: completion state shown once the Review Queue empties (spec.md US2
// acceptance scenario 6), with the session's updated totals.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueueComplete } from "../../../src/features/review/QueueComplete";

describe("QueueComplete", () => {
  it("announces completion and shows the updated session totals as text", () => {
    render(
      <QueueComplete totals={{ matched: 8, review: 0, missing: 2, rejected: 1, unmatchable: 0 }} />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Review afgerond");
    expect(screen.getByText("Gematcht: 8")).toBeInTheDocument();
    expect(screen.getByText("Controleren: 0")).toBeInTheDocument();
    expect(screen.getByText("Ontbreekt: 2")).toBeInTheDocument();
    expect(screen.getByText("Afgewezen: 1")).toBeInTheDocument();
    expect(screen.getByText("Niet matchbaar: 0")).toBeInTheDocument();
  });
});
