import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../api/client";
import { asApiResponse } from "../features/spotify-sync/types";
import type { SyncSession, SyncTotals } from "../features/spotify-sync/types";

// GET /api/spotify/playlists (contracts/api.md, "Spotify playlists"), typed by
// hand for the same reason as the sync feature's shapes: the backend routes
// carry no `response_model`, so the generated client types every response
// `unknown` (features/spotify-sync/types.ts).
//
// There is deliberately no track count: Spotify strips the `tracks` object
// from `/me/playlists` for this application, so none is reported and none is
// invented.
export type SpotifySyncState =
  "not_scanned" | "fetching" | "matching" | "ready" | "applied" | "failed";

export interface SpotifyPlaylistDto {
  spotify_playlist_id: string;
  name: string;
  image_url: string | null;
  owner_display_name: string | null;
  sync: {
    state: SpotifySyncState;
    session_id: number | null;
    session_created_at: string | null;
    last_applied_at: string | null;
    totals: SyncTotals | null;
  };
}

interface SpotifyPlaylistListProps {
  // A started sync hands its session to the shell, which switches to the
  // Match-overzicht view and loads the report.
  onSessionCreated: (session: SyncSession) => void;
}

// The list endpoint answers a documented refusal, never a short or empty list
// (engine/src/companion/api/spotify.py), so each code gets its own Dutch
// message and its own fix.
function listErrorMessageFor(apiError: unknown): string {
  const code = (apiError as { code?: string } | undefined)?.code;
  switch (code) {
    case "spotify_not_connected":
      return "Verbind je Spotify-account om je afspeellijsten te zien.";
    case "spotify_session_expired":
      return "Je Spotify-sessie is verlopen. Verbind je account opnieuw.";
    case "spotify_not_configured":
      return "Spotify is niet ingesteld op deze computer. Vul de Spotify-client-ID en het secret in.";
    case "spotify_playlists_unavailable":
      return "Spotify kon je afspeellijsten nu niet geven. Probeer het straks opnieuw.";
    default:
      return "Kon je Spotify-afspeellijsten niet laden. Probeer het opnieuw.";
  }
}

// POST /api/sync/sessions' own documented codes (api/sync.py), the same set
// PlaylistUrlForm maps -- minus the URL-shaped ones, because this row builds
// the URL itself from an id Spotify just handed us.
function syncErrorMessageFor(apiError: unknown, playlistName: string): string {
  const code = (apiError as { code?: string } | undefined)?.code;
  switch (code) {
    case "spotify_not_connected":
      return "Verbind eerst je Spotify-account voordat je kunt synchroniseren.";
    case "playlist_too_large":
      return "Deze afspeellijst heeft meer dan 999 nummers. Splits de afspeellijst op en probeer het opnieuw.";
    case "playlist_unreachable":
      return "Deze afspeellijst is niet beschikbaar bij Spotify. Controleer of hij nog bestaat.";
    default:
      return `Synchroniseren van ${playlistName} is mislukt. Probeer het opnieuw.`;
  }
}

