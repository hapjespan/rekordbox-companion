// T087: folder/playlist tree editor (create/rename/nest/move/delete), Set
// Phase labels, Run-of-Show folder, keyboard-operable (WCAG).
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Tree } from "../../src/components/Tree";
import type { TreeNodeDto } from "../../src/components/Tree";

const FOLDER: TreeNodeDto = {
  id: 1,
  parent_id: null,
  kind: "folder",
  name: "Vooravond",
  position: 0,
  set_phase: "vooravond",
  rb_ref: null,
};

const PLAYLIST: TreeNodeDto = {
  id: 2,
  parent_id: 1,
  kind: "playlist",
  name: "Ontvangst",
  position: 0,
  set_phase: null,
  rb_ref: null,
};

const APPLIED_PLAYLIST: TreeNodeDto = {
  ...PLAYLIST,
  id: 3,
  parent_id: null,
  name: "Toegepast",
  rb_ref: "rb-playlist-1",
};

function noop() {
  /* not under test */
}

describe("Tree", () => {
  it("renders folders and nested playlists with their Set Phase label", () => {
    render(
      <Tree
        nodes={[FOLDER, PLAYLIST]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByText("Vooravond")).toBeInTheDocument();
    expect(screen.getByText("Ontvangst")).toBeInTheDocument();
    expect(screen.getByText("Setfase: vooravond")).toBeInTheDocument();
  });

  it("renders as a real tree with nesting conveyed structurally", () => {
    render(
      <Tree
        nodes={[FOLDER, PLAYLIST]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByRole("tree")).toBeInTheDocument();
    const playlistItem = screen.getByRole("treeitem", { name: /Ontvangst/ });
    expect(playlistItem).toBeInTheDocument();
  });

  it("indents by depth through the spacing token, never a hardcoded pixel value", () => {
    // Project rule 5 / FR-039: every spacing value traces to a token in
    // design-input/theme.css. The indent used to be `depth * 16` in raw
    // pixels (phase 7 review finding).
    render(
      <Tree
        nodes={[FOLDER, PLAYLIST]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
      />,
    );

    const nestedRow = screen
      .getByRole("treeitem", { name: "Ontvangst" })
      .querySelector<HTMLElement>("div");
    const style = nestedRow?.getAttribute("style") ?? "";
    expect(style).toContain("var(--spacing-16)");
    expect(style).not.toMatch(/\d+px/);
  });

  it("renames a node via the field-naming form, no colour-only state", async () => {
    const onRename = vi.fn().mockResolvedValue(null);
    render(
      <Tree nodes={[FOLDER]} onCreate={noop} onRename={onRename} onMove={noop} onDelete={noop} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Naam wijzigen: Vooravond" }));
    fireEvent.change(screen.getByLabelText("Nieuwe naam voor Vooravond"), {
      target: { value: "Ontvangst en borrel" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    expect(onRename).toHaveBeenCalledWith(1, "Ontvangst en borrel");
  });

  it("shows a naming error instead of renaming when the backend refuses", async () => {
    const onRename = vi.fn().mockResolvedValue({
      code: "node_name_locked",
      message: "already applied",
      field: "name",
    });
    render(
      <Tree
        nodes={[APPLIED_PLAYLIST]}
        onCreate={noop}
        onRename={onRename}
        onMove={noop}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Naam wijzigen: Toegepast" }));
    fireEvent.change(screen.getByLabelText("Nieuwe naam voor Toegepast"), {
      target: { value: "Nieuwe naam" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    expect(
      await screen.findByText("Dit is al toegepast in Rekordbox; hernoem daar in plaats hiervan."),
    ).toBeInTheDocument();
  });

  it("conveys an applied node in text, not colour alone", () => {
    render(
      <Tree
        nodes={[APPLIED_PLAYLIST]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
      />,
    );

    expect(screen.getByText("Toegepast in Rekordbox")).toBeInTheDocument();
  });

  it("moves a node up, swapping position with the previous sibling", () => {
    const onMove = vi.fn();
    const second = { ...PLAYLIST, id: 4, name: "Tweede", position: 1 };
    render(
      <Tree
        nodes={[FOLDER, PLAYLIST, second]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={onMove}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Verplaats omhoog: Tweede" }));

    expect(onMove).toHaveBeenCalledWith(4, 1, 0);
    expect(onMove).toHaveBeenCalledWith(2, 1, 1);
  });

  it("nests a node under its previous sibling", () => {
    const onMove = vi.fn();
    const sibling = { ...FOLDER, id: 5, name: "Mid", position: 1 };
    render(
      <Tree
        nodes={[FOLDER, sibling]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={onMove}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Nest onder vorige: Mid" }));

    expect(onMove).toHaveBeenCalledWith(5, 1, 0);
  });

  it("nests under a previous sibling that already has children, without colliding on position", () => {
    // Regression: a plain count() of existing children collides once a
    // prior move/removal already left the group non-dense (same bug class
    // fixed server-side for structure_track positions, commit 6b4ee24).
    const onMove = vi.fn();
    const sibling = { ...FOLDER, id: 5, name: "Mid", position: 1 };
    const existingChild = { ...PLAYLIST, id: 6, parent_id: 1, position: 3 };
    render(
      <Tree
        nodes={[FOLDER, sibling, existingChild]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={onMove}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Nest onder vorige: Mid" }));

    expect(onMove).toHaveBeenCalledWith(5, 1, 4); // max(3) + 1, not count() == 1
  });

  it("lifts a node out of its folder without colliding with an existing sibling", () => {
    const onMove = vi.fn();
    const outerSibling = { ...FOLDER, id: 7, name: "Later Root", position: 5 };
    const nested = { ...PLAYLIST, id: 8, name: "Nested", parent_id: 1, position: 0 };
    render(
      <Tree
        nodes={[FOLDER, outerSibling, nested]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={onMove}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Til uit map: Nested" }));

    expect(onMove).toHaveBeenCalledWith(8, null, 6); // max(0, 5) + 1, not FOLDER.position + 1 == 1
  });

  it("deletes a node", () => {
    const onDelete = vi.fn();
    render(
      <Tree
        nodes={[FOLDER]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Verwijderen: Vooravond" }));

    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it("creates a new root folder and a new root playlist", () => {
    const onCreate = vi.fn();
    render(
      <Tree nodes={[]} onCreate={onCreate} onRename={vi.fn()} onMove={noop} onDelete={noop} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe map" }));
    fireEvent.click(screen.getByRole("button", { name: "Nieuwe playlist" }));

    expect(onCreate).toHaveBeenCalledWith(null, "folder");
    expect(onCreate).toHaveBeenCalledWith(null, "playlist");
  });

  it("creates a child node under a folder", () => {
    const onCreate = vi.fn();
    render(
      <Tree
        nodes={[FOLDER]}
        onCreate={onCreate}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Nieuwe playlist in Vooravond" }));

    expect(onCreate).toHaveBeenCalledWith(1, "playlist");
  });

  it("calls onSelect when a playlist row is chosen", () => {
    const onSelect = vi.fn();
    render(
      <Tree
        nodes={[FOLDER, PLAYLIST]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Selecteer Ontvangst" }));

    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("folds a folder closed and open again, reporting it on the treeitem too", () => {
    render(
      <Tree
        nodes={[FOLDER, PLAYLIST]}
        onCreate={noop}
        onRename={vi.fn()}
        onMove={noop}
        onDelete={noop}
      />,
    );

    // Open by default: a booking structure is built by looking at all of it.
    expect(screen.getByRole("treeitem", { name: /Vooravond/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "Vouw in: Vooravond" }));

    expect(screen.getByRole("treeitem", { name: /Vooravond/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText("Ontvangst")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Vouw uit: Vooravond" }));

    expect(screen.getByText("Ontvangst")).toBeInTheDocument();
  });

  it("offers no fold control on a folder that has no children", () => {
    render(
      <Tree nodes={[FOLDER]} onCreate={noop} onRename={vi.fn()} onMove={noop} onDelete={noop} />,
    );

    expect(screen.queryByRole("button", { name: /Vouw/ })).not.toBeInTheDocument();
    expect(screen.getByRole("treeitem", { name: /Vooravond/ })).not.toHaveAttribute(
      "aria-expanded",
    );
  });
});

// The same component renders the read-only Rekordbox library in the sidebar
// (components/RekordboxLibrary.tsx): string ids, no editing affordances, and
// a folder row that is itself the expand/collapse control.
const LIBRARY_FOLDER = {
  id: "1",
  parent_id: null,
  kind: "folder" as const,
  name: "Bruiloften",
  position: 1,
};

const LIBRARY_PLAYLIST = {
  id: "2",
  parent_id: "1",
  kind: "playlist" as const,
  name: "Warme opener",
  position: 1,
};

describe("Tree, compact variant", () => {
  it("renders string-keyed nodes without any editing control", () => {
    render(
      <Tree
        variant="compact"
        label="Rekordbox-bibliotheek"
        nodes={[LIBRARY_FOLDER, LIBRARY_PLAYLIST]}
        onSelect={noop}
      />,
    );

    expect(screen.getByRole("tree", { name: "Rekordbox-bibliotheek" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Naam wijzigen/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Verwijderen/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Nieuwe/ })).not.toBeInTheDocument();
  });

  it("makes the folder row itself the expand/collapse control", () => {
    render(
      <Tree
        variant="compact"
        label="Rekordbox-bibliotheek"
        nodes={[LIBRARY_FOLDER, LIBRARY_PLAYLIST]}
        onSelect={noop}
      />,
    );

    const folder = screen.getByRole("button", { name: "Bruiloften" });
    expect(folder).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(folder);

    expect(folder).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Warme opener" })).not.toBeInTheDocument();
  });

  it("selects a playlist by its own name and marks the selected one", () => {
    const onSelect = vi.fn();
    render(
      <Tree
        variant="compact"
        label="Rekordbox-bibliotheek"
        nodes={[LIBRARY_FOLDER, LIBRARY_PLAYLIST]}
        onSelect={onSelect}
        selectedId="2"
      />,
    );

    const playlist = screen.getByRole("button", { name: "Warme opener" });
    expect(playlist).toHaveAttribute("aria-current", "true");

    fireEvent.click(playlist);

    expect(onSelect).toHaveBeenCalledWith("2");
  });

  it("indents nested rows through the spacing token, never a hardcoded pixel value", () => {
    render(
      <Tree
        variant="compact"
        label="Rekordbox-bibliotheek"
        nodes={[LIBRARY_FOLDER, LIBRARY_PLAYLIST]}
        onSelect={noop}
      />,
    );

    const nestedRow = screen
      .getByRole("treeitem", { name: "Warme opener" })
      .querySelector<HTMLElement>("div");
    const style = nestedRow?.getAttribute("style") ?? "";
    expect(style).toContain("var(--spacing-16)");
    expect(style).not.toMatch(/\d+px/);
  });
});
