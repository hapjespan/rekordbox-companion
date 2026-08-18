import { useState } from "react";

import { apiClient } from "./api/client";
import { EnrichmentPanel } from "./features/enrichment/EnrichmentPanel";
import { MissingQueue } from "./features/missing/MissingQueue";
import { ApplyAction } from "./features/spotify-sync/ApplyAction";
import { MatchReport } from "./features/spotify-sync/MatchReport";
import { PlaylistUrlForm } from "./features/spotify-sync/PlaylistUrlForm";
import { SpotifyConnection } from "./features/spotify-sync/SpotifyConnection";
import { asApiResponse } from "./features/spotify-sync/types";
import type { SyncSession, SyncSessionDetail } from "./features/spotify-sync/types";

// Minimal US1/US3/US4/US6 wiring (T032 build finding, extended by
// T052/T107/T077): no router, no nav -- premature before every user story
// has its own screen. Assembles PlaylistUrlForm -> MatchReport ->
// ApplyAction, plus SpotifyConnection, MissingQueue and EnrichmentPanel (all
// three not session-scoped: they span every playlist lineage or the whole
// collection, per contracts/api.md), so T033/T052/T107's e2e tests have a
// real page to click through. US5's TrackTable/PlayerBar (T064/T065) are
// not wired in here yet -- a pre-existing gap, not this task's (T077) scope.
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
      <div className="mt-24">
        <EnrichmentPanel />
      </div>
    </div>
  );
}
