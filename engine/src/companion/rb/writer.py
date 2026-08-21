"""The single, guarded write path into the Rekordbox database (FR-016..FR-018).

This is the ONLY module in the codebase permitted to write to the DJ's real,
irreplaceable Rekordbox library (project rule 2). A backup already exists and
the guard has already passed by the time `apply_playlist` is called: this
module's job starts at "write to `db_path`" and ends at "readback confirms it".
Backup creation (`rb/backup.py`, T047) and the write-refusal guard
(`rb/guard.py`, T046) are separate modules run before this one in the apply
flow (the API endpoint, T050).

The three safety invariants this module upholds (FR-017/FR-018, Principle
II/III):

- **Write only playlists.** It creates and appends to playlists, and never
  edits track metadata, cues or beat grids.
- **Add-only.** On re-apply it appends only content ids not already present as
  a `DjmdSongPlaylist` row for the target playlist, and never removes or
  reorders anything it did not just add. A content id already in the playlist is
  counted as already-present and left untouched.
- **Readback-verified.** After committing and closing the write session, a
  brand-new `Rekordbox6Database` is opened against the same file to confirm the
  playlist exists with every intended content id present. This proves the write
  reached disk, not just an in-memory session. A failed readback is *reported*
  (`readback_ok=False`), never raised, so the caller can tell the DJ which
  backup to restore (spec.md US3 scenario 7) instead of crashing.

`Rekordbox6Database` is imported directly from `pyrekordbox.db6.database` and
referenced as a module global on purpose: the readback-failure test monkeypatches
`companion.rb.writer.Rekordbox6Database` to simulate a write that did not
persist, and both the write-session open and the readback open must resolve
through that patchable name.

`configure_logging()` (T018) is called at import, after the `pyrekordbox`
import, following `rb/reader.py`'s precedent: `pyrekordbox/logger.py` attaches
its own raw, non-redacting handler as an import side effect, so redaction must
be (re)installed afterwards, before this module ever drives pyrekordbox. It is
idempotent.
"""

from dataclasses import dataclass
from pathlib import Path

from pyrekordbox.db6.database import Rekordbox6Database

from companion.logging import configure_logging, get_logger

configure_logging()

_logger = get_logger(__name__)


@dataclass(frozen=True)
class WriteResult:
    """The outcome of one `apply_playlist` call.

    `rb_playlist_id` is the id of the created-or-updated Target Playlist (a new
    id when `created` is True, the reused id otherwise). `tracks_added` counts
    genuinely new `DjmdSongPlaylist` rows written; `tracks_already_present`
    counts intended content ids skipped because they were already in the
    playlist (add-only). `readback_ok` is the verdict of the post-write reopen:
    True only when the playlist and every intended content id were found.
    """

    rb_playlist_id: str
    created: bool
    tracks_added: int
    tracks_already_present: int
    readback_ok: bool


def _dedupe_preserving_order(content_ids: list[str]) -> list[str]:
    """The intended content ids with duplicates removed, first occurrence kept.

    A content id repeated in the caller's list must only ever be added once
    (US3: a track accepted twice is still one playlist entry)."""
    seen: set[str] = set()
    unique: list[str] = []
    for content_id in content_ids:
        if content_id not in seen:
            seen.add(content_id)
            unique.append(content_id)
    return unique


def apply_playlist(
    db_path: Path,
    rb_playlist_id: str | None,
    playlist_name: str,
    rb_content_ids: list[str],
) -> WriteResult:
    """Ensure the Target Playlist named `playlist_name` contains every id in
    `rb_content_ids`, add-only, then verify by readback.

    `rb_playlist_id` is `None` on first apply (a new playlist is created at the
    root of the tree) or the previously-known id on re-apply. If a known id no
    longer resolves to a playlist (the DJ deleted the Target Playlist inside
    Rekordbox since the last apply, spec.md US3 scenario 5), it is treated as a
    first apply: a new playlist is created and `created` is True, so the caller
    can report that it was recreated.

    Never raises on a failed readback: returns `WriteResult(readback_ok=False)`
    so the caller can surface it to the DJ (spec.md US3 scenario 7)."""
    intended_ids = _dedupe_preserving_order(rb_content_ids)

    db = Rekordbox6Database(path=str(db_path))
    try:
        existing_playlist = (
            db.get_playlist(ID=rb_playlist_id) if rb_playlist_id is not None else None
        )
        created = existing_playlist is None

        if created:
            playlist = db.create_playlist(playlist_name, parent=None)
            already_present_ids: set[str] = set()
        else:
            playlist = existing_playlist
            # The DJ's explicit intent on this call, applied to the one
            # playlist this module already owns (it created it on a
            # previous apply) -- not "editing something it didn't create"
            # (FR-017), and without this the companion's own record
            # (PlaylistLink.rb_playlist_name) would silently drift from
            # the real Rekordbox playlist's name (review finding).
            if playlist.Name != playlist_name:
                playlist.Name = playlist_name
            already_present_ids = {song.ContentID for song in playlist.Songs}

        tracks_added = 0
        tracks_already_present = 0
        for content_id in intended_ids:
            if content_id in already_present_ids:
                tracks_already_present += 1
                continue
            db.add_to_playlist(playlist, content_id)
            already_present_ids.add(content_id)
            tracks_added += 1

        db.commit()
        result_playlist_id = str(playlist.ID)
    finally:
        db.close()

    readback_ok = _readback_ok(db_path, result_playlist_id, intended_ids)

    _logger.info(
        "rekordbox playlist write applied",
        # Nested under one field: `created` (and other names) collide with
        # reserved `LogRecord` attributes if passed as top-level `extra` keys.
        extra={
            "write": {
                "rb_playlist_id": result_playlist_id,
                "created": created,
                "tracks_added": tracks_added,
                "tracks_already_present": tracks_already_present,
                "readback_ok": readback_ok,
            }
        },
    )

    return WriteResult(
        rb_playlist_id=result_playlist_id,
        created=created,
        tracks_added=tracks_added,
        tracks_already_present=tracks_already_present,
        readback_ok=readback_ok,
    )


