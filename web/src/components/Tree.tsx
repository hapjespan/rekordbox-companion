import { useId, useMemo, useRef, useState } from "react";

import type { ApiError } from "../features/spotify-sync/types";

// Ids come from two different sources: a booking structure's own nodes are
// keyed by an integer primary key, a Rekordbox playlist by its `ID` string
// (GET /api/playlists). One tree renders both, so the id type is a parameter
// rather than a hardcoded `number`.
export type TreeNodeId = string | number;

// The shape both trees share: a name, whether the node is a folder, its
// parent and its position among its siblings. `set_phase` and `rb_ref` only
// exist on a booking structure's nodes, so they are optional -- the Rekordbox
// library has neither.
export interface TreeNode<TId extends TreeNodeId = number> {
  id: TId;
  parent_id: TId | null;
  kind: "folder" | "playlist";
  name: string;
  position: number;
  set_phase?: string | null;
  rb_ref?: string | null;
}

// The booking structure's node as GET /api/structures/{id} returns it.
export interface TreeNodeDto extends TreeNode<number> {
  set_phase: string | null;
  rb_ref: string | null;
}

// "editor" is the booking-structure workspace (T087): create, rename, move,
// nest, lift, delete. "compact" is the sidebar's read-only Rekordbox library:
// the same tree, folded and unfolded, with the row itself as the control.
type TreeVariant = "editor" | "compact";

