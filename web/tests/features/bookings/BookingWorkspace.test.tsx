// T088: profile editor, suggestion list (accept/dismiss, already-in-
// playlist flag), apply action and result state, naming-error inputs (WCAG).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("creates a structure with the chosen profile instead of a hardcoded none", async () => {
    // Regression (phase 7 review): create always sent
    // booking_profile_id: null, so a structure could never be linked to a
    // profile and Suggestions always ran unfiltered (US7 scenario 3).
    vi.mocked(apiClient.POST).mockResolvedValue({ data: STRUCTURE, error: undefined } as never);
    render(<BookingWorkspace />);
    await screen.findByText("Bruiloft Jansen");

    fireEvent.change(screen.getByLabelText("Naam nieuwe structuur"), {
      target: { value: "Bruiloft De Vries" },
    });
    fireEvent.change(screen.getByLabelText("Profiel"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Structuur aanmaken" }));

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith("/api/structures", {
        body: { name: "Bruiloft De Vries", booking_profile_id: 1 },
      });
    });
  });

  it("saves an edited profile's genre tags and BPM range via PUT", async () => {
    // Regression (phase 7 review): nothing in the UI called
    // PUT /api/profiles/{id}, so the seeded (deliberately empty) profiles
    // could never get the filters FR-031 calls editable.
    vi.mocked(apiClient.PUT).mockResolvedValue({ data: PROFILE, error: undefined } as never);
    render(<BookingWorkspace />);
    await screen.findByText("Bruiloft Jansen");

    const form = within(screen.getByRole("group", { name: "Profiel Bruiloft" }));
    expect(form.getByLabelText("Naam profiel")).toHaveValue("Bruiloft");
    fireEvent.change(form.getByLabelText("Genre tags, komma-gescheiden"), {
      target: { value: "house, disco" },
    });
    fireEvent.change(form.getByLabelText("BPM min"), { target: { value: "118" } });
    fireEvent.change(form.getByLabelText("BPM max"), { target: { value: "128" } });
    fireEvent.click(form.getByRole("button", { name: "Profiel opslaan" }));

    await waitFor(() => {
      expect(apiClient.PUT).toHaveBeenCalledWith("/api/profiles/{profile_id}", {
        params: { path: { profile_id: 1 } },
        body: {
          name: "Bruiloft",
          bpm_min: 118,
          bpm_max: 128,
          genre_tags: ["house", "disco"],
        },
      });
    });
  });

  it("links a profile to the selected structure via PUT", async () => {
    vi.mocked(apiClient.PUT).mockResolvedValue({ data: STRUCTURE, error: undefined } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.change(await screen.findByLabelText("Profiel voor deze structuur"), {
      target: { value: "1" },
    });

    await waitFor(() => {
      expect(apiClient.PUT).toHaveBeenCalledWith("/api/structures/{structure_id}", {
        params: { path: { structure_id: 1 } },
        body: { name: "Bruiloft Jansen", booking_profile_id: 1 },
      });
    });
  });

  it("asks for a bounded page of suggestions, never the whole collection", async () => {
    // Regression (phase 7 review): the limit the endpoint accepts was never
    // sent, so selecting a node fetched every Collection Track and rendered
    // a row with two buttons for each of them.
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    fireEvent.click(await screen.findByRole("button", { name: "Selecteer Ontvangst" }));
    await screen.findByText("Daft Punk – One More Time");

    expect(apiClient.GET).toHaveBeenCalledWith(
      "/api/structures/{structure_id}/nodes/{node_id}/suggestions",
      { params: { path: { structure_id: 1, node_id: 2 }, query: { limit: 50 } } },
    );
  });

  it("raises the limit a page at a time via 'toon meer'", async () => {
    const fullPage = Array.from({ length: 50 }, (_, i) => ({
      ...SUGGESTION,
      rb_content_id: String(i),
      title: `Track ${i}`,
    }));
    mockGet({
      "/api/structures": [STRUCTURE],
      "/api/profiles": [PROFILE],
      "/api/structures/{structure_id}/nodes": [PLAYLIST_NODE],
      "/api/structures/{structure_id}/nodes/{node_id}/suggestions": fullPage,
    });
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    fireEvent.click(await screen.findByRole("button", { name: "Selecteer Ontvangst" }));

    fireEvent.click(await screen.findByRole("button", { name: "Toon meer suggesties" }));

    await waitFor(() => {
      expect(apiClient.GET).toHaveBeenCalledWith(
        "/api/structures/{structure_id}/nodes/{node_id}/suggestions",
        { params: { path: { structure_id: 1, node_id: 2 }, query: { limit: 100 } } },
      );
    });
  });

  it("gives a new node max(position)+1, not the sibling count", async () => {
    // Regression (phase 7 review): a count reuses a position once a
    // non-trailing sibling has been deleted -- the same collision class
    // already fixed in the backend's add_track and Tree.nextPositionAmong.
    const LATER_NODE = { ...PLAYLIST_NODE, id: 9, name: "Later", position: 5 };
    mockGet({
      "/api/structures": [STRUCTURE],
      "/api/profiles": [PROFILE],
      "/api/structures/{structure_id}/nodes": [PLAYLIST_NODE, LATER_NODE],
    });
    vi.mocked(apiClient.POST).mockResolvedValue({ data: {}, error: undefined } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));
    await screen.findByRole("button", { name: "Selecteer Later" });

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe map" }));

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/structures/{structure_id}/nodes",
        expect.objectContaining({
          body: expect.objectContaining({ position: 6 }), // max(0, 5) + 1, not count() == 2
        }),
      );
    });
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