@dataclass(frozen=True)
class NodeSpec:
    """One folder or playlist to write in an `apply_structure` batch.

    `node_id` is the companion app's own `structure_node.id`, carried through
    untouched so the caller can correlate a `NodeWriteResult` back to the row
    it came from -- it is never a Rekordbox id and never confused with one.
    `parent_node_id` references another `NodeSpec.node_id` in the SAME call's
    list (or `None` for a root node); `apply_structure` resolves it to the real
    Rekordbox parent id itself, never trusting the caller's list order.
    `rb_ref` is the real Rekordbox folder/playlist id from a previous apply (the
    same id `apply_playlist` returns), or `None` on first apply.
    `rb_content_ids` is only meaningful for `kind == "playlist"`; folders carry
    an empty list.
    """

    node_id: int
    kind: str  # folder, playlist
    name: str
    parent_node_id: int | None
    rb_ref: str | None
    rb_content_ids: list[str]


@dataclass(frozen=True)
class NodeWriteResult:
    """The outcome of writing one `NodeSpec`.

    `rb_ref` is the real Rekordbox id of the created-or-reused folder/playlist
    (a new id when `created` is True, the reused id otherwise). For a folder,
    `tracks_added`/`tracks_already_present` are always `0`; `readback_ok` still
    applies and verifies the folder itself is reachable by the post-write
    reopen. For a playlist they carry the add-only diff, the same semantics as
    `WriteResult`.
    """

    node_id: int
    rb_ref: str
    created: bool
    tracks_added: int
    tracks_already_present: int
    readback_ok: bool


def apply_structure(db_path: Path, nodes: list[NodeSpec]) -> list[NodeWriteResult]:
    """Apply a whole folder/playlist tree in one open/write/commit/close cycle,
    then verify every node by a single readback reopen (FR-018, FR-035).

    Mirrors `apply_playlist`'s safety discipline for a tree instead of a single
    root playlist: one `Rekordbox6Database` write session for the whole batch,
    add-only per playlist node, one brand-new session at the end to confirm the
    committed writes reached disk. Never raises on a failed readback -- reports
    `readback_ok=False` per node so the caller can tell the DJ which backup to
    restore (spec.md US3 scenario 7), never crashes the apply.

    A node's real Rekordbox parent id must exist before the node itself can be
    created, and `nodes` is a flat, unordered list. `apply_structure` resolves
    this topologically itself: it repeatedly processes any node whose parent is
    already resolved (root, or handled in an earlier pass), bounded to at most
    `len(nodes)` passes. A leftover node whose declared parent never resolves
    (a cyclic or dangling `parent_node_id`) can only come from a caller bug --
    the API layer always passes a valid tree from the database -- so it is
    raised as a `ValueError` rather than silently looping forever.
    """
    intended_by_node = {
        node.node_id: _dedupe_preserving_order(node.rb_content_ids)
        for node in nodes
        if node.kind == "playlist"
    }
    resolved_rb_ref: dict[int, str] = {}
    written: dict[int, tuple[str, bool, int, int]] = {}

    db = Rekordbox6Database(path=str(db_path))
    try:
        pending = list(nodes)
        for _pass in range(len(nodes)):
            if not pending:
                break
            still_pending: list[NodeSpec] = []
            progressed = False
            for node in pending:
                if node.parent_node_id is not None and node.parent_node_id not in resolved_rb_ref:
                    still_pending.append(node)
                    continue
                parent_rb_ref = (
                    resolved_rb_ref[node.parent_node_id]
                    if node.parent_node_id is not None
                    else None
                )
                outcome = _write_node(db, node, parent_rb_ref, intended_by_node)
                written[node.node_id] = outcome
                resolved_rb_ref[node.node_id] = outcome[0]
                progressed = True
            pending = still_pending
            if not progressed:
                break
        if pending:
            raise ValueError(
                "apply_structure could not resolve parents for nodes "
                f"{[node.node_id for node in pending]} (cyclic or dangling parent_node_id)"
            )

        db.commit()
    finally:
        db.close()

    readback_by_node = _readback_structure(db_path, nodes, written, intended_by_node)

    results = [
        NodeWriteResult(
            node_id=node.node_id,
            rb_ref=written[node.node_id][0],
            created=written[node.node_id][1],
            tracks_added=written[node.node_id][2],
            tracks_already_present=written[node.node_id][3],
            readback_ok=readback_by_node[node.node_id],
        )
        for node in nodes
    ]

    _logger.info(
        "rekordbox structure write applied",
        extra={
            "write": {
                "nodes": len(nodes),
                "created": sum(1 for r in results if r.created),
                "tracks_added": sum(r.tracks_added for r in results),
                "readback_ok": all(r.readback_ok for r in results),
            }
        },
    )

    return results


