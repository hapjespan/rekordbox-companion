import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import { KeymapOverlay } from "../../components/KeymapOverlay";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError, SyncSessionDetail, SyncTrack } from "../spotify-sync/types";
import { DualPlayback } from "./DualPlayback";
import { QueueComplete } from "./QueueComplete";
import { ReviewQueue } from "./ReviewQueue";

interface ReviewViewProps {
  // Fed from App.tsx's GET /api/sync/sessions/{id} rather than fetching the
  // same detail a second time: the session's `review` tracks, its totals
  // (QueueComplete) and MatchReport's numbers all have to agree, and one
  // fetch owner is the only way they stay in step.
  session: SyncSessionDetail;
  // Re-fetches the session after a resolution, so the queue shrinks and the
  // totals update from the backend's own numbers instead of a local guess.
  onResolved: () => Promise<void> | void;
}

// Same code-keyed-switch convention as PlaylistUrlForm/MissingQueue: Dutch
// text for the codes this endpoint documents, the raw backend message only
// as a last resort.
function resolutionErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "sync_track_not_found":
      return "Dit nummer bestaat niet meer in deze synchronisatie.";
    case "not_in_review":
      return "Dit nummer is al beoordeeld.";
    case "missing_field":
      return "Kies eerst een kandidaat met de pijltoetsen.";
    default:
      return error.message || "Kon de beoordeling niet opslaan. Probeer het opnieuw.";
  }
}

// T108 (phase 7 finding): the US2 review flow, assembled and reachable.
// ReviewQueue (T039) owns the keyboard and the focus, KeymapOverlay (T100)
// makes the key map discoverable from the screen, DualPlayback (T040) plays
// whichever side the selection points at, and QueueComplete (T041) closes
// the session -- none of which was mounted anywhere before, leaving US2's
// independent test and its WCAG criteria unreachable in the running app.
export function ReviewView({ session, onResolved }: ReviewViewProps) {
  const [activeSyncTrackId, setActiveSyncTrackId] = useState<number | null>(null);
  const [activeRbContentId, setActiveRbContentId] = useState<string | null>(null);
  const [previewRequestId, setPreviewRequestId] = useState(0);
  const [resolvedCount, setResolvedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // A different session is a different queue: whatever this one resolved
  // must not make the next session look finished (see `showComplete`).
  useEffect(() => {
    setResolvedCount(0);
    setError(null);
  }, [session.id]);

  // Stable by construction -- ReviewQueue keeps it as an effect dependency.
  const handleActiveChange = useCallback(
    (syncTrackId: number | null, rbContentId: string | null) => {
      setActiveSyncTrackId(syncTrackId);
      setActiveRbContentId(rbContentId);
    },
    [],
  );

  const reviewTracks = session.tracks.filter((track) => track.status === "review");
  const items = reviewTracks.map((track) => ({
    sync_track_id: track.id,
    spotify_artist: track.artist,
    spotify_title: track.title,
    // Backend scores are floats (rapidfuzz), the queue shows whole numbers.
    candidates: track.candidates.map((candidate) => ({
      rb_content_id: candidate.rb_content_id,
      score: Math.round(candidate.score),
    })),
  }));

  // Falls back to the first item so both playback sides are usable from the
  // moment the queue renders, before any key has been pressed (which is
  // also the state ReviewQueue itself starts in).
  const activeTrack: SyncTrack | undefined =
    reviewTracks.find((track) => track.id === activeSyncTrackId) ?? reviewTracks[0];
  const candidateRbContentId =
    (activeSyncTrackId === activeTrack?.id ? activeRbContentId : null) ??
    activeTrack?.candidates[0]?.rb_content_id ??
    null;

  // spec.md US2 scenario 6 is specifically about the LAST item being
  // resolved, so the completion state needs a resolution to have happened
  // here -- a session that never had doubtful matches is not a finished
  // review queue.
  const showComplete = items.length === 0 && resolvedCount > 0;

  async function resolve(action: () => Promise<{ error?: unknown }>) {
    try {
      const { error: apiError } = await action();
      if (apiError) {
        setError(resolutionErrorMessageFor(asApiResponse<ApiError>(apiError)));
        return;
      }
    } catch {
      setError("De Companion-server is niet bereikbaar. Probeer het opnieuw.");
      return;
    }
    setError(null);
    setResolvedCount((count) => count + 1);
    await onResolved();
  }

  async function handleAccept(syncTrackId: number, rbContentId: string) {
    await resolve(() =>
      apiClient.POST("/api/sync/sessions/{session_id}/tracks/{track_id}/accept", {
        params: { path: { session_id: session.id, track_id: syncTrackId } },
        body: { rb_content_id: rbContentId },
      }),
    );
  }

  async function handleReject(syncTrackId: number) {
    await resolve(() =>
      apiClient.POST("/api/sync/sessions/{session_id}/tracks/{track_id}/reject", {
        params: { path: { session_id: session.id, track_id: syncTrackId } },
      }),
    );
  }

  return (
    <div className="flex flex-col gap-16">
      <h2 className="text-heading font-bold">Controleren</h2>

      {showComplete ? (
        <QueueComplete totals={session.totals} />
      ) : items.length === 0 ? (
        <p className="text-body-lg text-mist">
          Geen nummers om te controleren in deze synchronisatie.
        </p>
      ) : (
        <>
          <KeymapOverlay />
          <ReviewQueue
            items={items}
            onAccept={(syncTrackId, rbContentId) => void handleAccept(syncTrackId, rbContentId)}
            onReject={(syncTrackId) => void handleReject(syncTrackId)}
            onPreview={() => setPreviewRequestId((id) => id + 1)}
            onActiveChange={handleActiveChange}
          />
          {activeTrack && (
            <DualPlayback
              spotifyTrackId={activeTrack.spotify_track_id}
              spotifyArtist={activeTrack.artist}
              spotifyTitle={activeTrack.title}
              candidate={
                candidateRbContentId
                  ? {
                      rbContentId: candidateRbContentId,
                      // The API's candidate rows carry no artist/title (see
                      // ReviewQueue's ReviewCandidate), so the local side is
                      // named by the Rekordbox id the DJ can look up.
                      artist: "Kandidaat",
                      title: `Rekordbox-id ${candidateRbContentId}`,
                    }
                  : null
              }
              previewRequestId={previewRequestId}
            />
          )}
        </>
      )}

      {error && (
        <p role="alert" className="text-body-lg font-semibold text-pure-white">
          {error}
        </p>
      )}
    </div>
  );
}
