import { useEffect, useId, useState } from "react";

import { apiClient } from "../api/client";
import { asApiResponse } from "../features/spotify-sync/types";
import type { SpotifyConnectionStatus } from "../features/spotify-sync/types";

// GET /api/health's documented body (engine/src/companion/api/health.py).
// Typed by hand for the same reason as the sync feature's shapes: the
// backend routes carry no `response_model`, so the generated client types
// every response `unknown` (see features/spotify-sync/types.ts).
interface HealthStatus {
  status: string;
  rekordbox_version: string | null;
  version_pin_ok: boolean;
  rekordbox_running: boolean;
}

interface TopBarProps {
  spotifyStatus: SpotifyConnectionStatus | null;
  // Submitting the search field navigates to the Collection view and seeds
  // its query; the shell owns that transition (App.tsx).
  onSearch: (query: string) => void;
  // The white "Sync" pill switches to Match-overzicht and focuses the
  // playlist URL field.
  onSyncRequested: () => void;
}

const PRIMARY_PILL =
  "inline-flex h-32 items-center justify-center rounded-full-2 bg-pure-white px-16 text-body font-bold whitespace-nowrap text-void-black hover:bg-chalk focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

function rekordboxLabel(health: HealthStatus | null, failed: boolean): string {
  if (failed) return "Rekordbox-status onbekend";
  if (health === null) return "Rekordbox-status laden…";
  // The version the app pins (7.2.17) is not hardcoded here: whatever health
  // reports is what the DJ's machine actually has, and a mismatch is exactly
  // what `version_pin_ok` reports as "degraded" (FR-015).
  if (health.rekordbox_version === null) return "Rekordbox niet gevonden";
  if (health.status !== "ok") return `Rekordbox ${health.rekordbox_version} niet gereed`;
  return `Rekordbox ${health.rekordbox_version} verbonden`;
}

function spotifyLabel(status: SpotifyConnectionStatus | null): string {
  if (status === null) return "Spotify · status onbekend";
  if (!status.connected) return "Spotify niet verbonden";
  return `Spotify · ${status.display_name ?? "verbonden"}`;
}

// The shell's top bar (HANDOFF.md, "Top bar"): 64px tall, full width, on the
// black canvas. Wired to real data throughout -- the Rekordbox version comes
// from GET /api/health and the Spotify display name from the auth status the
// shell already fetches, never from the prototype's demo strings.
export function TopBar({ spotifyStatus, onSearch, onSyncRequested }: TopBarProps) {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthFailed, setHealthFailed] = useState(false);
  const [query, setQuery] = useState("");
  const searchId = useId();

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const { data, error } = await apiClient.GET("/api/health");
        if (cancelled) return;
        if (error || data === undefined) {
          setHealthFailed(true);
          return;
        }
        setHealthFailed(false);
        setHealth(asApiResponse<HealthStatus>(data));
      } catch {
        if (!cancelled) setHealthFailed(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const rekordboxOk = health !== null && health.status === "ok";

  return (
    <header className="col-span-full flex h-64 items-center gap-16 border-b border-graphite bg-void-black px-24">
      <div className="flex w-252 flex-none items-center gap-10">
        <span
          aria-hidden="true"
          className="grid h-26 w-26 place-items-center rounded-full bg-spotify-green text-body font-bold text-void-black"
        >
          R
        </span>
        {/* The prototype's wordmark reads "Crate Bridge", the design bundle's
            own working name. The product is Rekordbox Companion. */}
        <span className="text-body-lg font-bold tracking-wordmark text-pure-white">
          Rekordbox Companion
        </span>
      </div>

      <form
        role="search"
        className="flex h-36 w-340 min-w-0 shrink items-center gap-8 rounded-full bg-graphite px-14"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch(query);
        }}
      >
        <label htmlFor={searchId} className="sr-only">
          Zoek in collectie of playlist
        </label>
        <input
          id={searchId}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Zoek in collectie of playlist"
          className="min-w-0 flex-1 bg-transparent text-body text-bone placeholder-bone focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        />
        <button
          type="submit"
          aria-label="Zoeken"
          className="grid h-24 w-24 flex-none place-items-center rounded-full text-body text-bone focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          <span aria-hidden="true">⌕</span>
        </button>
      </form>

      <div className="flex-1" />

      <div className="flex min-w-0 items-center gap-8 text-body-sm text-mist">
        {/* The dot repeats what the text already says, so it is decorative:
            status is never carried by colour alone (WCAG 1.4.1). */}
        <span
          aria-hidden="true"
          className={`h-7 w-7 flex-none rounded-full ${rekordboxOk ? "bg-spotify-green" : "bg-steel"}`}
        />
        <span className="truncate">{rekordboxLabel(health, healthFailed)}</span>
        {/* The prototype's pipe divider, drawn as a rule rather than a "|"
            glyph: at #333333 a text pipe would fail AA contrast. */}
        <span aria-hidden="true" className="mx-4 h-12 flex-none border-l border-iron" />
        <span className="truncate">{spotifyLabel(spotifyStatus)}</span>
      </div>

      <button type="button" onClick={onSyncRequested} className={`flex-none ${PRIMARY_PILL}`}>
        Sync
      </button>
    </header>
  );
}
