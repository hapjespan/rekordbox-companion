// Shared Spotify Web Playback SDK player (ADR 0022).
//
// The SDK allows exactly one `Spotify.Player` per page: a second instance
// opens a second device and the two fight over which one Spotify actually
// sends audio to. Two features now need to play a Spotify track -- the
// Review Queue's DualPlayback (FR-013) and the buy queue (FR-041/ADR 0022)
// -- and neither may create its own player. This module owns the single
// instance behind a reference count: whichever consumer mounts first
// creates and connects it, whichever unmounts last disconnects it, and
// every consumer reads the same device/error state through one external
// store (`useSyncExternalStore`), so React re-renders every subscriber
// together on every SDK event instead of each holding its own copy that
// could drift.
//
// This intentionally does NOT reconnect the underlying player every time
// the caller's track id changes (DualPlayback used to tear down and rebuild
// the whole SDK connection per review item). With one page-wide player,
// that would mean the Review Queue silently killing the connection the buy
// queue is using, and vice versa. Instead the connection is established
// once per "someone needs it" and `playTrack` simply issues a fresh play
// request for whichever track id the caller passes -- the fresh-token-per-
// request guarantee (below) is unaffected either way.
//
// NOT VERIFIED HERE: this container has no Spotify Premium session and no
// audio output, so none of this has been confirmed to actually produce
// sound. What IS covered by useSpotifyPlayer.test.ts: the token fetch (and
// that it is never cached across calls), the ref-counted connect/disconnect
// lifecycle, the account_error/authentication_error/initialization_error ->
// shared-error wiring, and that a play request is rejected cleanly when no
// device is ready.
import { useCallback, useEffect, useSyncExternalStore } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";
import type { ApiError } from "../spotify-sync/types";

interface PlayerToken {
  access_token: string;
  expires_in: number;
}

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

// Loaded at most once per page: the SDK's own `onSpotifyWebPlaybackSDKReady`
// global only fires once anyway, and a second <script> tag would be wasted
// work regardless of how many consumers of this module exist.
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

// Never cached. The backend hands out the REMAINING lifetime of the
// upstream access token minus a 60s skew
// (engine/src/companion/integrations/spotify.py, _EXPIRY_SKEW), so a token
// fetched even a minute ago can already be useless. Every consumer -- the
// SDK's own getOAuthToken callback (which the SDK also calls on each
// renewal) and the Web API play request -- fetches a fresh one (phase 7
// finding on the review queue's original DualPlayback implementation).
async function requestPlayerToken(onError: (error: ApiError) => void): Promise<string | null> {
  try {
    const { data, error } = await apiClient.GET("/api/auth/spotify/player-token");
    if (error) {
      onError(asApiResponse<ApiError>(error));
      return null;
    }
    return asApiResponse<PlayerToken>(data).access_token;
  } catch {
    onError({
      code: "spotify_playback_unavailable",
      message: "Spotify-afspelen kon niet worden gestart.",
    });
    return null;
  }
}

interface PlayerSnapshot {
  deviceId: string | null;
  error: ApiError | null;
}

let snapshot: PlayerSnapshot = { deviceId: null, error: null };
const listeners = new Set<() => void>();
let playerInstance: SpotifyPlayerInstance | null = null;
let connecting: Promise<void> | null = null;
let refCount = 0;

function publish(next: Partial<PlayerSnapshot>) {
  snapshot = { ...snapshot, ...next };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): PlayerSnapshot {
  return snapshot;
}

function setError(error: ApiError) {
  publish({ error });
}

async function connectPlayer(): Promise<void> {
  const token = await requestPlayerToken(setError);
  if (token === null) return;

  const sdk = await loadSpotifySdk();
  // A consumer may have unmounted while the SDK script/token round-trip was
  // in flight; connecting a player nobody asked for anymore would leak a
  // device no one can ever release.
  if (refCount <= 0) return;

  const player = new sdk.Player({
    name: "Rekordbox Companion",
    getOAuthToken: (callback) => {
      // No token means the session is gone; requestPlayerToken has already
      // published the failure, so the callback is simply never invoked
      // rather than handing the SDK an empty string to choke on.
      void requestPlayerToken(setError).then((fresh) => {
        if (fresh !== null) callback(fresh);
      });
    },
  });
  player.addListener("ready", (payload) => {
    publish({ deviceId: (payload as SpotifyPlayerReadyPayload).device_id, error: null });
  });
  player.addListener("not_ready", () => publish({ deviceId: null }));
  player.addListener("account_error", () => {
    setError({
      code: "spotify_account_error",
      message: "Spotify Premium is vereist voor afspelen in de app.",
    });
  });
  // The SDK raises this when the token it was handed is rejected -- the
  // expiry case that used to die silently before the fresh-token-per-
  // callback fix. Same degradation as account_error.
  player.addListener("authentication_error", () => {
    setError({
      code: "spotify_authentication_error",
      message: "De Spotify-sessie is verlopen. Verbind opnieuw met Spotify.",
    });
  });
  player.addListener("initialization_error", () => {
    setError({
      code: "spotify_playback_unavailable",
      message: "Spotify-afspelen kon niet worden gestart in deze browser.",
    });
  });

  try {
    await player.connect();
    if (refCount <= 0) {
      // Every consumer released while connect() was pending.
      player.disconnect();
      return;
    }
    playerInstance = player;
  } catch {
    setError({
      code: "spotify_playback_unavailable",
      message: "Spotify-afspelen kon niet worden gestart.",
    });
  }
}

