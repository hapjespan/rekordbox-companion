// ADR 0022: the shared Spotify Web Playback SDK player used by both
// DualPlayback (Review Queue) and the buy queue. These tests cover the
// hook's own logic -- token fetch (never cached), the ref-counted
// connect/disconnect lifecycle that keeps a page-wide single player, and
// the account_error/authentication_error/initialization_error -> shared
// error wiring. Real device/Premium/audio verification is the owner's
// Mac's job (this container has neither).
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { useSpotifyPlayer } from "../../../src/features/playback/useSpotifyPlayer";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

function mockPlayerToken(result: { data?: unknown; error?: unknown }) {
  vi.mocked(apiClient.GET).mockResolvedValue(result as never);
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

beforeEach(() => {
  FakeSpotifyPlayer.instances = [];
  window.Spotify = { Player: FakeSpotifyPlayer as never };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
});

afterEach(() => {
  delete window.Spotify;
  delete window.onSpotifyWebPlaybackSDKReady;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("useSpotifyPlayer", () => {
  it("creates exactly one SDK player even when two consumers enable at once (ADR 0022: one player per page)", async () => {
    mockPlayerToken({ data: { access_token: "tok-123", expires_in: 3600 }, error: undefined });

    const a = renderHook(() => useSpotifyPlayer(true));
    const b = renderHook(() => useSpotifyPlayer(true));

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));

    a.unmount();
    b.unmount();

    expect(FakeSpotifyPlayer.instances[0].disconnect).toHaveBeenCalledTimes(1);
  });

  it("keeps the shared player connected while at least one consumer is still mounted", async () => {
    mockPlayerToken({ data: { access_token: "tok-123", expires_in: 3600 }, error: undefined });

    const a = renderHook(() => useSpotifyPlayer(true));
    const b = renderHook(() => useSpotifyPlayer(true));
    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));

    a.unmount();
    expect(FakeSpotifyPlayer.instances[0].disconnect).not.toHaveBeenCalled();

    b.unmount();
    expect(FakeSpotifyPlayer.instances[0].disconnect).toHaveBeenCalledTimes(1);
  });

  it("re-fetches the player token on every SDK callback rather than replaying the first one", async () => {
    vi.mocked(apiClient.GET)
      .mockResolvedValueOnce({ data: { access_token: "tok-expiring", expires_in: 61 } } as never)
      .mockResolvedValue({ data: { access_token: "tok-fresh", expires_in: 3600 } } as never);

    const { result } = renderHook(() => useSpotifyPlayer(true));
    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));

    let captured = "";
    FakeSpotifyPlayer.instances[0].options.getOAuthToken((token) => (captured = token));
    await waitFor(() => expect(captured).toBe("tok-fresh"));

    FakeSpotifyPlayer.instances[0].emit("ready", { device_id: "device-1" });
    await waitFor(() => expect(result.current.deviceId).toBe("device-1"));

    await act(async () => {
      await result.current.playTrack("sp-track-1");
    });
    expect(fetch).toHaveBeenCalledWith(
      "https://api.spotify.com/v1/me/player/play?device_id=device-1",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok-fresh" }),
      }),
    );
  });

  it("reports an account_error from the SDK as the shared error", async () => {
    mockPlayerToken({ data: { access_token: "tok-123", expires_in: 3600 }, error: undefined });
    const { result } = renderHook(() => useSpotifyPlayer(true));

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("account_error", { message: "no premium" });

    await waitFor(() => expect(result.current.error?.code).toBe("spotify_account_error"));
  });

  it("reports an authentication_error from the SDK as the shared error", async () => {
    mockPlayerToken({ data: { access_token: "tok-123", expires_in: 3600 }, error: undefined });
    const { result } = renderHook(() => useSpotifyPlayer(true));

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("authentication_error", { message: "expired" });

    await waitFor(() => expect(result.current.error?.code).toBe("spotify_authentication_error"));
  });

  it("refuses to play when no device is ready yet", async () => {
    mockPlayerToken({ data: undefined, error: { code: "pending" } });
    const { result } = renderHook(() => useSpotifyPlayer(true));

    const sent = await result.current.playTrack("sp-track-1");
    expect(sent).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("retry() clears a previously reported error", async () => {
    mockPlayerToken({ data: { access_token: "tok-123", expires_in: 3600 }, error: undefined });
    const { result } = renderHook(() => useSpotifyPlayer(true));

    await waitFor(() => expect(FakeSpotifyPlayer.instances).toHaveLength(1));
    FakeSpotifyPlayer.instances[0].emit("account_error", { message: "no premium" });
    await waitFor(() => expect(result.current.error).not.toBeNull());

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.error).toBeNull());
  });

  it("does not connect at all while disabled", async () => {
    mockPlayerToken({ data: { access_token: "tok-123", expires_in: 3600 }, error: undefined });
    renderHook(() => useSpotifyPlayer(false));

    // Give any accidental async connect a tick to run.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(FakeSpotifyPlayer.instances).toHaveLength(0);
  });
});