function formatDay(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("nl-NL", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// The counts of the latest Sync Session, only the ones that are not zero: a
// row of five zeroes says nothing, and the meta line is one truncated line in
// a 300px column.
function totalsLine(totals: SyncTotals | null): string | null {
  if (!totals) return null;
  const parts: string[] = [];
  if (totals.matched > 0) parts.push(`${totals.matched} gematcht`);
  if (totals.review > 0) parts.push(`${totals.review} te controleren`);
  if (totals.missing > 0) {
    parts.push(totals.missing === 1 ? "1 ontbreekt" : `${totals.missing} ontbreken`);
  }
  if (totals.rejected > 0) parts.push(`${totals.rejected} afgewezen`);
  if (totals.unmatchable > 0) parts.push(`${totals.unmatchable} niet matchbaar`);
  return parts.length > 0 ? parts.join(" · ") : "Geen nummers in deze afspeellijst";
}

// The row's second line. Derived from `sync.state` plus `sync.totals`, because
// the endpoint deliberately returns a state and counts rather than a rendered
// sentence: UI copy is Dutch and belongs here.
export function syncMetaLine(sync: SpotifyPlaylistDto["sync"]): string {
  switch (sync.state) {
    case "not_scanned":
      return "Nog niet gescand";
    case "fetching":
      return "Ophalen bij Spotify…";
    case "matching":
      return "Matchen met je collectie…";
    case "failed":
      return "Laatste sync mislukt";
    case "applied": {
      const day = formatDay(sync.last_applied_at);
      return day ? `Toegepast in Rekordbox · ${day}` : "Toegepast in Rekordbox";
    }
    case "ready":
    default:
      return totalsLine(sync.totals) ?? "Gescand";
  }
}

// The sidebar's "SPOTIFY PLAYLISTS" block (HANDOFF.md, "Sidebar"): 40x40
// cover, name with ellipsis, meta line. Clicking a row starts a Sync Session
// for that playlist, which is what replaces pasting a URL.
export function SpotifyPlaylistList({ onSessionCreated }: SpotifyPlaylistListProps) {
  const [playlists, setPlaylists] = useState<SpotifyPlaylistDto[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [openedId, setOpenedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data, error: apiError } = await apiClient.GET("/api/spotify/playlists");
      if (apiError) {
        setLoadError(listErrorMessageFor(apiError));
        setPlaylists(null);
        return;
      }
      setLoadError(null);
      setPlaylists(asApiResponse<SpotifyPlaylistDto[] | undefined>(data) ?? []);
    } catch {
      setLoadError(listErrorMessageFor(undefined));
      setPlaylists(null);
    }
  }, []);

  useEffect(() => {
    // Fetching on mount; nothing here is derivable during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function startSync(playlist: SpotifyPlaylistDto) {
    setSyncingId(playlist.spotify_playlist_id);
    setSyncError(null);
    try {
      const { data, error: apiError } = await apiClient.POST("/api/sync/sessions", {
        // The backend parses a URL, a URI or a bare id (integrations/
        // spotify.py, parse_playlist_id); the canonical URL keeps this row
        // and the pasted-URL form on exactly one code path.
        body: { playlist_url: `https://open.spotify.com/playlist/${playlist.spotify_playlist_id}` },
      });
      if (apiError) {
        setSyncError(syncErrorMessageFor(apiError, playlist.name));
        return;
      }
      setOpenedId(playlist.spotify_playlist_id);
      onSessionCreated(asApiResponse<SyncSession>(data));
      // The row's meta line is now stale: a session exists where none did.
      await load();
    } catch {
      setSyncError(syncErrorMessageFor(undefined, playlist.name));
    } finally {
      setSyncingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      {loadError && (
        <p role="alert" className="text-caption leading-body text-pure-white">
          {loadError}
        </p>
      )}
      {syncError && (
        <p role="alert" className="text-caption leading-body text-pure-white">
          {syncError}
        </p>
      )}
      {playlists === null && loadError === null && (
        <p className="text-caption leading-body text-mist">Afspeellijsten laden…</p>
      )}
      {playlists !== null && playlists.length === 0 && (
        <p className="text-caption leading-body text-mist">
          Je hebt nog geen Spotify-afspeellijsten.
        </p>
      )}
      {playlists !== null && playlists.length > 0 && (
        <ul className="flex flex-col">
          {playlists.map((playlist) => {
            const isSyncing = syncingId === playlist.spotify_playlist_id;
            const isOpen = openedId === playlist.spotify_playlist_id;
            return (
              <li key={playlist.spotify_playlist_id}>
                <button
                  type="button"
                  aria-busy={isSyncing}
                  // Which playlist's report the main pane shows is announced,
                  // not only shaded (WCAG 1.4.1).
                  aria-current={isOpen ? "true" : undefined}
                  onClick={() => void startSync(playlist)}
                  className={`flex w-full items-center gap-12 rounded-md p-8 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green ${
                    isOpen ? "bg-smoke" : "hover:bg-graphite"
                  }`}
                >
                  {playlist.image_url ? (
                    // Decorative: the playlist name is text in the same row.
                    <img
                      src={playlist.image_url}
                      alt=""
                      className="h-40 w-40 flex-none rounded-md object-cover"
                    />
                  ) : (
                    <span
                      aria-hidden="true"
                      className="grid h-40 w-40 flex-none place-items-center rounded-md bg-smoke text-body-lg text-steel"
                    >
                      ♫
                    </span>
                  )}
                  <span className="flex min-w-0 flex-col gap-2">
                    <span className="truncate text-body font-semibold text-pure-white">
                      {playlist.name}
                    </span>
                    <span className="truncate text-caption text-mist">
                      {isSyncing ? "Synchroniseren…" : syncMetaLine(playlist.sync)}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
