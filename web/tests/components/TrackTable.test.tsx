// T064 (FR-024, WCAG): searchable, sortable table, keyboard navigation.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../src/api/client";
import { TrackTable } from "../../src/components/TrackTable";

vi.mock("../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

function mockCollection(total: number, items: unknown[]) {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: { total, items },
    error: undefined,
  } as never);
}

const TRACKS = [
  {
    rb_content_id: "rb1",
    artist: "Adele",
    title: "Rolling in the Deep",
    duration_ms: 228_000,
    bpm: 105,
    play_count: 30,
    genres: [],
    format: "mp3",
  },
  {
    rb_content_id: "rb2",
    artist: "Daft Punk",
    title: "One More Time",
    duration_ms: 210_000,
    bpm: 123,
    play_count: 50,
    genres: [],
    format: "mp3",
  },
];

beforeEach(() => {
  mockCollection(2, TRACKS);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TrackTable", () => {
  it("renders every track's artist, title, BPM and play count", async () => {
    render(<TrackTable />);

    expect(await screen.findByText("Adele")).toBeInTheDocument();
    expect(screen.getByText("Rolling in the Deep")).toBeInTheDocument();
    expect(screen.getByText("105")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getByText("Daft Punk")).toBeInTheDocument();
  });

  it("typing in the search box requeries with the query param", async () => {
    render(<TrackTable />);
    await screen.findByText("Adele");

    fireEvent.change(screen.getByLabelText("Zoeken in collectie"), {
      target: { value: "daft" },
    });

    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({ query: "daft" }),
          }),
        }),
      ),
    );
  });

  it("clicking a column header sorts by that field, ascending then descending", async () => {
    render(<TrackTable />);
    await screen.findByText("Adele");

    fireEvent.click(screen.getByRole("button", { name: "Afspeelteller" }));
    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({ sort: "play_count" }),
          }),
        }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: /Afspeelteller/ }));
    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({ sort: "-play_count" }),
          }),
        }),
      ),
    );
  });

  it("marks the active sort column with aria-sort, conveyed as more than colour", async () => {
    render(<TrackTable />);
    await screen.findByText("Adele");

    const artistHeader = screen.getByRole("columnheader", { name: /Artiest/ });
    expect(artistHeader).toHaveAttribute("aria-sort", "ascending");
  });

  it("only the active row's play button is tab-reachable (roving tabindex)", async () => {
    render(<TrackTable />);
    await screen.findByText("Adele");

    const playButtons = screen.getAllByRole("button", { name: "Afspelen" });
    expect(playButtons[0]).toHaveAttribute("tabindex", "0");
    expect(playButtons[1]).toHaveAttribute("tabindex", "-1");
  });

  it("ArrowDown/ArrowUp move the active row without needing to re-tab", async () => {
    render(<TrackTable />);
    await screen.findByText("Adele");
    const playButtons = screen.getAllByRole("button", { name: "Afspelen" });
    playButtons[0].focus();

    fireEvent.keyDown(playButtons[0], { key: "ArrowDown" });

    expect(document.activeElement).toBe(playButtons[1]);
    expect(playButtons[1]).toHaveAttribute("tabindex", "0");
    expect(playButtons[0]).toHaveAttribute("tabindex", "-1");

    fireEvent.keyDown(playButtons[1], { key: "ArrowUp" });

    expect(document.activeElement).toBe(playButtons[0]);
  });

  it("ArrowUp at the first row does not wrap or move focus away", async () => {
    render(<TrackTable />);
    await screen.findByText("Adele");
    const playButtons = screen.getAllByRole("button", { name: "Afspelen" });
    playButtons[0].focus();

    fireEvent.keyDown(playButtons[0], { key: "ArrowUp" });

    expect(document.activeElement).toBe(playButtons[0]);
  });

  it("clicking a row's play button calls onPlay with that track", async () => {
    const onPlay = vi.fn();
    render(<TrackTable onPlay={onPlay} />);
    await screen.findByText("Adele");

    const playButtons = screen.getAllByRole("button", { name: "Afspelen" });
    fireEvent.click(playButtons[0]);

    expect(onPlay).toHaveBeenCalledWith(TRACKS[0]);
  });

  it("paginates using the API's own total, disabling Vorige on the first page", async () => {
    mockCollection(120, TRACKS);
    render(<TrackTable />);
    await screen.findByText("Adele");

    expect(screen.getByText("Pagina 1 van 3 (120 nummers)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vorige" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Volgende" }));

    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({ offset: 50 }),
          }),
        }),
      ),
    );
  });

  it("shows an empty state when nothing matches", async () => {
    mockCollection(0, []);
    render(<TrackTable />);
    // A search term is what makes this "nothing matches" rather than "the
    // index is empty", which since the phase 7 review are different messages.
    fireEvent.change(screen.getByLabelText("Zoeken in collectie"), {
      target: { value: "iets dat niet bestaat" },
    });

    expect(await screen.findByText("Geen nummers gevonden.")).toBeInTheDocument();
  });

  it("reports a documented API error distinctly from an empty result, not as 'Geen nummers gevonden.'", async () => {
    vi.mocked(apiClient.GET).mockResolvedValue({
      data: undefined,
      error: { code: "rekordbox_not_found", message: "master.db not found" },
    } as never);
    render(<TrackTable />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Rekordbox is niet gevonden. Start Rekordbox en herlaad de pagina.",
    );
    expect(screen.queryByText("Geen nummers gevonden.")).not.toBeInTheDocument();
  });

  it("reports a network failure with its own Dutch message, not a silent empty table", async () => {
    vi.mocked(apiClient.GET).mockRejectedValue(new Error("network down"));
    render(<TrackTable />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Kon de collectie niet laden. Probeer het opnieuw.");
    expect(screen.queryByText("Geen nummers gevonden.")).not.toBeInTheDocument();
  });

  it("recovers from a prior error once a later request succeeds", async () => {
    vi.mocked(apiClient.GET).mockResolvedValueOnce({
      data: undefined,
      error: { code: "rekordbox_not_found", message: "master.db not found" },
    } as never);
    render(<TrackTable />);
    await screen.findByRole("alert");

    mockCollection(2, TRACKS);
    fireEvent.change(screen.getByLabelText("Zoeken in collectie"), {
      target: { value: "daft" },
    });

    await screen.findByText("Adele");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("collection index refresh", () => {
  // Phase 7 review: the index is an in-memory cache rebuilt on demand
  // (ADR 0012) and nothing in the UI ever demanded it, so a freshly started
  // app showed an empty collection with no way to fill it. The rebuild
  // control itself now lives in the shell's sidebar (the delivered design's
  // "Collectie-scan" card, tests/components/CollectionScanCard.test.tsx);
  // what stays this table's job is telling the DJ where to find it, and
  // reloading once a rebuild has happened.
  it("tells the DJ how to fill an empty collection instead of calling it no results", async () => {
    mockCollection(0, []);

    render(<TrackTable />);

    await waitFor(() => {
      expect(screen.getByText(/nog niet ingelezen/i)).toBeInTheDocument();
    });
    expect(screen.queryByText("Geen nummers gevonden.")).not.toBeInTheDocument();
  });

  it("still says no results when a search matches nothing", async () => {
    mockCollection(0, []);

    render(<TrackTable />);
    fireEvent.change(screen.getByLabelText("Zoeken in collectie"), {
      target: { value: "iets dat niet bestaat" },
    });

    await waitFor(() => {
      expect(screen.getByText("Geen nummers gevonden.")).toBeInTheDocument();
    });
  });

  it("points at the sidebar's scan card, the app's one rebuild control", async () => {
    mockCollection(0, []);

    render(<TrackTable />);

    expect(await screen.findByText(/Opnieuw scannen/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /verversen/i })).not.toBeInTheDocument();
  });

  it("reloads once the sidebar's scan card reports a completed rebuild", async () => {
    mockCollection(0, []);
    const { rerender } = render(<TrackTable reloadToken={0} />);
    await waitFor(() => {
      expect(screen.getByText(/nog niet ingelezen/i)).toBeInTheDocument();
    });

    mockCollection(TRACKS.length, TRACKS);
    rerender(<TrackTable reloadToken={1} />);

    await waitFor(() => {
      expect(screen.getByText("Rolling in the Deep")).toBeInTheDocument();
    });
  });
});

describe("top-bar search seeding", () => {
  // The shell's top-bar search navigates to this view and seeds the query
  // (web/design-input/HANDOFF.md, "Top bar"), both on the mount that the
  // navigation causes and again for a later search while already here.
  it("starts from the seeded query", async () => {
    render(<TrackTable seedQuery="daft" seedToken={1} />);

    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({ query: expect.objectContaining({ query: "daft" }) }),
        }),
      ),
    );
    expect(screen.getByLabelText("Zoeken in collectie")).toHaveValue("daft");
  });

  it("re-seeds on a later search, even for the same term", async () => {
    const { rerender } = render(<TrackTable seedQuery="daft" seedToken={1} />);
    await screen.findByText("Adele");
    fireEvent.change(screen.getByLabelText("Zoeken in collectie"), {
      target: { value: "iets anders" },
    });

    rerender(<TrackTable seedQuery="daft" seedToken={2} />);

    expect(screen.getByLabelText("Zoeken in collectie")).toHaveValue("daft");
  });
});
