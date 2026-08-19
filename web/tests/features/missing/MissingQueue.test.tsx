// T059: Store Link + copy action, status controls, manual override input
// with field-naming errors (FR-020..FR-022, WCAG).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { MissingQueue } from "../../../src/features/missing/MissingQueue";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

function mockList(tracks: unknown[]) {
  vi.mocked(apiClient.GET).mockResolvedValue({ data: tracks, error: undefined } as never);
}

const TRACK_WITH_LINK = {
  id: 1,
  artist: "Daft Punk",
  title: "One More Time",
  status: "open",
  itunes_url_auto: "https://music.apple.com/nl/album/one-more-time/1",
  itunes_url_chosen: null,
  effective_url: "https://music.apple.com/nl/album/one-more-time/1",
  no_link_found: false,
  itunes_preview_url: "https://audio-ssl.itunes.apple.com/itunes-assets/one-more-time.m4a",
  itunes_price: 1.29,
  itunes_currency: "EUR",
};

const TRACK_NO_LINK = {
  id: 2,
  artist: "Nobody At All",
  title: "Nothing Similar",
  status: "open",
  itunes_url_auto: null,
  itunes_url_chosen: null,
  effective_url: null,
  no_link_found: true,
  itunes_preview_url: null,
  itunes_price: null,
  itunes_currency: null,
};

