import { useState } from "react";

import { apiClient } from "./api/client";
import { MatchReport } from "./features/spotify-sync/MatchReport";
import { PlaylistUrlForm } from "./features/spotify-sync/PlaylistUrlForm";
import { SpotifyConnection } from "./features/spotify-sync/SpotifyConnection";
import { asApiResponse } from "./features/spotify-sync/types";
import type { SyncSession, SyncSessionDetail } from "./features/spotify-sync/types";

// Minimal US1-only wiring (T032 build finding): no router, no nav --
// premature before a second user story's UI exists. Assembles
// PlaylistUrlForm -> MatchReport, plus SpotifyConnection, so T033's e2e
// test has a real page to click through.
export function App() {
  const [session, setSession] = useState<SyncSessionDetail | null>(null);

  async function handleSessionCreated(created: SyncSession) {
    const { data } = await apiClient.GET("/api/sync/sessions/{session_id}", {
      params: { path: { session_id: created.id } },
    });
    setSession(asApiResponse<SyncSessionDetail>(data));
  }

  return (
    <div className="min-h-screen bg-void-black px-24 py-24 text-pure-white">
      <h1 className="text-heading font-bold">Rekordbox Companion</h1>
      <div className="mt-24">
        <SpotifyConnection />
      </div>
      <div className="mt-24">
        <PlaylistUrlForm onSessionCreated={(created) => void handleSessionCreated(created)} />
      </div>
      {session && (
        <div className="mt-24">
          <MatchReport totals={session.totals} tracks={session.tracks} />
        </div>
      )}
    </div>
  );
}
