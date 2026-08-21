// T040: DualPlayback (FR-013) -- local candidate via T038's stream endpoint,
// Spotify original via the Web Playback SDK using T099's player-token
// endpoint. Real device/DRM verification is the owner's Mac's job (ADR
// 0009); these tests cover the component's own logic: token fetch, SDK
// wiring, play/pause toggling, and the documented fallback (spec.md
// Assumptions: no Premium / no session -> local preview plus a
// `spotify:track:` deep link) when the Spotify side can't be reached.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { DualPlayback } from "../../../src/features/review/DualPlayback";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const CANDIDATE = { rbContentId: "rb-a", artist: "Daft Punk", title: "One More Time (Edit)" };

// openapi-fetch's real GET() return type carries a full `Response` alongside
// `data`/`error`; the mock only needs the two fields DualPlayback reads.
// One cast point here instead of one per call site (types.ts's
// `asApiResponse` precedent).
function mockPlayerToken(result: { data?: unknown; error?: unknown }) {
  vi.mocked(apiClient.GET).mockResolvedValue(result as never);
}

// The backend's `expires_in` is the REMAINING lifetime minus a 60s skew
// (engine/src/companion/integrations/spotify.py), so the token handed out at
// mount can be seconds from expiry while later calls return a fresh one.
// This helper makes those two differ, which is exactly what a component that
// caches the first token can never notice (review finding).
function mockRotatingPlayerToken(first: string, rest: string) {
  vi.mocked(apiClient.GET)
    .mockResolvedValueOnce({ data: { access_token: first, expires_in: 61 } } as never)
    .mockResolvedValue({ data: { access_token: rest, expires_in: 3600 } } as never);
}

class FakeSpotifyPlayer {
  static instances: FakeSpotifyPlayer[] = [];
  listeners: Record<string, ((payload: unknown) => void)[]> = {};
  connect = vi.fn().mockResolvedValue(true);
  disconnect = vi.fn();
  pause = vi.fn().mockResolvedValue(undefined);

  constructor(public options: { getOAuthToken: (cb: (token: string) => void) => void }) {
    FakeSpotifyPlayer.instances.push(this);
  }

  addListener(event: string, callback: (payload: unknown) => void) {
    (this.listeners[event] ??= []).push(callback);
  }

  emit(event: string, payload: unknown) {
    for (const cb of this.listeners[event] ?? []) cb(payload);
  }
}

function renderDualPlayback(overrides = {}) {
  return render(
    <DualPlayback
      spotifyTrackId="sp-track-1"
      spotifyArtist="Daft Punk"
      spotifyTitle="One More Time"
      candidate={CANDIDATE}
      {...overrides}
    />,
  );
}

beforeEach(() => {
  FakeSpotifyPlayer.instances = [];
  window.Spotify = { Player: FakeSpotifyPlayer as never };
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
});

