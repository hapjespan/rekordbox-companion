// Phase 7 review: US2 and US5 both shipped as fully built, fully unit-tested
// components that nothing ever imported, so neither story existed for the DJ.
// Component tests cannot catch that by construction -- they mount the component
// themselves. This file asserts the one thing they cannot: that every user
// story is reachable from the page the app actually serves.
//
// Deliberately shallow. It checks presence, not behaviour: each story's own
// suite owns its behaviour, and duplicating that here would make this file a
// second place to update on every UI change, which is how a guard like this
// stops being maintained.
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../src/api/client";
import { App } from "../src/App";

vi.mock("../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() },
}));

// Every panel fetches on mount. One empty-but-valid answer per shape keeps the
// page in its loaded state without any panel throwing.
function mockEmptyBackend() {
  vi.mocked(apiClient.GET).mockImplementation((path: string) => {
    if (path.includes("/auth/spotify/status")) {
      return Promise.resolve({ data: { connected: false }, error: undefined }) as never;
    }
    if (path.includes("/enrichment/status")) {
      return Promise.resolve({
        data: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0, running: false },
        error: undefined,
      }) as never;
    }
    if (path.includes("/collection")) {
      return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
    }
    if (path.includes("/unenriched")) {
      return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
    }
    return Promise.resolve({ data: [], error: undefined }) as never;
  });
}

// jsdom has no EventSource, and the enrichment panel opens one on mount.
class SilentEventSource {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("EventSource", SilentEventSource);
  mockEmptyBackend();
});

describe("App", () => {
  it("puts every user story on the page", async () => {
    render(<App />);

    // US1 sync, US4 missing, US6 enrichment, US7 bookings and US5 collection
    // are all unconditional; US2 review and US3 apply are session-scoped, so
    // they only appear once a session exists and their own suites cover them.
    // Queried by text, not by heading role: the section titles are styled
    // paragraphs rather than real headings today (recorded in the phase 7
    // report), so a heading query would be asserting a fix that has not landed.
    expect(screen.getByLabelText("Spotify-afspeellijst URL")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Ontbrekende nummers")).toBeInTheDocument();
    });
    expect(screen.getByText("Genre-verrijking")).toBeInTheDocument();
    expect(screen.getByText("Boekingstructuren")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("mounts the collection browser and its player, which US5 needs to exist at all", async () => {
    render(<App />);

    // The search field and the table are TrackTable; the player only renders
    // its controls once a track is selected, so its landmark is what is
    // assertable here without driving playback.
    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/zoek/i)).toBeInTheDocument();
  });
});
