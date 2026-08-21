// The sidebar's "Collectie-scan" card (web/design-input/HANDOFF.md,
// "Sidebar"). It is the app's ONE collection-rebuild control: the button and
// the failure reporting that TrackTable carried after the phase 7 review moved
// here with the delivered design, so the two tests that named that button
// moved with it (tests/components/TrackTable.test.tsx).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../src/api/client";
import { CollectionScanCard } from "../../src/components/CollectionScanCard";

vi.mock("../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

function mockTotal(total: number) {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: { total, items: [] },
    error: undefined,
  } as never);
}

beforeEach(() => {
  mockTotal(8412);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CollectionScanCard", () => {
  it("shows the collection's real total, not a placeholder", async () => {
    render(<CollectionScanCard onScanned={vi.fn()} />);

    expect(await screen.findByText(/8\.412 tracks in Rekordbox/)).toBeInTheDocument();
  });

  it("admits the scan moment is unknown rather than inventing one, when the index already holds tracks", async () => {
    // The index outlives this page, so it can hold tracks indexed before this
    // tab existed. Claiming "nog niet gescand" beside a real count would
    // contradict itself; the moment is genuinely unknown, because it is
    // recorded here and not in the backend.
    render(<CollectionScanCard onScanned={vi.fn()} />);

    expect(await screen.findByText(/Scanmoment onbekend/)).toBeInTheDocument();
    expect(screen.queryByText(/Laatste scan/)).not.toBeInTheDocument();
  });

  it("says a scan has not happened yet when the index is empty", async () => {
    vi.mocked(apiClient.GET).mockResolvedValue({
      data: { total: 0, items: [] },
      error: undefined,
    } as never);

    render(<CollectionScanCard onScanned={vi.fn()} />);

    expect(await screen.findByText(/Nog niet gescand/)).toBeInTheDocument();
  });

  it("rebuilds the index, records the scan moment and reports the new total", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { indexed_count: 9000, took_ms: 12 },
      error: undefined,
    } as never);
    const onScanned = vi.fn();

    render(<CollectionScanCard onScanned={onScanned} />);
    await screen.findByText(/8\.412 tracks in Rekordbox/);

    mockTotal(9000);
    fireEvent.click(screen.getByRole("button", { name: "Opnieuw scannen" }));

    await waitFor(() => {
      expect(screen.getByText(/9\.000 tracks in Rekordbox/)).toBeInTheDocument();
    });
    expect(vi.mocked(apiClient.POST)).toHaveBeenCalledWith("/api/collection/reindex", {});
    expect(screen.getByText(/Laatste scan \d{2}:\d{2}/)).toBeInTheDocument();
    // The Collection view's table reloads on this.
    expect(onScanned).toHaveBeenCalled();
  });

  it("reports a failed rebuild instead of failing silently", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "rekordbox_not_found", message: "geen Rekordbox" },
    } as never);
    const onScanned = vi.fn();

    render(<CollectionScanCard onScanned={onScanned} />);
    fireEvent.click(screen.getByRole("button", { name: "Opnieuw scannen" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Rekordbox is niet gevonden. Start Rekordbox en probeer het opnieuw.",
      );
    });
    expect(onScanned).not.toHaveBeenCalled();
  });

  it("reports a network failure with its own Dutch message", async () => {
    vi.mocked(apiClient.POST).mockRejectedValue(new Error("network down"));

    render(<CollectionScanCard onScanned={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Opnieuw scannen" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Opnieuw scannen is mislukt. Probeer het opnieuw.",
      );
    });
  });
});