// A real store page that sells nothing on its own: a link, but no preview
// and no single-track price (FR-041's documented gaps).
const TRACK_LINK_WITHOUT_PREVIEW_OR_PRICE = {
  ...TRACK_WITH_LINK,
  id: 4,
  artist: "Album Only",
  title: "Not Sold Separately",
  itunes_preview_url: null,
  itunes_price: null,
  itunes_currency: null,
};

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  // jsdom implements neither, so both are stubbed the same way
  // DualPlayback.test.tsx does.
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MissingQueue", () => {
  it("renders each row with artist, title, status and a Store Link (US4 scenario 1)", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);

    expect(await screen.findByText("Daft Punk – One More Time")).toBeInTheDocument();
    expect(screen.getByText("Status: Open")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in browser" })).toHaveAttribute(
      "href",
      "https://music.apple.com/nl/album/one-more-time/1",
    );
  });

  // FR-042: on macOS, the Music app plays and sells the full track, the
  // browser only an excerpt -- so a music.apple.com/itunes.apple.com link
  // gets a Music-app destination too, named apart from the browser one by
  // its own link text rather than a tooltip.
  it("offers the Music app as well as the browser for a music.apple.com Store Link (FR-042)", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    expect(screen.getByRole("link", { name: "Open in Muziek-app" })).toHaveAttribute(
      "href",
      "itmss://music.apple.com/nl/album/one-more-time/1",
    );
    expect(screen.getByRole("link", { name: "Open in browser" })).toHaveAttribute(
      "href",
      "https://music.apple.com/nl/album/one-more-time/1",
    );
  });

  it("does not invent a Music-app link for a manual override that is not an Apple Music URL", async () => {
    mockList([{ ...TRACK_WITH_LINK, effective_url: "https://example.com/not-apple-music" }]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    expect(screen.queryByRole("link", { name: "Open in Muziek-app" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in browser" })).toHaveAttribute(
      "href",
      "https://example.com/not-apple-music",
    );
  });

  it("defaults to the open view, never fetching ignored tracks (scenario 3)", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    expect(apiClient.GET).toHaveBeenCalledWith(
      "/api/missing",
      expect.objectContaining({ params: { query: { status: "open" } } }),
    );
  });

  it("shows 'no link found' and offers the manual override when nothing resolved (scenario 5)", async () => {
    mockList([TRACK_NO_LINK]);
    render(<MissingQueue />);

    expect(await screen.findByText("Geen link gevonden.")).toBeInTheDocument();
    expect(screen.getByLabelText("Handmatige link")).toBeInTheDocument();
  });

  it("copies the Store Link to the clipboard", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(screen.getByRole("button", { name: "Kopieer link" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        "https://music.apple.com/nl/album/one-more-time/1",
      ),
    );
    expect(await screen.findByRole("button", { name: "Gekopieerd" })).toBeInTheDocument();
  });

  // FR-041 (ADR 0021): hear it and see the price before buying.
  it("plays the store preview and names the track in the control's accessible name", async () => {
    mockList([TRACK_WITH_LINK]);
    const { container } = render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    const play = screen.getByRole("button", {
      name: "Speel fragment van Daft Punk – One More Time",
    });
    expect(play).toHaveAttribute("aria-pressed", "false");
    expect(container.querySelector("audio")).toHaveAttribute(
      "src",
      "https://audio-ssl.itunes.apple.com/itunes-assets/one-more-time.m4a",
    );

    fireEvent.click(play);

    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1));
    // State in text AND in an accessible attribute, never colour alone.
    const pause = await screen.findByRole("button", {
      name: "Pauzeer fragment van Daft Punk – One More Time",
    });
    expect(pause).toHaveAttribute("aria-pressed", "true");
    expect(pause).toHaveTextContent("Pauzeer fragment");
  });

  it("pauses the preview again on a second press", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(
      screen.getByRole("button", { name: "Speel fragment van Daft Punk – One More Time" }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Pauzeer fragment van Daft Punk – One More Time",
      }),
    );

    await waitFor(() => expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled());
    expect(
      await screen.findByRole("button", { name: "Speel fragment van Daft Punk – One More Time" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("plays only one preview at a time: starting the second stops the first", async () => {
    const SECOND = {
      ...TRACK_WITH_LINK,
      id: 3,
      artist: "Stardust",
      title: "Music Sounds Better with You",
      itunes_preview_url: "https://audio-ssl.itunes.apple.com/itunes-assets/music-sounds.m4a",
    };
    mockList([TRACK_WITH_LINK, SECOND]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(
      screen.getByRole("button", { name: "Speel fragment van Daft Punk – One More Time" }),
    );
    await screen.findByRole("button", { name: "Pauzeer fragment van Daft Punk – One More Time" });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Speel fragment van Stardust – Music Sounds Better with You",
      }),
    );

    // The second row is the only one still pressed.
    expect(
      await screen.findByRole("button", {
        name: "Pauzeer fragment van Stardust – Music Sounds Better with You",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: "Speel fragment van Daft Punk – One More Time" }),
    ).toHaveAttribute("aria-pressed", "false");
    await waitFor(() => expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled());
  });

  it("says a row has no preview instead of offering a dead control", async () => {
    mockList([TRACK_LINK_WITHOUT_PREVIEW_OR_PRICE]);
    render(<MissingQueue />);

    expect(await screen.findByText("Geen fragment beschikbaar.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Speel fragment/ })).not.toBeInTheDocument();
  });

  it("shows the price beside the Store Link, formatted for the Dutch locale", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    expect(screen.getByText(/Prijs:/)).toHaveTextContent(/1,29/);
    expect(screen.getByText(/Prijs:/)).toHaveTextContent(/€/);
  });

  it("shows no price at all for a track the store does not sell separately", async () => {
    mockList([TRACK_LINK_WITHOUT_PREVIEW_OR_PRICE]);
    render(<MissingQueue />);
    await screen.findByText("Album Only – Not Sold Separately");

    // A link to open, but no invented amount beside it.
    expect(screen.getByRole("link", { name: "Open in browser" })).toBeInTheDocument();
    expect(screen.queryByText(/Prijs:/)).not.toBeInTheDocument();
  });

  it("reports a preview that will not play and releases the control", async () => {
    HTMLMediaElement.prototype.play = vi.fn().mockRejectedValue(new Error("NotAllowedError"));
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(
      screen.getByRole("button", { name: "Speel fragment van Daft Punk – One More Time" }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Fragment kon niet worden afgespeeld.");
    // Never a button reading "Pauzeer fragment" over silence.
    expect(
      await screen.findByRole("button", { name: "Speel fragment van Daft Punk – One More Time" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("changing status posts the new status and refreshes the list", async () => {
    mockList([TRACK_WITH_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({ data: {}, error: undefined } as never);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    // Scoped to the row's own status group: the top-level status filter
    // (review finding) also has a button named "Genegeerd".
    const statusGroup = screen.getByRole("group", { name: "Status wijzigen" });
    fireEvent.click(within(statusGroup).getByRole("button", { name: "Genegeerd" }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/missing/{missing_id}/status",
        expect.objectContaining({
          params: { path: { missing_id: 1 } },
          body: { status: "ignored" },
        }),
      ),
    );
    // Refresh is the second GET call (initial load + post-change refresh).
    await waitFor(() => expect(apiClient.GET).toHaveBeenCalledTimes(2));
  });

  it("shows an error and does not refresh when a status change fails (review finding)", async () => {
    mockList([TRACK_WITH_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "missing_track_not_found", message: "no missing track 1" },
    } as never);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    const statusGroup = screen.getByRole("group", { name: "Status wijzigen" });
    fireEvent.click(within(statusGroup).getByRole("button", { name: "Genegeerd" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Dit ontbrekende nummer bestaat niet meer.");
    // A failed status change must not silently refresh/replace the queue
    // (previously the error was never inspected at all).
    expect(apiClient.GET).toHaveBeenCalledTimes(1);
  });

  it("shows an error and does not refresh when refresh-links fails (review finding)", async () => {
    mockList([TRACK_WITH_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "itunes_unreachable", message: "iTunes Search API is unreachable" },
    } as never);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(screen.getByRole("button", { name: "Links vernieuwen" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("iTunes Search API is unreachable");
    expect(apiClient.GET).toHaveBeenCalledTimes(1);
  });

  it("offers a filter to reach the acquired/ignored views, not just the open default (review finding)", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    const ACQUIRED_TRACK = { ...TRACK_WITH_LINK, id: 3, status: "acquired" };
    mockList([ACQUIRED_TRACK]);
    const filterGroup = screen.getByRole("group", { name: "Filter op status" });
    fireEvent.click(within(filterGroup).getByRole("button", { name: "Aangeschaft" }));

    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/missing",
        expect.objectContaining({ params: { query: { status: "acquired" } } }),
      ),
    );
    expect(await screen.findByText("Status: Aangeschaft")).toBeInTheDocument();
  });

  it("shows a filter-specific empty state for the ignored view", async () => {
    mockList([TRACK_WITH_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    mockList([]);
    const filterGroup = screen.getByRole("group", { name: "Filter op status" });
    fireEvent.click(within(filterGroup).getByRole("button", { name: "Genegeerd" }));

    expect(await screen.findByText("Geen genegeerde nummers.")).toBeInTheDocument();
  });

  it("submitting the override without a value names the field and the fix", async () => {
    mockList([TRACK_NO_LINK]);
    render(<MissingQueue />);
    await screen.findByText("Nobody At All – Nothing Similar");

    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Vul een Apple Music / iTunes-link in.");
    expect(apiClient.POST).not.toHaveBeenCalled();
  });

  it("shows the backend's error when the manual override link is rejected", async () => {
    mockList([TRACK_NO_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "missing_track_not_found", message: "no missing track 2" },
    } as never);
    render(<MissingQueue />);
    await screen.findByText("Nobody At All – Nothing Similar");

    fireEvent.change(screen.getByLabelText("Handmatige link"), {
      target: { value: "https://music.apple.com/nl/album/example/2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Dit ontbrekende nummer bestaat niet meer.");
    // A rejected override must not clear the DJ's typed input.
    expect(screen.getByLabelText("Handmatige link")).toHaveValue(
      "https://music.apple.com/nl/album/example/2",
    );
  });

  it("submitting a manual override link posts it and clears the input", async () => {
    mockList([TRACK_NO_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({ data: {}, error: undefined } as never);
    render(<MissingQueue />);
    await screen.findByText("Nobody At All – Nothing Similar");

    fireEvent.change(screen.getByLabelText("Handmatige link"), {
      target: { value: "https://music.apple.com/nl/album/example/2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/missing/{missing_id}/link",
        expect.objectContaining({
          params: { path: { missing_id: 2 } },
          body: { itunes_url: "https://music.apple.com/nl/album/example/2" },
        }),
      ),
    );
    await waitFor(() => expect(screen.getByLabelText("Handmatige link")).toHaveValue(""));
  });

  it("shows an empty state when there are no open missing tracks", async () => {
    mockList([]);
    render(<MissingQueue />);

    expect(await screen.findByText("Geen openstaande ontbrekende nummers.")).toBeInTheDocument();
  });

  it("degrades to the empty view instead of crashing when the fetch itself fails", async () => {
    // T107 finding: this queue is mounted unconditionally on every page,
    // so a network-level failure (not an HTTP error response) must not
    // crash the surrounding page.
    vi.mocked(apiClient.GET).mockRejectedValue(new TypeError("Failed to fetch"));
    render(<MissingQueue />);

    expect(await screen.findByText("Geen openstaande ontbrekende nummers.")).toBeInTheDocument();
  });

  it("clicking refresh-links re-runs lookups and reloads the list", async () => {
    mockList([TRACK_WITH_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({ data: {}, error: undefined } as never);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(screen.getByRole("button", { name: "Links vernieuwen" }));

    await waitFor(() => expect(apiClient.POST).toHaveBeenCalledWith("/api/missing/refresh-links"));
    await waitFor(() => expect(apiClient.GET).toHaveBeenCalledTimes(2));
  });

  // Owner decision: the design's two-column buy queue -- one store card
  // holding the tracks as rows, plus a sticky summary panel with the real
  // total of the open tracks (HANDOFF.md, "2. Koop-wachtrij").
  describe("the store card and summary panel (owner decision: two-column buy queue)", () => {
    it("shows the store card header with the real track count and total", async () => {
      mockList([TRACK_WITH_LINK]);
      render(<MissingQueue />);
      await screen.findByText("Daft Punk – One More Time");

      const card = screen.getByTestId("buy-queue-store-card");
      expect(within(card).getByText("Apple Music")).toBeInTheDocument();
      expect(within(card).getByText("1 tracks")).toBeInTheDocument();
      expect(screen.getByTestId("buy-queue-store-card-total")).toHaveTextContent(/1,29/);
    });

    it("sums only the prices that are present and reports how many rows have none, never inventing a total", async () => {
      const UNPRICED = { ...TRACK_NO_LINK, id: 5, itunes_price: null };
      mockList([TRACK_WITH_LINK, UNPRICED]);
      render(<MissingQueue />);
      await screen.findByText("Daft Punk – One More Time");

      const summary = screen.getByTestId("buy-queue-summary");
      // Two open tracks, one priced (1.29) and one not: the total is the
      // priced one alone, and the unpriced one is reported, not hidden.
      expect(within(summary).getByText("2 tracks")).toBeInTheDocument();
      expect(within(summary).getByText("1 zonder prijs")).toBeInTheDocument();
      // The total appears twice in the summary panel (running total row and
      // the bordered "Totaal" row); both must show the real sum, not a
      // placeholder like the design's static "€ 26,84".
      expect(within(summary).getAllByText(/1,29/)).toHaveLength(2);
    });

    it("shows a dash rather than an invented amount when no open track has a price", async () => {
      mockList([TRACK_NO_LINK]);
      render(<MissingQueue />);
      await screen.findByText("Nobody At All – Nothing Similar");

      const summary = screen.getByTestId("buy-queue-summary");
      expect(within(summary).getByText("1 tracks")).toBeInTheDocument();
      expect(within(summary).getByText("1 zonder prijs")).toBeInTheDocument();
      expect(within(summary).getAllByText("–")).toHaveLength(2);
    });

    it("keeps the summary panel's total pinned to the open queue while browsing another filter", async () => {
      mockList([TRACK_WITH_LINK]);
      render(<MissingQueue />);
      await screen.findByText("Daft Punk – One More Time");
      // The initial "open" load also seeds the summary's own open-queue
      // total: confirm it before switching filters.
      expect(
        within(screen.getByTestId("buy-queue-summary")).getByText("1 tracks"),
      ).toBeInTheDocument();

      const ACQUIRED_TRACK = { ...TRACK_WITH_LINK, id: 9, status: "acquired", itunes_price: 4.5 };
      mockList([ACQUIRED_TRACK]);
      const filterGroup = screen.getByRole("group", { name: "Filter op status" });
      fireEvent.click(within(filterGroup).getByRole("button", { name: "Aangeschaft" }));
      await screen.findByText("Status: Aangeschaft");

      // The store card now reflects the Aangeschaft filter, but the summary
      // still reports the last known OPEN total, not the acquired one.
      expect(screen.getByTestId("buy-queue-store-card-total")).toHaveTextContent(/4,50/);
      const summary = screen.getByTestId("buy-queue-summary");
      expect(within(summary).getByText("1 tracks")).toBeInTheDocument();
      expect(within(summary).getAllByText(/1,29/).length).toBeGreaterThan(0);
    });

    it("stacks the two-column shell into a single column below the handoff's stacking width", async () => {
      mockList([TRACK_WITH_LINK]);
      render(<MissingQueue />);
      await screen.findByText("Daft Punk – One More Time");

      const shell = screen.getByTestId("buy-queue-columns");
      expect(shell.className).toContain("grid-cols-1");
      // The `stack:` variant comes from `--breakpoint-stack` in theme.css, so
      // this asserts the token is used rather than a hardcoded width.
      expect(shell.className).toContain("stack:grid-cols-");
    });
  });
});
