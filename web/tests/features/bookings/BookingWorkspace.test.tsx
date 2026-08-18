// T088: profile editor, suggestion list (accept/dismiss, already-in-
// playlist flag), apply action and result state, naming-error inputs (WCAG).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { BookingWorkspace } from "../../../src/features/bookings/BookingWorkspace";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() },
}));

const STRUCTURE = {
  id: 1,
  name: "Bruiloft Jansen",
  booking_profile_id: null,
  created_at: "2026-08-18T00:00:00",
  last_applied_at: null,
};

const PROFILE = {
  id: 1,
  name: "Bruiloft",
  slug: "bruiloft",
  bpm_min: null,
  bpm_max: null,
  genre_tags: [],
};

const PLAYLIST_NODE = {
  id: 2,
  structure_id: 1,
  parent_id: null,
  kind: "playlist",
  name: "Ontvangst",
  position: 0,
  set_phase: null,
  rb_ref: null,
};

const SUGGESTION = {
  rb_content_id: "1",
  artist: "Daft Punk",
  title: "One More Time",
  bpm: 123.0,
  play_count: 50,
  already_in_playlist: false,
};

function mockGet(routes: Record<string, unknown>) {
  vi.mocked(apiClient.GET).mockImplementation(((path: string) => {
    for (const [pattern, data] of Object.entries(routes)) {
      if (path === pattern) return Promise.resolve({ data, error: undefined });
    }
    return Promise.resolve({ data: undefined, error: undefined });
  }) as never);
}

beforeEach(() => {
  mockGet({
    "/api/structures": [STRUCTURE],
    "/api/profiles": [PROFILE],
    "/api/structures/{structure_id}/nodes": [PLAYLIST_NODE],
    "/api/structures/{structure_id}/nodes/{node_id}/suggestions": [SUGGESTION],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("BookingWorkspace", () => {
  it("lists existing structures", async () => {
    render(<BookingWorkspace />);

    expect(await screen.findByText("Bruiloft Jansen")).toBeInTheDocument();
  });

  it("shows a naming error when creating a structure without a name", async () => {
    render(<BookingWorkspace />);
    await screen.findByText("Bruiloft Jansen");

    fireEvent.click(screen.getByRole("button", { name: "Structuur aanmaken" }));

    expect(await screen.findByText("Vul een naam in.")).toBeInTheDocument();
    expect(apiClient.POST).not.toHaveBeenCalledWith("/api/structures", expect.anything());
  });

  it("creates a profile with genre tags", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        id: 2,
        name: "Zomerfeest",
        slug: "zomerfeest",
        bpm_min: 120,
        bpm_max: 128,
        genre_tags: ["house"],
      },
      error: undefined,
    } as never);
    render(<BookingWorkspace />);
    await screen.findByText("Bruiloft Jansen");

    fireEvent.change(screen.getByLabelText("Naam nieuw profiel"), {
      target: { value: "Zomerfeest" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Profiel aanmaken" }));

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/profiles",
        expect.objectContaining({ body: expect.objectContaining({ name: "Zomerfeest" }) }),
      );
    });
  });

  it("shows suggestions for the selected playlist, flagging already-in-playlist in text", async () => {
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    fireEvent.click(await screen.findByRole("button", { name: "Selecteer Ontvangst" }));

    expect(await screen.findByText("Daft Punk – One More Time")).toBeInTheDocument();
    expect(screen.getByText("Al in de playlist: nee")).toBeInTheDocument();
  });

  it("accepts a suggestion into the playlist", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { added: true },
      error: undefined,
    } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    fireEvent.click(await screen.findByRole("button", { name: "Selecteer Ontvangst" }));
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(screen.getByRole("button", { name: "Accepteren: Daft Punk – One More Time" }));

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/structures/{structure_id}/nodes/{node_id}/tracks",
        expect.objectContaining({
          params: { path: { structure_id: 1, node_id: 2 } },
          body: { rb_content_id: "1", origin: "suggestion" },
        }),
      );
    });
  });

  it("dismisses a suggestion", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { dismissed: true },
      error: undefined,
    } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    fireEvent.click(await screen.findByRole("button", { name: "Selecteer Ontvangst" }));
    await screen.findByText("Daft Punk – One More Time");

    fireEvent.click(screen.getByRole("button", { name: "Afwijzen: Daft Punk – One More Time" }));

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/structures/{structure_id}/nodes/{node_id}/dismissals",
        expect.objectContaining({
          params: { path: { structure_id: 1, node_id: 2 } },
          body: { rb_content_id: "1" },
        }),
      );
    });
  });

  it("applies the structure and shows the per-node result", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        nodes: [
          {
            node_id: 2,
            rb_ref: "rb-1",
            created: true,
            tracks_added: 1,
            tracks_already_present: 0,
            readback_ok: true,
          },
        ],
        backup_path: "/backups/master-1.db.zip",
        readback_ok: true,
      },
      error: undefined,
    } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.click(await screen.findByRole("button", { name: "Toepassen" }));

    expect(await screen.findByText("Toegepast: 1 nummer(s) toegevoegd.")).toBeInTheDocument();
  });

  it("shows the guard refusal message when apply is blocked", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "rekordbox_running", message: "Sluit Rekordbox af en probeer opnieuw." },
    } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.click(await screen.findByRole("button", { name: "Toepassen" }));

    expect(await screen.findByText("Sluit Rekordbox af en probeer opnieuw.")).toBeInTheDocument();
  });

  it("sequences a two-part move so the two PUT requests never race", async () => {
    // Regression: Tree's "move up" fires two independent onMove calls (a
    // position swap); each triggers its own PUT + refetch. Without
    // sequencing, the second PUT could fire before the first's refetch
    // lands, and whichever finishes last could silently drop the other's
    // change from the rendered tree.
    const SECOND_NODE = { ...PLAYLIST_NODE, id: 3, name: "Tweede", position: 1 };
    mockGet({
      "/api/structures": [STRUCTURE],
      "/api/profiles": [PROFILE],
      "/api/structures/{structure_id}/nodes": [PLAYLIST_NODE, SECOND_NODE],
    });
    let putCount = 0;
    const resolvers: (() => void)[] = [];
    vi.mocked(apiClient.PUT).mockImplementation(
      () =>
        new Promise((resolve) => {
          putCount += 1;
          resolvers.push(() => resolve({ data: {}, error: undefined } as never));
        }) as never,
    );
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    await screen.findByRole("button", { name: "Selecteer Tweede" });

    fireEvent.click(screen.getByRole("button", { name: "Verplaats omhoog: Tweede" }));

    // Only the first mutation's PUT may have fired yet.
    await waitFor(() => expect(putCount).toBe(1));
    resolvers[0]();

    // The second only fires once the first's full PUT-then-refetch cycle
    // has completed, never concurrently.
    await waitFor(() => expect(putCount).toBe(2));
  });
});
