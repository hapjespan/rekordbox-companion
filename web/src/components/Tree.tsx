import { useId, useState } from "react";

import type { ApiError } from "../features/spotify-sync/types";

export interface TreeNodeDto {
  id: number;
  parent_id: number | null;
  kind: "folder" | "playlist";
  name: string;
  position: number;
  set_phase: string | null;
  rb_ref: string | null;
}

interface TreeProps {
  nodes: TreeNodeDto[];
  onCreate: (parentId: number | null, kind: "folder" | "playlist") => void;
  onRename: (id: number, name: string) => Promise<ApiError | null>;
  onMove: (id: number, parentId: number | null, position: number) => void;
  onDelete: (id: number) => void;
  onSelect?: (id: number) => void;
  selectedId?: number | null;
}

// Same code-keyed-switch convention as MissingQueue.tsx/PlaylistUrlForm.tsx's
// error mappers: Dutch text for known codes, the raw backend message only
// as a last resort.
function renameErrorMessageFor(error: ApiError): string {
  switch (error.code) {
    case "node_name_locked":
      return "Dit is al toegepast in Rekordbox; hernoem daar in plaats hiervan.";
    default:
      return error.message || "Kon de naam niet opslaan. Probeer het opnieuw.";
  }
}

function siblingsOf(nodes: TreeNodeDto[], node: TreeNodeDto): TreeNodeDto[] {
  return nodes
    .filter((n) => n.parent_id === node.parent_id)
    .sort((a, b) => a.position - b.position);
}

function childrenOf(nodes: TreeNodeDto[], parentId: number): TreeNodeDto[] {
  return nodes.filter((n) => n.parent_id === parentId).sort((a, b) => a.position - b.position);
}

// max()+1, not count(): a count collides with an existing sibling once the
// group isn't perfectly dense (e.g. a prior move already left a gap or a
// duplicate) -- same bug class the backend's add_track fix (commit 6b4ee24)
// addressed for structure_track positions.
function nextPositionAmong(nodes: TreeNodeDto[], parentId: number | null): number {
  const siblings = nodes.filter((n) => n.parent_id === parentId);
  if (siblings.length === 0) return 0;
  return Math.max(...siblings.map((n) => n.position)) + 1;
}

interface RenameFormProps {
  node: TreeNodeDto;
  onRename: (id: number, name: string) => Promise<ApiError | null>;
  onDone: () => void;
}

// T087 (FR-032, WCAG): field-naming errors, same pattern as
// MissingQueue.tsx's manual override form.
function RenameForm({ node, onRename, onDone }: RenameFormProps) {
  const [draft, setDraft] = useState(node.name);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = useId();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const apiError = await onRename(node.id, draft);
    if (apiError) {
      setError(renameErrorMessageFor(apiError));
      return;
    }
    onDone();
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-8">
      <label htmlFor={inputId} className="text-body-lg font-semibold">
        {`Nieuwe naam voor ${node.name}`}
      </label>
      <div className="flex flex-wrap gap-8">
        <input
          id={inputId}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          className="min-h-24 flex-1 rounded-full border border-iron bg-smoke px-12 py-8 text-body-lg text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        />
        <button
          type="submit"
          className="min-h-24 rounded-full-2 bg-pure-white px-12 py-8 text-body-lg font-bold text-void-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green"
        >
          Opslaan
        </button>
      </div>
      {error && (
        <p id={errorId} role="alert" className="text-body-lg font-semibold text-pure-white">
          {error}
        </p>
      )}
    </form>
  );
}

interface TreeItemProps {
  node: TreeNodeDto;
  nodes: TreeNodeDto[];
  depth: number;
  onCreate: TreeProps["onCreate"];
  onRename: TreeProps["onRename"];
  onMove: TreeProps["onMove"];
  onDelete: TreeProps["onDelete"];
  onSelect?: TreeProps["onSelect"];
  selectedId?: number | null;
}

const ACTION_BUTTON_CLASSES =
  "min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

