import { useState } from "react";

import { apiClient } from "./api/client";
import { PlayerBar, type PlayerBarTrack } from "./components/PlayerBar";
import { TrackTable } from "./components/TrackTable";
import { BookingWorkspace } from "./features/bookings/BookingWorkspace";
import { EnrichmentPanel } from "./features/enrichment/EnrichmentPanel";
import { MissingQueue } from "./features/missing/MissingQueue";
import { ReviewView } from "./features/review/ReviewView";
import { ApplyAction } from "./features/spotify-sync/ApplyAction";
import { MatchReport } from "./features/spotify-sync/MatchReport";
import { PlaylistUrlForm } from "./features/spotify-sync/PlaylistUrlForm";
import { SpotifyConnection } from "./features/spotify-sync/SpotifyConnection";
import { asApiResponse } from "./features/spotify-sync/types";
import type { SyncSession, SyncSessionDetail } from "./features/spotify-sync/types";

// Wiring for all seven user stories (T032 build finding, extended by
// T052/T107/T077/T088 and two phase 7 review findings that added US2 and US5):
// no router, no nav -- premature before every user story has its own screen.
// Assembles PlaylistUrlForm -> MatchReport -> ReviewView -> ApplyAction, plus
// SpotifyConnection, MissingQueue, EnrichmentPanel, BookingWorkspace and the
// collection browser (all not session-scoped: they span every playlist lineage
// or the whole collection, per contracts/api.md), so T033/T052/T107's e2e
// tests have a real page to click through.
//
// Every story must be reachable from here or it does not exist for the DJ,
// however well its components are tested in isolation: US2 and US5 both
// shipped as unmounted components and were caught in phase 7, US5 only by
// running the app and looking at it.
export function App() {
  const [session, setSession] = useState<SyncSessionDetail | null>(null);
  const [playingTrack, setPlayingTrack] = useState<PlayerBarTrack | null>(null);

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
    <main className="min-h-screen bg-void-black px-24 py-24 text-pure-white">
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
          <ReviewView session={session} onResolved={() => refreshSession(session.id)} />
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
      <div className="mt-24">
        <BookingWorkspace />
      </div>
      <div className="mt-24">
        <TrackTable onPlay={setPlayingTrack} />
      </div>
      <PlayerBar track={playingTrack} />
    </main>
  );
}
