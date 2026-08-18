// T059: Store Link + copy action, status controls, manual override input
// with field-naming errors (FR-020..FR-022, WCAG).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
};

beforeEach(() => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
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
    expect(screen.getByRole("link", { name: "Open in Apple Music" })).toHaveAttribute(
      "href",
      "https://music.apple.com/nl/album/one-more-time/1",
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

  it("changing status posts the new status and refreshes the list", async () => {
    mockList([TRACK_WITH_LINK]);
    vi.mocked(apiClient.POST).mockResolvedValue({ data: {}, error: undefined } as never);
    render(<MissingQueue />);
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(screen.getByRole("button", { name: "Genegeerd" }));

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
});