// The Playlist builder's own blocks (HANDOFF.md "3. Playlist builder"), wired
// to the endpoints that actually exist: phase membership comes from the
// Suggestions endpoint's `already_in_playlist` flag (there is no GET for a
// node's tracks), and BPM/key come from a bounded sweep of GET /api/collection
// (which has no per-id lookup).
const PHASE_A = {
  ...PLAYLIST_NODE,
  id: 2,
  name: "Ontvangst",
  position: 0,
  set_phase: "vooravond",
};
const PHASE_B = {
  ...PLAYLIST_NODE,
  id: 3,
  name: "Dansvloer",
  position: 1,
  set_phase: "prime",
};

interface GetOptions {
  params?: { path?: { node_id?: number }; query?: Record<string, unknown> };
}

function mockPhaseTree(
  overrides: {
    nodes?: unknown[];
    missing?: { artist: string; title: string; status: string }[];
    collection?: { total: number; items: unknown[] };
  } = {},
) {
  vi.mocked(apiClient.GET).mockImplementation(((path: string, options?: GetOptions) => {
    const data = (() => {
      switch (path) {
        case "/api/structures":
          return [STRUCTURE];
        case "/api/profiles":
          return [PROFILE];
        case "/api/structures/{structure_id}/nodes":
          return overrides.nodes ?? [PHASE_A, PHASE_B];
        case "/api/structures/{structure_id}/nodes/{node_id}/suggestions":
          return options?.params?.path?.node_id === 2
            ? [{ ...SUGGESTION, already_in_playlist: true }]
            : [];
        case "/api/collection":
          return (
            overrides.collection ?? {
              total: 1,
              items: [
                {
                  rb_content_id: "1",
                  artist: "Daft Punk",
                  title: "One More Time",
                  bpm: 123,
                  musical_key: "8m",
                  duration_ms: 320_000,
                },
              ],
            }
          );
        case "/api/missing":
          return overrides.missing ?? [];
        default:
          return undefined;
      }
    })();
    return Promise.resolve({ data, error: undefined });
  }) as never);
}