def _write_node(
    db: Rekordbox6Database,
    node: NodeSpec,
    parent_rb_ref: str | None,
    intended_by_node: dict[int, list[str]],
) -> tuple[str, bool, int, int]:
    """Create-or-reuse one folder/playlist under `parent_rb_ref` (a real
    Rekordbox id, or `None` at the tree root) and, for a playlist, apply its
    add-only track diff. Returns `(rb_ref, created, tracks_added,
    tracks_already_present)`; folders always report `0` for both counts.

    Same reuse/recreate rule as `apply_playlist`: a `rb_ref` that no longer
    resolves (the DJ deleted the folder/playlist inside Rekordbox since the
    last apply) is treated as a first apply -- created fresh, `created=True`.
    The defensive rename-sync mirrors `apply_playlist`'s; in practice it is a
    no-op, since `structures.update_node` rename-locks a node once its `rb_ref`
    is set, so an already-owned node's name already matches Rekordbox.
    """
    existing = db.get_playlist(ID=node.rb_ref) if node.rb_ref is not None else None
    created = existing is None

    if node.kind == "folder":
        if created:
            obj = db.create_playlist_folder(node.name, parent=parent_rb_ref)
        else:
            obj = existing
            if obj.Name != node.name:
                obj.Name = node.name
        return str(obj.ID), created, 0, 0

    if created:
        obj = db.create_playlist(node.name, parent=parent_rb_ref)
        already_present_ids: set[str] = set()
    else:
        obj = existing
        if obj.Name != node.name:
            obj.Name = node.name
        already_present_ids = {song.ContentID for song in obj.Songs}

    tracks_added = 0
    tracks_already_present = 0
    for content_id in intended_by_node[node.node_id]:
        if content_id in already_present_ids:
            tracks_already_present += 1
            continue
        db.add_to_playlist(obj, content_id)
        already_present_ids.add(content_id)
        tracks_added += 1

    return str(obj.ID), created, tracks_added, tracks_already_present


def _readback_structure(
    db_path: Path,
    nodes: list[NodeSpec],
    written: dict[int, tuple[str, bool, int, int]],
    intended_by_node: dict[int, list[str]],
) -> dict[int, bool]:
    """Open one fresh database against the same file and verify every node
    individually: a folder or playlist exists by its final `rb_ref`, and for a
    playlist every intended content id is present.

    One reopen for the whole batch (not one per node), but each node's verdict
    is independent -- a readback failure on one deeply-nested playlist never
    marks an unrelated sibling `readback_ok=True`, or vice versa. Mirrors
    `_readback_ok`: the brand-new instance reads from disk, proving the
    committed writes persisted rather than lingering in the write session's
    memory."""
    verdicts: dict[int, bool] = {}
    reopened = Rekordbox6Database(path=str(db_path))
    try:
        for node in nodes:
            rb_ref = written[node.node_id][0]
            obj = reopened.get_playlist(ID=rb_ref)
            if obj is None:
                verdicts[node.node_id] = False
                continue
            if node.kind == "folder":
                verdicts[node.node_id] = True
                continue
            present_ids = {song.ContentID for song in obj.Songs}
            verdicts[node.node_id] = set(intended_by_node[node.node_id]).issubset(present_ids)
    finally:
        reopened.close()
    return verdicts


def _readback_ok(db_path: Path, rb_playlist_id: str, intended_ids: list[str]) -> bool:
    """Open a fresh database against the same file and confirm the playlist
    exists with every intended content id present.

    The brand-new instance is the whole point: it reads from disk, proving the
    committed write persisted rather than lingering only in the write session's
    memory."""
    reopened = Rekordbox6Database(path=str(db_path))
    try:
        playlist = reopened.get_playlist(ID=rb_playlist_id)
        if playlist is None:
            return False
        present_ids = {song.ContentID for song in playlist.Songs}
        return set(intended_ids).issubset(present_ids)
    finally:
        reopened.close()