function TreeItem({
  node,
  nodes,
  depth,
  onCreate,
  onRename,
  onMove,
  onDelete,
  onSelect,
  selectedId,
}: TreeItemProps) {
  const [renaming, setRenaming] = useState(false);
  const siblings = siblingsOf(nodes, node);
  const index = siblings.findIndex((s) => s.id === node.id);
  const previousSibling = index > 0 ? siblings[index - 1] : null;
  const nextSibling = index < siblings.length - 1 ? siblings[index + 1] : null;
  const parent = node.parent_id !== null ? nodes.find((n) => n.id === node.parent_id) : undefined;
  const children = node.kind === "folder" ? childrenOf(nodes, node.id) : [];

  function moveUp() {
    if (!previousSibling) return;
    onMove(node.id, node.parent_id, previousSibling.position);
    onMove(previousSibling.id, node.parent_id, node.position);
  }

  function moveDown() {
    if (!nextSibling) return;
    onMove(node.id, node.parent_id, nextSibling.position);
    onMove(nextSibling.id, node.parent_id, node.position);
  }

  function nestUnderPrevious() {
    if (!previousSibling) return;
    onMove(node.id, previousSibling.id, nextPositionAmong(nodes, previousSibling.id));
  }

  function liftOut() {
    if (!parent) return;
    onMove(node.id, parent.parent_id, nextPositionAmong(nodes, parent.parent_id));
  }

  return (
    <li
      role="treeitem"
      aria-label={node.name}
      aria-selected={selectedId === node.id}
      aria-expanded={node.kind === "folder" ? true : undefined}
    >
      <div className="flex flex-wrap items-center gap-8 py-4" style={{ paddingLeft: depth * 16 }}>
        {node.kind === "playlist" && onSelect ? (
          <button type="button" onClick={() => onSelect(node.id)} className={ACTION_BUTTON_CLASSES}>
            {`Selecteer ${node.name}`}
          </button>
        ) : (
          <span className="text-body-lg font-semibold text-pure-white">{node.name}</span>
        )}
        {node.set_phase && (
          <span className="text-body-lg text-mist">{`Set Phase: ${node.set_phase}`}</span>
        )}
        {node.rb_ref && <span className="text-body-lg text-mist">Toegepast in Rekordbox</span>}

        <button
          type="button"
          onClick={() => setRenaming((current) => !current)}
          className={ACTION_BUTTON_CLASSES}
        >
          {`Naam wijzigen: ${node.name}`}
        </button>
        {previousSibling && (
          <button type="button" onClick={moveUp} className={ACTION_BUTTON_CLASSES}>
            {`Verplaats omhoog: ${node.name}`}
          </button>
        )}
        {nextSibling && (
          <button type="button" onClick={moveDown} className={ACTION_BUTTON_CLASSES}>
            {`Verplaats omlaag: ${node.name}`}
          </button>
        )}
        {previousSibling && (
          <button type="button" onClick={nestUnderPrevious} className={ACTION_BUTTON_CLASSES}>
            {`Nest onder vorige: ${node.name}`}
          </button>
        )}
        {parent && (
          <button type="button" onClick={liftOut} className={ACTION_BUTTON_CLASSES}>
            {`Til uit map: ${node.name}`}
          </button>
        )}
        {node.kind === "folder" && (
          <>
            <button
              type="button"
              onClick={() => onCreate(node.id, "folder")}
              className={ACTION_BUTTON_CLASSES}
            >
              {`Nieuwe map in ${node.name}`}
            </button>
            <button
              type="button"
              onClick={() => onCreate(node.id, "playlist")}
              className={ACTION_BUTTON_CLASSES}
            >
              {`Nieuwe playlist in ${node.name}`}
            </button>
          </>
        )}
        <button type="button" onClick={() => onDelete(node.id)} className={ACTION_BUTTON_CLASSES}>
          {`Verwijderen: ${node.name}`}
        </button>
      </div>

      {renaming && (
        <div style={{ paddingLeft: depth * 16 }}>
          <RenameForm node={node} onRename={onRename} onDone={() => setRenaming(false)} />
        </div>
      )}

      {children.length > 0 && (
        <ul role="group">
          {children.map((child) => (
            <TreeItem
              key={child.id}
              node={child}
              nodes={nodes}
              depth={depth + 1}
              onCreate={onCreate}
              onRename={onRename}
              onMove={onMove}
              onDelete={onDelete}
              onSelect={onSelect}
              selectedId={selectedId}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// T087 (FR-032, WCAG): a real nested <ul>/<li role="treeitem"> tree, not a
// flat list -- nesting is conveyed structurally, matching TrackTable.tsx's
// choice of a real <table> for its own semantics. Move/nest/lift use plain
// buttons (position swap / re-parent), not drag-and-drop: fully keyboard-
// operable by construction, no custom arrow-key widget needed.
export function Tree({
  nodes,
  onCreate,
  onRename,
  onMove,
  onDelete,
  onSelect,
  selectedId,
}: TreeProps) {
  const roots = childrenOfRoot(nodes);

  return (
    <div className="flex flex-col gap-16">
      <div className="flex flex-wrap gap-8" role="group" aria-label="Nieuw item aanmaken">
        <button
          type="button"
          onClick={() => onCreate(null, "folder")}
          className={ACTION_BUTTON_CLASSES}
        >
          Nieuwe map
        </button>
        <button
          type="button"
          onClick={() => onCreate(null, "playlist")}
          className={ACTION_BUTTON_CLASSES}
        >
          Nieuwe playlist
        </button>
      </div>
      <ul role="tree" aria-label="Booking Structure">
        {roots.map((node) => (
          <TreeItem
            key={node.id}
            node={node}
            nodes={nodes}
            depth={0}
            onCreate={onCreate}
            onRename={onRename}
            onMove={onMove}
            onDelete={onDelete}
            onSelect={onSelect}
            selectedId={selectedId}
          />
        ))}
      </ul>
    </div>
  );
}

function childrenOfRoot(nodes: TreeNodeDto[]): TreeNodeDto[] {
  return nodes.filter((n) => n.parent_id === null).sort((a, b) => a.position - b.position);
}
