import { useCallback, useEffect, useRef, useState } from "react";

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
  // Bumped by the parent every time the DJ presses space in the review
  // queue (FR-011's "space previews"): the queue owns the keyboard, so a
  // preview request arrives as a changing prop instead of an imperative
  // handle. Undefined/0 means "no preview requested yet".
  previewRequestId?: number;
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
    event:
      "ready" | "not_ready" | "account_error" | "authentication_error" | "initialization_error",
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
  previewRequestId,
}: DualPlaybackProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const playerRef = useRef<SpotifyPlayerInstance | null>(null);

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

  // Never cache the player token. The backend hands out the REMAINING
  // lifetime of the upstream access token minus a 60s skew
  // (engine/src/companion/integrations/spotify.py, _EXPIRY_SKEW), so a token
  // fetched at mount can be ~61 seconds from useless -- far shorter than a
  // review session. Every consumer (the SDK's own getOAuthToken callback,
  // which the SDK also calls on each renewal, and the Web API play request)
  // therefore fetches a fresh one, and a failure degrades exactly like the
  // documented fallbacks: local preview plus a `spotify:track:` deep link
  // (review finding).
  const requestPlayerToken = useCallback(async (): Promise<string | null> => {
    try {
      const { data, error } = await apiClient.GET("/api/auth/spotify/player-token");
      if (error) {
        setSpotifyUnavailable(asApiResponse<ApiError>(error));
        return null;
      }
      return asApiResponse<PlayerToken>(data).access_token;
    } catch {
      setSpotifyUnavailable({
        code: "spotify_playback_unavailable",
        message: "Spotify-afspelen kon niet worden gestart.",
      });
      return null;
    }
  }, []);

  useEffect(() => {
    if (!spotifyTrackId) return;
    let cancelled = false;

    function fail(error: ApiError) {
      if (cancelled) return;
      setSpotifyUnavailable(error);
    }

    async function connect() {
      try {
        // Fetched up front purely to establish that a usable Spotify session
        // exists at all: without one there is nothing to connect and the
        // component degrades to the deep link right away.
        const token = await requestPlayerToken();
        if (cancelled || token === null) return;

        const sdk = await loadSpotifySdk();
        if (cancelled) return;

        const player = new sdk.Player({
          name: "Rekordbox Companion",
          getOAuthToken: (callback) => {
            // No token means the session is gone; `requestPlayerToken` has
            // already switched this component to the deep-link fallback, so
            // the callback is simply never invoked rather than handing the
            // SDK an empty string to choke on.
            void requestPlayerToken().then((fresh) => {
              if (fresh !== null) callback(fresh);
            });
          },
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
        // The SDK raises this when the token it was handed is rejected --
        // the expiry case the review flow used to die silently on. Same
        // degradation as account_error: the DJ keeps local preview and gets
        // the deep link, and the message names the fix.
        player.addListener("authentication_error", () => {
          fail({
            code: "spotify_authentication_error",
            message: "De Spotify-sessie is verlopen. Verbind opnieuw met Spotify.",
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
  }, [spotifyTrackId, requestPlayerToken]);

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
    if (!deviceId || !spotifyTrackId) return;
    // A fresh token per request, for the same expiry reason as above: this
    // PUT can happen many minutes into a review session.
    const token = await requestPlayerToken();
    if (token === null) return;
    try {
      const response = await fetch(
        `https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`,
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
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

  // Space in the review queue previews the LOCAL candidate (FR-011/US2
  // scenario 4) and toggles it off again on a second press -- the same
  // single-source-at-a-time path the buttons take.
  useEffect(() => {
    if (!previewRequestId) return;
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