interface TreeProps<TId extends TreeNodeId> {
  nodes: TreeNode<TId>[];
  // The tree's accessible name; defaults to the booking structure's.
  label?: string;
  variant?: TreeVariant;
  // Every editing affordance is optional: a row only offers what the caller
  // can actually carry out, which is what makes the read-only variant read-
  // only by construction instead of by a flag.
  onCreate?: (parentId: TId | null, kind: "folder" | "playlist") => void;
  onRename?: (id: TId, name: string) => Promise<ApiError | null>;
  onMove?: (id: TId, parentId: TId | null, position: number) => void;
  onDelete?: (id: TId) => void;
  onSelect?: (id: TId) => void;
  selectedId?: TId | null;
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

function siblingsOf<TId extends TreeNodeId>(
  nodes: TreeNode<TId>[],
  node: TreeNode<TId>,
): TreeNode<TId>[] {
  return nodes
    .filter((n) => n.parent_id === node.parent_id)
    .sort((a, b) => a.position - b.position);
}

function childrenOf<TId extends TreeNodeId>(
  nodes: TreeNode<TId>[],
  parentId: TId,
): TreeNode<TId>[] {
  return nodes.filter((n) => n.parent_id === parentId).sort((a, b) => a.position - b.position);
}

// One indent step per depth level, expressed as calc() over the delivered
// --spacing-16 token: project rule 5 / FR-039 forbid a hardcoded pixel value
// here, and a per-depth multiple can't be a static Tailwind utility class.
function indentStyle(depth: number): React.CSSProperties {
  return { paddingLeft: `calc(var(--spacing-16) * ${depth})` };
}

// max()+1, not count(): a count collides with an existing sibling once the
// group isn't perfectly dense (e.g. a prior move already left a gap or a
// duplicate) -- same bug class the backend's add_track fix (commit 6b4ee24)
// addressed for structure_track positions. Exported so every caller that
// needs a fresh sibling position (BookingWorkspace's create included) shares
// this one implementation instead of re-deriving it from a count.
export function nextPositionAmong<TId extends TreeNodeId>(
  nodes: TreeNode<TId>[],
  parentId: TId | null,
): number {
  const siblings = nodes.filter((n) => n.parent_id === parentId);
  if (siblings.length === 0) return 0;
  return Math.max(...siblings.map((n) => n.position)) + 1;
}

interface RenameFormProps<TId extends TreeNodeId> {
  node: TreeNode<TId>;
  onRename: (id: TId, name: string) => Promise<ApiError | null>;
  onDone: () => void;
}

// T087 (FR-032, WCAG): field-naming errors, same pattern as
// MissingQueue.tsx's manual override form.
function RenameForm<TId extends TreeNodeId>({ node, onRename, onDone }: RenameFormProps<TId>) {
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

interface TreeItemProps<TId extends TreeNodeId> {
  node: TreeNode<TId>;
  nodes: TreeNode<TId>[];
  depth: number;
  variant: TreeVariant;
  collapsedKeys: Set<string>;
  onToggle: (id: TId) => void;
  onCreate?: TreeProps<TId>["onCreate"];
  onRename?: TreeProps<TId>["onRename"];
  onMove?: TreeProps<TId>["onMove"];
  onDelete?: TreeProps<TId>["onDelete"];
  onSelect?: TreeProps<TId>["onSelect"];
  selectedId?: TId | null;
  // ARIA APG treeview: exactly one treeitem is ever part of the page's Tab
  // order (this one, when its id matches). Arrow/Home/End move which one
  // that is; Tree.tsx owns the computation (it needs the whole visible
  // list), TreeItem only renders what it is told.
  activeId: TId | null;
  registerItemRef: (id: TId, el: HTMLLIElement | null) => void;
  onItemKeyDown: (event: React.KeyboardEvent<HTMLLIElement>, node: TreeNode<TId>) => void;
  onItemFocus: (id: TId) => void;
}

const ACTION_BUTTON_CLASSES =
  "min-h-24 min-w-24 rounded-full-2 border border-iron bg-transparent px-12 py-8 text-body-lg font-bold text-pure-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

// The sidebar's row: the prototype's list-row rhythm (HANDOFF.md "Sidebar" --
// 6px radius, #1f1f1f hover), sized for a 300px column instead of the
// workspace's pill buttons, and still a 24px minimum target (WCAG 2.5.8).
const COMPACT_ROW_CLASSES =
  "flex min-h-24 w-full items-center gap-8 rounded-md px-8 py-6 text-left text-body-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spotify-green";

function TreeItem<TId extends TreeNodeId>({
  node,
  nodes,
  depth,
  variant,
  collapsedKeys,
  onToggle,
  onCreate,
  onRename,
  onMove,
  onDelete,
  onSelect,
  selectedId,
  activeId,
  registerItemRef,
  onItemKeyDown,
  onItemFocus,
}: TreeItemProps<TId>) {
  const [renaming, setRenaming] = useState(false);
  const siblings = siblingsOf(nodes, node);
  const index = siblings.findIndex((s) => s.id === node.id);
  const previousSibling = index > 0 ? siblings[index - 1] : null;
  const nextSibling = index < siblings.length - 1 ? siblings[index + 1] : null;
  const parent = node.parent_id !== null ? nodes.find((n) => n.id === node.parent_id) : undefined;
  const children = node.kind === "folder" ? childrenOf(nodes, node.id) : [];
  const foldable = children.length > 0;
  const expanded = foldable && !collapsedKeys.has(String(node.id));
  const isSelected = selectedId === node.id;
  const isActive = activeId !== null && activeId === node.id;
  // Every pill button below is pulled out of the page's Tab order while its
  // row isn't the active one -- `undefined` (not 0) on the active row so a
  // real DOM tabindex attribute is only ever written for the -1 case, same
  // as leaving it off entirely.
  const pillTabIndex = isActive ? undefined : -1;

  function moveUp() {
    if (!previousSibling || !onMove) return;
    onMove(node.id, node.parent_id, previousSibling.position);
    onMove(previousSibling.id, node.parent_id, node.position);
  }

  function moveDown() {
    if (!nextSibling || !onMove) return;
    onMove(node.id, node.parent_id, nextSibling.position);
    onMove(nextSibling.id, node.parent_id, node.position);
  }

  function nestUnderPrevious() {
    if (!previousSibling || !onMove) return;
    onMove(node.id, previousSibling.id, nextPositionAmong(nodes, previousSibling.id));
  }

  function liftOut() {
    if (!parent || !onMove) return;
    onMove(node.id, parent.parent_id, nextPositionAmong(nodes, parent.parent_id));
  }

  return (
    <li
      role="treeitem"
      aria-label={node.name}
      aria-selected={variant === "editor" ? isSelected : undefined}
      // Real state, not a constant: a collapsed folder reports itself as
      // collapsed, and a folder with nothing in it is a leaf (ARIA APG).
      aria-expanded={foldable ? expanded : undefined}
      // Roving tabindex (ARIA APG treeview): the active row is the tree's
      // one Tab stop, every other row is skipped entirely.
      tabIndex={isActive ? 0 : -1}
      ref={(el) => registerItemRef(node.id, el)}
      // A child's own <li> is nested INSIDE its parent's <li> (the real,
      // structural nesting this tree is built on), so a keydown/focus fired
      // on a child bubbles straight through every ancestor treeitem too.
      // Without the target check below, pressing Enter on a child would also
      // fire the ancestor folder's own handler and toggle it -- a real
      // double-activation, not just a test artifact.
      onKeyDown={(event) => {
        if (event.target === event.currentTarget) onItemKeyDown(event, node);
      }}
      onFocus={(event) => {
        if (event.target === event.currentTarget) onItemFocus(node.id);
      }}
    >
      <div
        className={variant === "compact" ? "py-2" : "flex flex-wrap items-center gap-8 py-4"}
        style={indentStyle(depth)}
      >
        {variant === "compact" ? (
          <CompactRow
            node={node}
            foldable={foldable}
            expanded={expanded}
            isSelected={isSelected}
            onToggle={onToggle}
            onSelect={onSelect}
          />
        ) : (
          <>
            {foldable && (
              <button
                type="button"
                aria-expanded={expanded}
                tabIndex={pillTabIndex}
                onClick={() => onToggle(node.id)}
                className={ACTION_BUTTON_CLASSES}
              >
                {expanded ? `Vouw in: ${node.name}` : `Vouw uit: ${node.name}`}
              </button>
            )}
            {node.kind === "playlist" && onSelect ? (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={() => onSelect(node.id)}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Selecteer ${node.name}`}
              </button>
            ) : (
              <span className="text-body-lg font-semibold text-pure-white">{node.name}</span>
            )}
            {node.set_phase && (
              <span className="text-body-lg text-mist">{`Setfase: ${node.set_phase}`}</span>
            )}
            {node.rb_ref && <span className="text-body-lg text-mist">Toegepast in Rekordbox</span>}

            {onRename && (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={() => setRenaming((current) => !current)}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Naam wijzigen: ${node.name}`}
              </button>
            )}
            {onMove && previousSibling && (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={moveUp}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Verplaats omhoog: ${node.name}`}
              </button>
            )}
            {onMove && nextSibling && (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={moveDown}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Verplaats omlaag: ${node.name}`}
              </button>
            )}
            {onMove && previousSibling && (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={nestUnderPrevious}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Nest onder vorige: ${node.name}`}
              </button>
            )}
            {onMove && parent && (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={liftOut}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Til uit map: ${node.name}`}
              </button>
            )}
            {onCreate && node.kind === "folder" && (
              <>
                <button
                  type="button"
                  tabIndex={pillTabIndex}
                  onClick={() => onCreate(node.id, "folder")}
                  className={ACTION_BUTTON_CLASSES}
                >
                  {`Nieuwe map in ${node.name}`}
                </button>
                <button
                  type="button"
                  tabIndex={pillTabIndex}
                  onClick={() => onCreate(node.id, "playlist")}
                  className={ACTION_BUTTON_CLASSES}
                >
                  {`Nieuwe playlist in ${node.name}`}
                </button>
              </>
            )}
            {onDelete && (
              <button
                type="button"
                tabIndex={pillTabIndex}
                onClick={() => onDelete(node.id)}
                className={ACTION_BUTTON_CLASSES}
              >
                {`Verwijderen: ${node.name}`}
              </button>
            )}
          </>
        )}
      </div>

