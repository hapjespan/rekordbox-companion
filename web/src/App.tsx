import { useState } from "react";

import { apiClient } from "./api/client";
import { MissingQueue } from "./features/missing/MissingQueue";
import { ApplyAction } from "./features/spotify-sync/ApplyAction";
import { MatchReport } from "./features/spotify-sync/MatchReport";
import { PlaylistUrlForm } from "./features/spotify-sync/PlaylistUrlForm";
import { SpotifyConnection } from "./features/spotify-sync/SpotifyConnection";
import { asApiResponse } from "./features/spotify-sync/types";
import type { SyncSession, SyncSessionDetail } from "./features/spotify-sync/types";

// Minimal US1/US3/US4-only wiring (T032 build finding, extended by
// T052/T107): no router, no nav -- premature before a fifth user story's UI
// exists. Assembles PlaylistUrlForm -> MatchReport -> ApplyAction, plus
// SpotifyConnection and MissingQueue (not session-scoped: the Missing
// Tracks queue spans every playlist lineage, per contracts/api.md's
// `GET /api/missing` having no session id), so T033/T052/T107's e2e tests
// have a real page to click through.
export function App() {
  const [session, setSession] = useState<SyncSessionDetail | null>(null);

  async function refreshSession(sessionId: number) {
    const { data } = await apiClient.GET("/api/sync/sessions/{session_id}", {
      params: { path: { session_id: sessionId } },
    });
    setSession(asApiResponse<SyncSessionDetail>(data));
  }

  async function handleSessionCreated(created: SyncSession) {
    await refreshSession(created.id);
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
      {session && (
        <div className="mt-24">
          <ApplyAction
            sessionId={session.id}
            defaultPlaylistName={session.name}
            onApplied={() => void refreshSession(session.id)}
          />
        </div>
      )}
      <div className="mt-24">
        <MissingQueue />
      </div>
    </div>
  );
}