afterEach(() => {
  delete window.Spotify;
  delete window.onSpotifyWebPlaybackSDKReady;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("DualPlayback", () => {
  it("renders the local candidate and the Spotify original as text (FR-013)", () => {
    mockPlayerToken({ data: undefined, error: { code: "pending" } });
    renderDualPlayback();

    expect(screen.getByText("Daft Punk – One More Time (Edit)")).toBeInTheDocument();
    expect(screen.getByText("Daft Punk – One More Time")).toBeInTheDocument();
  });

  it("toggling the local candidate button plays and pauses the audio element", () => {
    mockPlayerToken({ data: undefined, error: { code: "pending" } });
    renderDualPlayback();

    const button = screen.getByRole("button", { name: "Speel kandidaat af" });
    fireEvent.click(button);

    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1);
  });

  it("connects to the Web Playback SDK with the player token and enables Spotify playback once ready", async () => {
    mockPlayerToken({
      data: { access_token: "tok-123", expires_in: 3600 },
      error: undefined,
    });
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    const player = FakeSpotifyPlayer.instances[0];

    let capturedToken = "";
    player.options.getOAuthToken((token) => (capturedToken = token));
    // Asynchronous by design: the callback re-fetches the token instead of
    // replaying a cached one.
    await waitFor(() => expect(capturedToken).toBe("tok-123"));

    const spotifyButton = screen.getByRole("button", { name: "Speel origineel af" });
    expect(spotifyButton).toBeDisabled();

    player.emit("ready", { device_id: "device-1" });
    await waitFor(() => expect(spotifyButton).not.toBeDisabled());

    fireEvent.click(spotifyButton);
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "https://api.spotify.com/v1/me/player/play?device_id=device-1",
        expect.objectContaining({
          method: "PUT",
          headers: expect.objectContaining({ Authorization: "Bearer tok-123" }),
        }),
      ),
    );
  });

  it("re-fetches the player token on every SDK callback instead of replaying the mount-time one", async () => {
    mockRotatingPlayerToken("tok-expiring", "tok-fresh");
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    const player = FakeSpotifyPlayer.instances[0];

    let capturedToken = "";
    player.options.getOAuthToken((token) => (capturedToken = token));

    await waitFor(() => expect(capturedToken).toBe("tok-fresh"));
  });

  it("sends the play request with a freshly fetched token, not the mount-time one", async () => {
    mockRotatingPlayerToken("tok-expiring", "tok-fresh");
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("ready", { device_id: "device-1" });
    const spotifyButton = await screen.findByRole("button", { name: "Speel origineel af" });
    await waitFor(() => expect(spotifyButton).not.toBeDisabled());

    fireEvent.click(spotifyButton);

    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "https://api.spotify.com/v1/me/player/play?device_id=device-1",
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: "Bearer tok-fresh" }),
        }),
      ),
    );
  });

  it("falls back to a deep link when the SDK reports an authentication error (expired token)", async () => {
    mockPlayerToken({
      data: { access_token: "tok-123", expires_in: 61 },
      error: undefined,
    });
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("authentication_error", { message: "token expired" });

    expect(
      await screen.findByRole("link", { name: "Open origineel in Spotify" }),
    ).toBeInTheDocument();
  });

  it("previews the local candidate when the review queue reports a space press", async () => {
    mockPlayerToken({ data: undefined, error: { code: "pending" } });
    const { rerender } = render(
      <DualPlayback
        spotifyTrackId="sp-track-1"
        spotifyArtist="Daft Punk"
        spotifyTitle="One More Time"
        candidate={CANDIDATE}
        previewRequestId={0}
      />,
    );

    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();

    rerender(
      <DualPlayback
        spotifyTrackId="sp-track-1"
        spotifyArtist="Daft Punk"
        spotifyTitle="One More Time"
        candidate={CANDIDATE}
        previewRequestId={1}
      />,
    );

    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1));

    // A second press toggles the same side off again.
    rerender(
      <DualPlayback
        spotifyTrackId="sp-track-1"
        spotifyArtist="Daft Punk"
        spotifyTitle="One More Time"
        candidate={CANDIDATE}
        previewRequestId={2}
      />,
    );

    await waitFor(() => expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(1));
  });

  it("falls back to a spotify:track: deep link when the player token cannot be fetched", async () => {
    mockPlayerToken({
      data: undefined,
      error: { code: "spotify_not_connected", message: "not connected" },
    });
    renderDualPlayback();

    const link = await screen.findByRole("link", { name: "Open origineel in Spotify" });
    expect(link).toHaveAttribute("href", "spotify:track:sp-track-1");
    expect(screen.queryByRole("button", { name: /origineel/i })).not.toBeInTheDocument();
  });

  it("falls back to a deep link when the SDK reports an account error (no Premium)", async () => {
    mockPlayerToken({
      data: { access_token: "tok-123", expires_in: 3600 },
      error: undefined,
    });
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("account_error", { message: "no premium" });

    expect(
      await screen.findByRole("link", { name: "Open origineel in Spotify" }),
    ).toBeInTheDocument();
  });

  it("falls back to a deep link when the SDK reports an initialization error", async () => {
    mockPlayerToken({
      data: { access_token: "tok-123", expires_in: 3600 },
      error: undefined,
    });
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("initialization_error", { message: "no EME" });

    expect(
      await screen.findByRole("link", { name: "Open origineel in Spotify" }),
    ).toBeInTheDocument();
  });

  it("awaits pausing Spotify before starting local playback, and vice versa (mutual exclusion)", async () => {
    mockPlayerToken({
      data: { access_token: "tok-123", expires_in: 3600 },
      error: undefined,
    });
    renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    const player = FakeSpotifyPlayer.instances[0];
    player.emit("ready", { device_id: "device-1" });
    const spotifyButton = await screen.findByRole("button", { name: "Speel origineel af" });
    await waitFor(() => expect(spotifyButton).not.toBeDisabled());

    // Start Spotify playback first.
    fireEvent.click(spotifyButton);
    await waitFor(() => expect(spotifyButton).toHaveTextContent("Pauzeer origineel"));

    // Switching to local must pause Spotify (awaited) before local starts.
    const localButton = screen.getByRole("button", { name: "Speel kandidaat af" });
    fireEvent.click(localButton);

    await waitFor(() => expect(player.pause).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Kandidaat speelt af"),
    );
  });

  it("disconnects the Spotify player on unmount", async () => {
    mockPlayerToken({
      data: { access_token: "tok-123", expires_in: 3600 },
      error: undefined,
    });
    const { unmount } = renderDualPlayback();

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    unmount();

    expect(FakeSpotifyPlayer.instances[0].disconnect).toHaveBeenCalledTimes(1);
  });

  it("exposes the currently playing side to assistive tech via a live status region", () => {
    mockPlayerToken({ data: undefined, error: { code: "pending" } });
    const { container } = renderDualPlayback();

    expect(screen.getByRole("status")).toHaveTextContent("Afspelen gepauzeerd");

    const audio = container.querySelector("audio") as HTMLAudioElement;
    fireEvent.play(audio);

    expect(screen.getByRole("status")).toHaveTextContent("Kandidaat speelt af");
  });
});
