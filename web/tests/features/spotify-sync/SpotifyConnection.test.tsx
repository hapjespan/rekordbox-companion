// Phase 7 finding: SpotifyConnection destructured only `data`, so any fetch
// failure left `status` as `undefined` -- past the `status === null` loading
// guard and straight into a crash on `status.connected`, taking down the whole
// page in exactly the degraded-backend state T105 requires to be survivable.
// These tests cover both failure shapes openapi-fetch can produce (an HTTP
// error response, and a rejected call) alongside the happy paths.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { SpotifyConnection } from "../../../src/features/spotify-sync/SpotifyConnection";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

// One cast point for the mocked responses: openapi-fetch's real return type
// carries a full `Response` the component never reads (types.ts's
// `asApiResponse` precedent).
function mockStatus(result: { data?: unknown; error?: unknown }) {
  vi.mocked(apiClient.GET).mockResolvedValue(result as never);
}

beforeEach(() => {
  vi.mocked(apiClient.GET).mockReset();
  vi.mocked(apiClient.POST).mockReset();
  vi.mocked(apiClient.POST).mockResolvedValue({ data: {} } as never);
});

describe("SpotifyConnection", () => {
  it("renders the connected account and its product", async () => {
    mockStatus({ data: { connected: true, display_name: "DJ Test", product: "premium" } });
    render(<SpotifyConnection />);

    expect(await screen.findByText("DJ Test")).toBeInTheDocument();
    expect(screen.getByText(/Premium/)).toBeInTheDocument();
  });

  it("offers the connect link when no account is connected", async () => {
    mockStatus({ data: { connected: false, display_name: null, product: null } });
    render(<SpotifyConnection />);

    const link = await screen.findByRole("link", { name: "Verbinden met Spotify" });
    expect(link).toHaveAttribute("href", "/api/auth/spotify/login");
  });

  it("survives an error response from the status endpoint with a Dutch failure message", async () => {
    mockStatus({ data: undefined, error: { code: "internal_error", message: "boom" } });
    render(<SpotifyConnection />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "De Spotify-status kon niet worden opgehaald.",
    );
    // Never the crash-adjacent states: no loading text left hanging, no
    // connect/disconnect controls implying a known status.
    expect(screen.queryByText("Spotify-status laden…")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Verbinden met Spotify" })).not.toBeInTheDocument();
  });

  it("survives a network-level failure the same way", async () => {
    vi.mocked(apiClient.GET).mockRejectedValue(new Error("network down"));
    render(<SpotifyConnection />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "De Spotify-status kon niet worden opgehaald.",
    );
  });

  it("retries the status fetch and recovers once the backend answers", async () => {
    vi.mocked(apiClient.GET)
      .mockResolvedValueOnce({ data: undefined, error: { code: "internal_error" } } as never)
      .mockResolvedValue({
        data: { connected: true, display_name: "DJ Test", product: "premium" },
      } as never);
    render(<SpotifyConnection />);

    fireEvent.click(await screen.findByRole("button", { name: "Opnieuw proberen" }));

    expect(await screen.findByText("DJ Test")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disconnects and refreshes the status (the AVG deletion path)", async () => {
    vi.mocked(apiClient.GET)
      .mockResolvedValueOnce({
        data: { connected: true, display_name: "DJ Test", product: "premium" },
      } as never)
      .mockResolvedValue({
        data: { connected: false, display_name: null, product: null },
      } as never);
    render(<SpotifyConnection />);

    fireEvent.click(await screen.findByRole("button", { name: "Verbinding verbreken" }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith("/api/auth/spotify/disconnect"),
    );
    expect(await screen.findByRole("link", { name: "Verbinden met Spotify" })).toBeInTheDocument();
  });
});
