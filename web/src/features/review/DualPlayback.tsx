import { useEffect, useRef, useState } from "react";

import { useSpotifyPlayer } from "../playback/useSpotifyPlayer";

interface DualPlaybackCandidate {
  rbContentId: string;
  artist: string;
  title: string;
}

interface DualPlaybackProps {
  spotifyTrackId: string | null;
  spotifyArtist: string;
  spotifyTitle: string;
  candidate: DualPlaybackCandidate | null;
  // Bumped by the parent every time the DJ presses space in the review
  // queue (FR-011's "space previews"): the queue owns the keyboard, so a
  // preview request arrives as a changing prop instead of an imperative
  // handle. Undefined/0 means "no preview requested yet".
  previewRequestId?: number;
}

type Source = "local" | "spotify";

// T040 (FR-013): hear both sides of a doubtful Match -- the local candidate
// via T038's Range-streaming endpoint, the Spotify original full-length via
// the Web Playback SDK (T099's short-lived player token, ADR 0009; the SDK
// connection itself is shared page-wide with the buy queue via
// useSpotifyPlayer, ADR 0022). Per spec.md's own fallback assumption
// ("without Premium the review flow degrades to local preview only" /
// "local preview plus opening the track in Spotify's own client"), any
// failure on the Spotify side -- no session, an expired session, a
// non-Premium account, or the SDK failing to connect -- degrades to a
// `spotify:track:` deep link instead of embedded playback, never a dead
// control or a silent crash.
export function DualPlayback({
  spotifyTrackId,
  spotifyArtist,
  spotifyTitle,
  candidate,
  previewRequestId,
}: DualPlaybackProps) {
  const audioRef = useRef<HTMLAudioElement>(null);

  const [activeSource, setActiveSource] = useState<Source | null>(null);
  const spotify = useSpotifyPlayer(spotifyTrackId !== null);
  const { deviceId, error: spotifyUnavailable, retry } = spotify;

  // A new queue item is an entirely new playback context: stale
  // playing/paused state from the PREVIOUS item must never leak into the
  // next one (review finding). The shared player's device connection
  // itself is NOT torn down here (ADR 0022 -- it stays alive for whichever
  // other consumer, review or buy queue, still needs it); `retry()` instead
  // gives this new item the same "fresh chance" a full reconnect used to
  // give implicitly, by clearing a stale failure from the previous item
  // without disconnecting the one shared device.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveSource(null);
    retry();
    // `retry` is stable (useCallback with no deps in useSpotifyPlayer), but
    // listing it keeps this honest about being a dependency.
  }, [spotifyTrackId, candidate?.rbContentId, retry]);

  async function pauseLocal() {
    audioRef.current?.pause();
  }

  async function pauseSpotify() {
    await spotify.pause();
  }

  async function playLocal() {
    await audioRef.current?.play();
    setActiveSource("local");
  }

  async function playSpotify() {
    if (!spotifyTrackId) return;
    const sent = await spotify.playTrack(spotifyTrackId);
    if (sent) setActiveSource("spotify");
  }

  // Single, shared toggle so local and Spotify playback can never both be
  // "active" at once: whichever source was previously playing is always
  // fully paused (awaited) before the new one starts (review finding: two
  // separately-written toggles had drifted into an async race that broke
  // this guarantee).
  async function toggle(source: Source) {
    const wasActive = activeSource === source;

    if (activeSource === "local") await pauseLocal();
    else if (activeSource === "spotify") await pauseSpotify();

    if (wasActive) {
      setActiveSource(null);
      return;
    }
    if (source === "local") await playLocal();
    else await playSpotify();
  }

  // Space in the review queue previews the LOCAL candidate (FR-011/US2
  // scenario 4) and toggles it off again on a second press -- the same
  // single-source-at-a-time path the buttons take.
  useEffect(() => {
    if (!previewRequestId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void toggle("local");
    // `toggle` is re-created on every render; depending on it would restart
    // playback on each render instead of on each new space press.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewRequestId]);

  return (
    <div className="flex flex-col gap-12" aria-label="Beide kanten beluisteren">
      <div className="flex items-center gap-12">
        <button
          type="button"
          disabled={!candidate}
          aria-pressed={activeSource === "local"}
          onClick={() => void toggle("local")}
          className="min-h-24 min-w-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
        >
          {activeSource === "local" ? "Pauzeer kandidaat" : "Speel kandidaat af"}
        </button>
        <span className="text-body-lg text-mist">
          {candidate ? `${candidate.artist} – ${candidate.title}` : "Geen kandidaat geselecteerd"}
        </span>
        {candidate && (
          <audio
            key={candidate.rbContentId}
            ref={audioRef}
            src={`/api/player/stream/${candidate.rbContentId}`}
            onPlay={() => setActiveSource("local")}
            onPause={() => setActiveSource((current) => (current === "local" ? null : current))}
            onEnded={() => setActiveSource((current) => (current === "local" ? null : current))}
          />
        )}
      </div>

      <div className="flex items-center gap-12">
        {spotifyUnavailable ? (
          <a
            href={spotifyTrackId ? `spotify:track:${spotifyTrackId}` : undefined}
            className="text-body-lg text-spotify-green underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
          >
            Open origineel in Spotify
          </a>
        ) : (
          <button
            type="button"
            disabled={!spotifyTrackId || !deviceId}
            aria-pressed={activeSource === "spotify"}
            onClick={() => void toggle("spotify")}
            className="min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green disabled:opacity-50"
          >
            {activeSource === "spotify" ? "Pauzeer origineel" : "Speel origineel af"}
          </button>
        )}
        <span className="text-body-lg text-mist">
          {spotifyArtist} – {spotifyTitle}
        </span>
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {activeSource === "local" && "Kandidaat speelt af"}
        {activeSource === "spotify" && "Spotify-origineel speelt af"}
        {activeSource === null && "Afspelen gepauzeerd"}
      </p>
    </div>
  );
}