async function acquire(): Promise<void> {
  refCount += 1;
  if (!playerInstance && !connecting) {
    connecting = connectPlayer().finally(() => {
      connecting = null;
    });
  }
  if (connecting) await connecting;
}

function release(): void {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0 && playerInstance) {
    playerInstance.disconnect();
    playerInstance = null;
    publish({ deviceId: null, error: null });
  }
}

// Imperative pause on the shared device, usable by an orchestrator that
// isn't itself a mounted `useSpotifyPlayer` consumer -- the buy queue needs
// to pause the PREVIOUSLY active row's Spotify playback before switching a
// DIFFERENT row to a different source (a store preview, which is a
// completely separate `<audio>` element the shared device knows nothing
// about), and it needs to do so before flipping the state that starts the
// new source, not from inside the old row's own unmount/disable effect --
// that would race an in-flight `playTrack` for the new row against this
// pause landing on the same shared device. Switching from one Spotify track
// to ANOTHER one needs no such call: the Web API's play request already
// replaces whatever the device was playing.
export async function pauseSharedSpotifyPlayer(): Promise<void> {
  await playerInstance?.pause();
}

export interface UseSpotifyPlayerResult {
  /** Set once the SDK reports a ready device; playback is only possible once this is non-null. */
  deviceId: string | null;
  /** Set on any account/auth/init/network failure; callers fall back to the store preview while this is non-null (ADR 0022). */
  error: ApiError | null;
  /** Issues a fresh play request for the given Spotify track id on the shared device, with a freshly fetched token. Returns whether the request was sent. */
  playTrack: (spotifyTrackId: string) => Promise<boolean>;
  /** Pauses the shared player. */
  pause: () => Promise<void>;
  /**
   * Clears a previously reported error so the caller's UI offers the
   * Spotify control again on the next render. Mirrors DualPlayback's old
   * per-item "give it another try" behaviour (a new review item used to get
   * a fully fresh connection attempt) without tearing down the shared
   * connection: a transient authentication_error is often resolved by the
   * very next play attempt's fresh token, so callers invoke this when a new
   * playback context becomes active (a new review item, a newly visible
   * buy-queue row) rather than leaving a stale failure stuck forever.
   */
  retry: () => void;
}

/**
 * Connects to the shared Spotify Web Playback SDK player while `enabled`,
 * and releases it on unmount/disable. Safe to call from many components at
 * once (DualPlayback and every buy-queue row that carries a Spotify id):
 * only the first caller actually creates the SDK player, and it stays
 * connected until the last caller releases it.
 */
export function useSpotifyPlayer(enabled: boolean): UseSpotifyPlayerResult {
  const state = useSyncExternalStore(subscribe, getSnapshot);

  useEffect(() => {
    if (!enabled) return;
    void acquire();
    return () => release();
  }, [enabled]);

  const playTrack = useCallback(async (spotifyTrackId: string): Promise<boolean> => {
    if (!snapshot.deviceId) return false;
    const token = await requestPlayerToken(setError);
    if (token === null) return false;
    try {
      const response = await fetch(
        `https://api.spotify.com/v1/me/player/play?device_id=${snapshot.deviceId}`,
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
      return true;
    } catch {
      setError({
        code: "spotify_playback_unavailable",
        message: "Spotify-afspelen kon niet worden gestart.",
      });
      return false;
    }
  }, []);

  const pause = useCallback(async () => {
    await playerInstance?.pause();
  }, []);

  const retry = useCallback(() => {
    publish({ error: null });
  }, []);

  return { deviceId: state.deviceId, error: state.error, playTrack, pause, retry };
}