describe("BookingWorkspace playlist builder", () => {
  it("builds a phase column per playlist node that carries a set_phase", async () => {
    mockPhaseTree();
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    expect(await screen.findByRole("heading", { name: "vooravond" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "prime" })).toBeInTheDocument();
    expect(screen.getByText("Nog geen nummers in deze fase.")).toBeInTheDocument();
  });

  it("resolves BPM and key for the phase rows from one bounded collection page", async () => {
    mockPhaseTree();
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    const column = (await screen.findByRole("heading", { name: "vooravond" })).closest(
      "li",
    ) as HTMLElement;
    await waitFor(() => {
      expect(within(column).getByText("8m")).toBeInTheDocument();
    });
    expect(within(column).getByText("123 BPM")).toBeInTheDocument();
    expect(apiClient.GET).toHaveBeenCalledWith("/api/collection", {
      params: { query: { limit: 200, offset: 0 } },
    });
  });

  it("moves a track to the next phase as an add plus a remove", async () => {
    mockPhaseTree();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { added: true },
      error: undefined,
    } as never);
    vi.mocked(apiClient.DELETE).mockResolvedValue({
      data: { removed: true },
      error: undefined,
    } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.click(
      await screen.findByRole("button", { name: "Verplaats One More Time naar fase prime" }),
    );

    await waitFor(() => {
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/structures/{structure_id}/nodes/{node_id}/tracks",
        {
          params: { path: { structure_id: 1, node_id: 3 } },
          body: { rb_content_id: "1", origin: "manual" },
        },
      );
    });
    expect(apiClient.DELETE).toHaveBeenCalledWith(
      "/api/structures/{structure_id}/nodes/{node_id}/tracks/{rb_content_id}",
      { params: { path: { structure_id: 1, node_id: 2, rb_content_id: "1" } } },
    );
  });

  it("refuses to move out of a phase that Rekordbox already owns, before writing anything", async () => {
    mockPhaseTree({ nodes: [{ ...PHASE_A, rb_ref: "rb-1" }, PHASE_B] });
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.click(
      await screen.findByRole("button", { name: "Verplaats One More Time naar fase prime" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Deze fase is al toegepast in Rekordbox; verplaats het nummer daar.",
    );
    expect(apiClient.POST).not.toHaveBeenCalled();
  });

  it("says the move failed instead of silently leaving the row where it was", async () => {
    // FR-026's silent-failure ban: a rejected request (offline, backend down)
    // must not look like a click that did nothing.
    mockPhaseTree();
    vi.mocked(apiClient.POST).mockRejectedValue(new Error("offline") as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.click(
      await screen.findByRole("button", { name: "Verplaats One More Time naar fase prime" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Verplaatsen is mislukt. Probeer het opnieuw.",
    );
  });

  it("gives a playlist node a set_phase, which is what makes it a phase column", async () => {
    mockPhaseTree({ nodes: [{ ...PHASE_A, set_phase: null }] });
    vi.mocked(apiClient.PUT).mockResolvedValue({ data: PHASE_A, error: undefined } as never);
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    fireEvent.change(await screen.findByLabelText("Setfase voor Ontvangst"), {
      target: { value: "vooravond" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Setfase opslaan: Ontvangst" }));

    await waitFor(() => {
      expect(apiClient.PUT).toHaveBeenCalledWith("/api/structures/{structure_id}/nodes/{node_id}", {
        params: { path: { structure_id: 1, node_id: 2 } },
        body: { name: "Ontvangst", parent_id: null, position: 0, set_phase: "vooravond" },
      });
    });
  });

  it("flags a phase track that still sits in the buy queue as an open item", async () => {
    mockPhaseTree({
      missing: [{ artist: "daft punk", title: "One More Time", status: "open" }],
    });
    render(<BookingWorkspace />);
    fireEvent.click(await screen.findByText("Bruiloft Jansen"));

    expect(
      await screen.findByText(
        "1 nummer(s) staan nog in de koop-wachtrij: Daft Punk – One More Time",
      ),
    ).toBeInTheDocument();
  });
});
