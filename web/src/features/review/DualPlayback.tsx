import { useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";

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
}

interface PlayerToken {
  access_token: string;
  expires_in: number;
}

type Source = "local" | "spotify";

interface SpotifyPlayerReadyPayload {
  device_id: string;
}

interface SpotifyPlayerInstance {
  connect: () => Promise<boolean>;
  disconnect: () => void;
  pause: () => Promise<void>;
  addListener: (
    event: "ready" | "not_ready" | "account_error" | "initialization_error",
    callback: (payload: SpotifyPlayerReadyPayload | { message: string }) => void,
  ) => void;
}

interface SpotifySdk {
  Player: new (options: {
    name: string;
    getOAuthToken: (callback: (token: string) => void) => void;
    volume?: number;
  }) => SpotifyPlayerInstance;
}

declare global {
  interface Window {
    Spotify?: SpotifySdk;
    onSpotifyWebPlaybackSDKReady?: () => void;
  }
}

const SDK_SRC = "https://sdk.scdn.co/spotify-player.js";

// Loaded at most once per page, regardless of how many DualPlayback
// instances mount (the review queue only ever shows one at a time, but a
// second script tag would still be wasteful and the SDK singleton-style
// `onSpotifyWebPlaybackSDKReady` global only fires once anyway).
let sdkLoadPromise: Promise<SpotifySdk> | null = null;

function loadSpotifySdk(): Promise<SpotifySdk> {
  if (window.Spotify) return Promise.resolve(window.Spotify);
  if (!sdkLoadPromise) {
    sdkLoadPromise = new Promise((resolve) => {
      window.onSpotifyWebPlaybackSDKReady = () => resolve(window.Spotify as SpotifySdk);
      const script = document.createElement("script");
      script.src = SDK_SRC;
      script.async = true;
      document.head.appendChild(script);
    });
  }
  return sdkLoadPromise;
}

// T040 (FR-013): hear both sides of a doubtful Match -- the local candidate
// via T038's Range-streaming endpoint, the Spotify original full-length via
// the Web Playback SDK (T099's short-lived player token, ADR 0009). Per
// spec.md's own fallback assumption ("without Premium the review flow
// degrades to local preview only" / "local preview plus opening the track
// in Spotify's own client"), any failure on the Spotify side -- no session,
// an expired session, a non-Premium account, or the SDK failing to connect
// -- degrades to a `spotify:track:` deep link instead of embedded playback,
// never a dead control or a silent crash.
export function DualPlayback({
  spotifyTrackId,
  spotifyArtist,
  spotifyTitle,
  candidate,
}: DualPlaybackProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const playerRef = useRef<SpotifyPlayerInstance | null>(null);
  const tokenRef = useRef<string | null>(null);

  const [activeSource, setActiveSource] = useState<Source | null>(null);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [spotifyUnavailable, setSpotifyUnavailable] = useState<ApiError | null>(null);

  // A new queue item is an entirely new playback context: stale
  // playing/paused state, a stale device, or a stale failure from the
  // PREVIOUS item must never leak into the next one (review finding).
  useEffect(() => {
    setActiveSource(null);
    setDeviceId(null);
    setSpotifyUnavailable(null);
  }, [spotifyTrackId, candidate?.rbContentId]);

  useEffect(() => {
    if (!spotifyTrackId) return;
    let cancelled = false;

    function fail(error: ApiError) {
      if (cancelled) return;
      setSpotifyUnavailable(error);
    }

    async function connect() {
      try {
        const { data, error } = await apiClient.GET("/api/auth/spotify/player-token");
        if (cancelled) return;
        if (error) {
          fail(asApiResponse<ApiError>(error));
          return;
        }
        const token = asApiResponse<PlayerToken>(data);
        tokenRef.current = token.access_token;

        const sdk = await loadSpotifySdk();
        if (cancelled) return;

        const player = new sdk.Player({
          name: "Rekordbox Companion",
          getOAuthToken: (callback) => callback(tokenRef.current ?? ""),
        });
        player.addListener("ready", (payload) => {
          if (cancelled) return;
          setDeviceId((payload as SpotifyPlayerReadyPayload).device_id);
        });
        player.addListener("not_ready", () => {
          if (cancelled) return;
          setDeviceId(null);
        });
        player.addListener("account_error", () => {
          fail({
            code: "spotify_account_error",
            message: "Spotify Premium is vereist voor afspelen in de app.",
          });
        });
        player.addListener("initialization_error", () => {
          fail({
            code: "spotify_playback_unavailable",
            message: "Spotify-afspelen kon niet worden gestart in deze browser.",
          });
        });
        playerRef.current = player;
        await player.connect();
      } catch {
        // Network failure reaching our backend, the SDK's CDN, or Spotify's
        // own connect() rejecting -- all fall back the same way as a
        // documented error response (spec.md: local preview plus a
        // spotify:track: deep link), never an unhandled rejection.
        fail({
          code: "spotify_playback_unavailable",
          message: "Spotify-afspelen kon niet worden gestart.",
        });
      }
    }

    void connect();

    return () => {
      cancelled = true;
      playerRef.current?.disconnect();
      playerRef.current = null;
    };
  }, [spotifyTrackId]);

  async function pauseLocal() {
    audioRef.current?.pause();
  }

  async function pauseSpotify() {
    await playerRef.current?.pause();
  }

  async function playLocal() {
    await audioRef.current?.play();
    setActiveSource("local");
  }

  async function playSpotify() {
    if (!deviceId || !tokenRef.current || !spotifyTrackId) return;
    try {
      const response = await fetch(
        `https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`,
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${tokenRef.current}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ uris: [`spotify:track:${spotifyTrackId}`] }),
        },
      );
      if (!response.ok) throw new Error(`Spotify play request failed: ${response.status}`);
      setActiveSource("spotify");
    } catch {
      setSpotifyUnavailable({
        code: "spotify_playback_unavailable",
        message: "Spotify-afspelen kon niet worden gestart.",
      });
    }
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