      {renaming && onRename && (
        <div style={indentStyle(depth)}>
          <RenameForm node={node} onRename={onRename} onDone={() => setRenaming(false)} />
        </div>
      )}

      {expanded && children.length > 0 && (
        <ul role="group">
          {children.map((child) => (
            <TreeItem
              key={String(child.id)}
              node={child}
              nodes={nodes}
              depth={depth + 1}
              variant={variant}
              collapsedKeys={collapsedKeys}
              onToggle={onToggle}
              onCreate={onCreate}
              onRename={onRename}
              onMove={onMove}
              onDelete={onDelete}
              onSelect={onSelect}
              selectedId={selectedId}
              activeId={activeId}
              registerItemRef={registerItemRef}
              onItemKeyDown={onItemKeyDown}
              onItemFocus={onItemFocus}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

interface CompactRowProps<TId extends TreeNodeId> {
  node: TreeNode<TId>;
  foldable: boolean;
  expanded: boolean;
  isSelected: boolean;
  onToggle: (id: TId) => void;
  onSelect?: (id: TId) => void;
}

// One sidebar row. A folder row IS its fold control (biggest target); a
// playlist row selects. Both are real buttons for the mouse and for a
// screen reader's own element list, but neither is a Tab stop of its own
// (`tabIndex={-1}`): the wrapping `<li role="treeitem">` is the tree's roving
// tab stop and its Enter/Space handling already reproduces this exact click,
// so there is nothing left for a second, separate stop to do. The fold state
// rides on aria-expanded plus the glyph's shape -- never on colour.
function CompactRow<TId extends TreeNodeId>({
  node,
  foldable,
  expanded,
  isSelected,
  onToggle,
  onSelect,
}: CompactRowProps<TId>) {
  if (node.kind === "folder") {
    if (!foldable) {
      return (
        <span className={`${COMPACT_ROW_CLASSES} font-semibold text-mist`}>
          <span aria-hidden="true" className="flex-none">
            ·
          </span>
          <span className="truncate">{node.name}</span>
        </span>
      );
    }
    return (
      <button
        type="button"
        aria-expanded={expanded}
        tabIndex={-1}
        onClick={() => onToggle(node.id)}
        className={`${COMPACT_ROW_CLASSES} font-semibold text-pure-white hover:bg-graphite`}
      >
        <span aria-hidden="true" className="flex-none">
          {expanded ? "▾" : "▸"}
        </span>
        <span className="truncate">{node.name}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      // The playlist the main pane is currently filtered to is announced,
      // not merely shaded (WCAG 1.4.1 / 4.1.2) -- same pattern as the
      // WORKSPACE nav items.
      aria-current={isSelected ? "true" : undefined}
      tabIndex={-1}
      onClick={() => onSelect?.(node.id)}
      className={`${COMPACT_ROW_CLASSES} ${
        isSelected
          ? "bg-smoke text-pure-white"
          : "text-mist hover:bg-graphite hover:text-pure-white"
      }`}
    >
      <span aria-hidden="true" className="flex-none">
        ♪
      </span>
      <span className="truncate">{node.name}</span>
    </button>
  );
}

// T087 (FR-032, WCAG): a real nested <ul>/<li role="treeitem"> tree, not a
// flat list -- nesting is conveyed structurally, matching TrackTable.tsx's
// choice of a real <table> for its own semantics. Move/nest/lift use plain
// buttons (position swap / re-parent), not drag-and-drop: fully keyboard-
// operable by construction, no custom arrow-key widget needed.
//
// The sidebar's Rekordbox library (components/RekordboxLibrary.tsx) renders
// through this same component in the "compact" variant, rather than a second
// tree implementation: the indentation, the parent_id reconstruction, the
// treeitem semantics and the fold state are the parts that must not drift.
export function Tree<TId extends TreeNodeId>({
  nodes,
  label = "Boekingstructuur",
  variant = "editor",
  onCreate,
  onRename,
  onMove,
  onDelete,
  onSelect,
  selectedId,
}: TreeProps<TId>) {
  // Collapsed, not expanded, is what is tracked: everything starts open, so a
  // freshly loaded tree shows what is in it, and a node added later is not
  // hidden by a stale expansion set.
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(new Set());

  function handleToggle(id: TId) {
    setCollapsedKeys((current) => {
      const next = new Set(current);
      const key = String(id);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const roots = rootsOf(nodes);

  // ARIA APG treeview: the roving tab stop, and the DOM nodes it moves
  // between. A ref map rather than one ref per row, because the number of
  // rows is dynamic and every row already unmounts/remounts on fold.
  const [activeId, setActiveId] = useState<TId | null>(null);
  const itemRefs = useRef(new Map<string, HTMLLIElement>());

  function registerItemRef(id: TId, el: HTMLLIElement | null) {
    const key = String(id);
    if (el) itemRefs.current.set(key, el);
    else itemRefs.current.delete(key);
  }

  function focusNode(id: TId) {
    itemRefs.current.get(String(id))?.focus();
  }

  // Every VISIBLE row, in document order, depth-first, skipping a collapsed
  // folder's children entirely -- recomputed whenever the tree's shape or its
  // fold state changes. ArrowUp/Down/Home/End just step through this list
  // instead of walking sibling/parent pointers node by node.
  const visible = useMemo(() => {
    const acc: { node: TreeNode<TId>; depth: number }[] = [];
    function walk(level: TreeNode<TId>[], depth: number) {
      for (const n of level) {
        acc.push({ node: n, depth });
        const kids = n.kind === "folder" ? childrenOf(nodes, n.id) : [];
        const isExpanded = kids.length > 0 && !collapsedKeys.has(String(n.id));
        if (isExpanded) walk(kids, depth + 1);
      }
    }
    // `rootsOf(nodes)` recomputed here rather than closing over the outer
    // `roots` -- that one is a fresh array every render, so using it as a
    // useMemo dependency would defeat the memoisation it's declared in.
    walk(rootsOf(nodes), 0);
    return acc;
  }, [nodes, collapsedKeys]);

  const activeIndex = activeId !== null ? visible.findIndex((v) => v.node.id === activeId) : -1;
  // A stale id (its node was deleted, or nothing has been focused yet) falls
  // back to the first visible row -- the tree always has exactly one roving
  // tab stop, never zero.
  const effectiveActiveId = activeIndex >= 0 ? activeId : (visible[0]?.node.id ?? null);

  function moveTo(id: TId) {
    setActiveId(id);
    focusNode(id);
  }

  // What Enter/Space does, matching each variant's own primary click: a
  // foldable row toggles (the fold button's/compact row's own action), a
  // playlist row with a select handler selects (the "Selecteer ..." button/
  // compact row's own action) -- a leaf folder with neither has nothing to
  // activate, same as clicking its plain-text row today.
  function activatePrimary(node: TreeNode<TId>) {
    const kids = node.kind === "folder" ? childrenOf(nodes, node.id) : [];
    if (kids.length > 0) {
      handleToggle(node.id);
      return;
    }
    if (node.kind === "playlist" && onSelect) onSelect(node.id);
  }

  function handleItemKeyDown(event: React.KeyboardEvent<HTMLLIElement>, node: TreeNode<TId>) {
    const index = visible.findIndex((v) => v.node.id === node.id);
    const kids = node.kind === "folder" ? childrenOf(nodes, node.id) : [];
    const foldable = kids.length > 0;
    const expanded = foldable && !collapsedKeys.has(String(node.id));

    switch (event.key) {
      case "ArrowDown": {
        event.preventDefault();
        const next = visible[Math.min(index + 1, visible.length - 1)];
        if (next) moveTo(next.node.id);
        break;
      }
      case "ArrowUp": {
        event.preventDefault();
        const previous = visible[Math.max(index - 1, 0)];
        if (previous) moveTo(previous.node.id);
        break;
      }
      case "Home": {
        event.preventDefault();
        if (visible[0]) moveTo(visible[0].node.id);
        break;
      }
      case "End": {
        event.preventDefault();
        const last = visible[visible.length - 1];
        if (last) moveTo(last.node.id);
        break;
      }
      case "ArrowRight": {
        event.preventDefault();
        if (foldable && !expanded) {
          handleToggle(node.id);
        } else if (foldable && expanded && kids[0]) {
          moveTo(kids[0].id);
        }
        break;
      }
      case "ArrowLeft": {
        event.preventDefault();
        if (foldable && expanded) {
          handleToggle(node.id);
        } else if (node.parent_id !== null) {
          moveTo(node.parent_id);
        }
        break;
      }
      case "Enter":
      case " ": {
        event.preventDefault();
        activatePrimary(node);
        break;
      }
      default:
        break;
    }
  }

  function handleItemFocus(id: TId) {
    setActiveId(id);
  }

  const items = (
    <ul role="tree" aria-label={label} className={variant === "compact" ? "flex flex-col" : ""}>
      {roots.map((node) => (
        <TreeItem
          key={String(node.id)}
          node={node}
          nodes={nodes}
          depth={0}
          variant={variant}
          collapsedKeys={collapsedKeys}
          onToggle={handleToggle}
          onCreate={onCreate}
          onRename={onRename}
          onMove={onMove}
          onDelete={onDelete}
          onSelect={onSelect}
          selectedId={selectedId}
          activeId={effectiveActiveId}
          registerItemRef={registerItemRef}
          onItemKeyDown={handleItemKeyDown}
          onItemFocus={handleItemFocus}
        />
      ))}
    </ul>
  );

  if (variant === "compact") return items;

  return (
    <div className="flex flex-col gap-16">
      {onCreate && (
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
      )}
      {items}
    </div>
  );
}

function rootsOf<TId extends TreeNodeId>(nodes: TreeNode<TId>[]): TreeNode<TId>[] {
  return nodes.filter((n) => n.parent_id === null).sort((a, b) => a.position - b.position);
}
