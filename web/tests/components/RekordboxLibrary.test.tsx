// The sidebar's Rekordbox section: the library as the hierarchical,
// expandable tree Rekordbox itself shows, reconstructed from the flat
// [PlaylistNode] of GET /api/playlists via parent_id.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../src/api/client";
import { RekordboxLibrary } from "../../src/components/RekordboxLibrary";

vi.mock("../../src/api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const NODES = [
  { rb_playlist_id: "1", name: "Bruiloften", parent_id: null, is_folder: true, position: 1 },
  { rb_playlist_id: "2", name: "Warme opener", parent_id: "1", is_folder: false, position: 1 },
  { rb_playlist_id: "3", name: "Peak time", parent_id: null, is_folder: false, position: 2 },
];

function mockNodes(nodes: unknown[]) {
  vi.mocked(apiClient.GET).mockResolvedValue({ data: nodes, error: undefined } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockNodes(NODES);
});

describe("RekordboxLibrary", () => {
  it("rebuilds the hierarchy from parent_id, folders holding their playlists", async () => {
    render(<RekordboxLibrary onSelect={vi.fn()} />);

    expect(await screen.findByRole("tree", { name: "Rekordbox-bibliotheek" })).toBeInTheDocument();
    const folder = screen.getByRole("treeitem", { name: /Bruiloften/ });
    expect(folder).toBeInTheDocument();
    // The nested playlist is a child of the folder's own group, not a sibling.
    expect(folder.querySelector("[role='group']")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Warme opener" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Peak time" })).toBeInTheDocument();
  });

  it("folds a folder closed and open again, keyboard-operable with aria-expanded", async () => {
    render(<RekordboxLibrary onSelect={vi.fn()} />);

    const folder = await screen.findByRole("button", { name: "Bruiloften" });
    expect(folder).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(folder);

    expect(folder).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Warme opener" })).not.toBeInTheDocument();

    fireEvent.click(folder);

    expect(folder).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Warme opener" })).toBeInTheDocument();
  });

  it("hands the clicked playlist's id and name up, so the view can name it", async () => {
    const onSelect = vi.fn();
    render(<RekordboxLibrary onSelect={onSelect} />);

    fireEvent.click(await screen.findByRole("button", { name: "Warme opener" }));

    expect(onSelect).toHaveBeenCalledWith({ id: "2", name: "Warme opener" });
  });

  it("marks the playlist the Collection view is filtered to, in more than colour", async () => {
    render(<RekordboxLibrary onSelect={vi.fn()} selectedId="3" />);

    expect(await screen.findByRole("button", { name: "Peak time" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "Warme opener" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("reports an unreadable Rekordbox library in Dutch instead of an empty tree", async () => {
    vi.mocked(apiClient.GET).mockResolvedValue({
      data: undefined,
      error: { code: "rekordbox_not_found", message: "master.db not found" },
    } as never);

    render(<RekordboxLibrary onSelect={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Rekordbox is niet gevonden. Start Rekordbox en herlaad de pagina.",
    );
  });

  it("tells an empty library apart from a failure", async () => {
    mockNodes([]);

    render(<RekordboxLibrary onSelect={vi.fn()} />);

    expect(await screen.findByText("Geen playlists in Rekordbox gevonden.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports a network failure with its own message", async () => {
    vi.mocked(apiClient.GET).mockRejectedValue(new Error("network down"));

    render(<RekordboxLibrary onSelect={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Kon je Rekordbox-bibliotheek niet laden. Probeer het opnieuw.",
    );
  });
});
