// The sidebar's "SPOTIFY PLAYLISTS" section (web/design-input/HANDOFF.md,
// "Sidebar"): the operator's own playlists from GET /api/spotify/playlists,
// each row starting a Sync Session for that playlist.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../src/api/client";
import { SpotifyPlaylistList } from "../../src/components/SpotifyPlaylistList";

vi.mock("../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

function playlist(overrides: Record<string, unknown> = {}) {
  return {
    spotify_playlist_id: "37i9",
    name: "Bruiloft 2026",
    image_url: null,
    owner_display_name: "Martien",
    sync: {
      state: "not_scanned",
      session_id: null,
      session_created_at: null,
      last_applied_at: null,
      totals: null,
    },
    ...overrides,
  };
}

function mockPlaylists(items: unknown[]) {
  vi.mocked(apiClient.GET).mockResolvedValue({ data: items, error: undefined } as never);
}

function mockRefusal(code: string) {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: undefined,
    error: { code, message: "refused" },
  } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPlaylists([playlist()]);
});

describe("SpotifyPlaylistList", () => {
  it("renders one row per playlist, with a placeholder cover when Spotify has no image", async () => {
    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByRole("button", { name: /Bruiloft 2026/ })).toBeInTheDocument();
    // The handoff's placeholder block, not a broken image.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("♫")).toBeInTheDocument();
  });

  it("uses the real cover art when Spotify supplies one", async () => {
    mockPlaylists([playlist({ image_url: "https://i.scdn.co/image/abc" })]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    await screen.findByRole("button", { name: /Bruiloft 2026/ });
    const cover = document.querySelector("img");
    expect(cover).toHaveAttribute("src", "https://i.scdn.co/image/abc");
    // Decorative: the playlist name is already text in the same row.
    expect(cover).toHaveAttribute("alt", "");
  });

  it("never invents a track count, because Spotify does not send one", async () => {
    mockPlaylists([playlist()]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    await screen.findByRole("button", { name: /Bruiloft 2026/ });
    expect(screen.queryByText(/tracks/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/nummers/i)).not.toBeInTheDocument();
  });

  it("says a playlist has never been scanned", async () => {
    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByText("Nog niet gescand")).toBeInTheDocument();
  });

  it("reports the totals of a finished scan, missing tracks included", async () => {
    mockPlaylists([
      playlist({
        sync: {
          state: "ready",
          session_id: 12,
          session_created_at: "2026-08-18T00:00:00",
          last_applied_at: null,
          totals: { matched: 2, review: 1, missing: 1, rejected: 0, unmatchable: 0 },
        },
      }),
    ]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(
      await screen.findByText("2 gematcht · 1 te controleren · 1 ontbreekt"),
    ).toBeInTheDocument();
  });

  it("pluralises more than one missing track", async () => {
    mockPlaylists([
      playlist({
        sync: {
          state: "ready",
          session_id: 12,
          session_created_at: "2026-08-18T00:00:00",
          last_applied_at: null,
          totals: { matched: 0, review: 0, missing: 3, rejected: 0, unmatchable: 0 },
        },
      }),
    ]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByText("3 ontbreken")).toBeInTheDocument();
  });

  it("reports a running scan, and a failed one, in words", async () => {
    mockPlaylists([
      playlist({ spotify_playlist_id: "a", name: "Aan het halen", sync: syncState("fetching") }),
      playlist({ spotify_playlist_id: "b", name: "Aan het matchen", sync: syncState("matching") }),
      playlist({ spotify_playlist_id: "c", name: "Mislukt", sync: syncState("failed") }),
    ]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByText("Ophalen bij Spotify…")).toBeInTheDocument();
    expect(screen.getByText("Matchen met je collectie…")).toBeInTheDocument();
    expect(screen.getByText("Laatste sync mislukt")).toBeInTheDocument();
  });

  it("names the day a playlist was written back to Rekordbox", async () => {
    mockPlaylists([
      playlist({
        sync: {
          state: "applied",
          session_id: 12,
          session_created_at: "2026-08-18T00:00:00",
          last_applied_at: "2026-08-18T12:30:00",
          totals: { matched: 2, review: 0, missing: 0, rejected: 0, unmatchable: 0 },
        },
      }),
    ]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByText("Toegepast in Rekordbox · 18-08-2026")).toBeInTheDocument();
  });

  it("starts a sync for the clicked playlist and hands the session up", async () => {
    const onSessionCreated = vi.fn();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { id: 7, name: "Bruiloft 2026" },
      error: undefined,
    } as never);

    render(<SpotifyPlaylistList onSessionCreated={onSessionCreated} />);
    fireEvent.click(await screen.findByRole("button", { name: /Bruiloft 2026/ }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith("/api/sync/sessions", {
        body: { playlist_url: "https://open.spotify.com/playlist/37i9" },
      }),
    );
    await waitFor(() =>
      expect(onSessionCreated).toHaveBeenCalledWith({ id: 7, name: "Bruiloft 2026" }),
    );
  });

  it("marks the playlist whose report is open, not by colour alone", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({ data: { id: 7 }, error: undefined } as never);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);
    const row = await screen.findByRole("button", { name: /Bruiloft 2026/ });
    expect(row).not.toHaveAttribute("aria-current");

    fireEvent.click(row);

    await waitFor(() => expect(row).toHaveAttribute("aria-current", "true"));
  });

  it("reports a refused sync in Dutch instead of failing silently", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "playlist_too_large", message: "1200 tracks" },
    } as never);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Bruiloft 2026/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Deze afspeellijst heeft meer dan 999 nummers. Splits de afspeellijst op en probeer het opnieuw.",
    );
  });

  it.each([
    ["spotify_not_connected", "Verbind je Spotify-account om je afspeellijsten te zien."],
    ["spotify_session_expired", "Je Spotify-sessie is verlopen. Verbind je account opnieuw."],
    [
      "spotify_not_configured",
      "Spotify is niet ingesteld op deze computer. Vul de Spotify-client-ID en het secret in.",
    ],
    [
      "spotify_playlists_unavailable",
      "Spotify kon je afspeellijsten nu niet geven. Probeer het straks opnieuw.",
    ],
  ])(
    "turns the documented refusal %s into a Dutch message, never an empty list",
    async (code, message) => {
      mockRefusal(code);

      render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(
        screen.queryByText("Je hebt nog geen Spotify-afspeellijsten."),
      ).not.toBeInTheDocument();
    },
  );

  it("tells an account with no playlists apart from a refusal", async () => {
    mockPlaylists([]);

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByText("Je hebt nog geen Spotify-afspeellijsten.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports a network failure with its own message", async () => {
    vi.mocked(apiClient.GET).mockRejectedValue(new Error("network down"));

    render(<SpotifyPlaylistList onSessionCreated={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Kon je Spotify-afspeellijsten niet laden. Probeer het opnieuw.",
    );
  });
});

function syncState(state: string) {
  return {
    state,
    session_id: 1,
    session_created_at: "2026-08-18T00:00:00",
    last_applied_at: null,
    totals: null,
  };
}
