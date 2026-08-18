import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "./types";
import type { SpotifyConnectionStatus } from "./types";

// T102: connection status, connect action, disconnect action -- the AVG
// deletion path (FR-001, pii-inventory.md).
export function SpotifyConnection() {
  const [status, setStatus] = useState<SpotifyConnectionStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  useEffect(() => {
    void refreshStatus();
  }, []);

  // This banner sits at the top of every page load, so a degraded backend
  // (T105) must never take the whole page down with it. Both failure shapes
  // are handled: openapi-fetch reports an HTTP error response as `{data:
  // undefined, error}` -- which would otherwise slip past the `status ===
  // null` loading guard as `setStatus(undefined)` and crash on
  // `status.connected` (review finding) -- and a network-level failure
  // rejects the call itself.
  async function refreshStatus() {
    try {
      const { data, error } = await apiClient.GET("/api/auth/spotify/status");
      if (error || data === undefined) {
        setFailed(true);
        return;
      }
      setFailed(false);
      setStatus(asApiResponse<SpotifyConnectionStatus>(data));
    } catch {
      setFailed(true);
    }
  }

  async function handleDisconnect() {
    setDisconnecting(true);
    await apiClient.POST("/api/auth/spotify/disconnect");
    setDisconnecting(false);
    await refreshStatus();
  }

  if (failed) {
    return (
      <div className="flex flex-wrap items-center gap-12">
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          De Spotify-status kon niet worden opgehaald. Controleer of de Companion-server draait.
        </p>
        <button
          type="button"
          onClick={() => void refreshStatus()}
          className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          Opnieuw proberen
        </button>
      </div>
    );
  }

  if (status === null) {
    return (
      <p className="text-body-lg text-mist" role="status">
        Spotify-status laden…
      </p>
    );
  }

  if (!status.connected) {
    return (
      <div className="flex items-center gap-12">
        <p className="text-body-lg text-mist">Niet verbonden met Spotify.</p>
        <a
          href="/api/auth/spotify/login"
          className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          Verbinden met Spotify
        </a>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-12">
      <p className="text-body-lg text-pure-white">
        Verbonden als <span className="font-semibold">{status.display_name}</span>
        {status.product === "premium" ? " (Premium)" : ""}
      </p>
      <button
        type="button"
        onClick={() => void handleDisconnect()}
        disabled={disconnecting}
        className="min-h-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
      >
        {disconnecting ? "Verbinding verbreken…" : "Verbinding verbreken"}
      </button>
    </div>
  );
}
