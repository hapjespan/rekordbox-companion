"""Structure/node tree CRUD, Suggestions, tracks, dismissals and Apply
(contracts/api.md "Profiles and structures", FR-032/FR-033/FR-034/FR-035/FR-018).

Apply (`POST /api/structures/{id}/apply`, T086, `[complexity: high]`) reuses
the guarded write path from US3 (`rb/writer.py` + `rb/guard.py` +
`rb/backup.py`): the same guard -> backup -> write -> write_log ->
`apply_done` sequence `api/sync.py`'s own apply endpoint uses, calling
`writer.apply_structure` (a whole folder/playlist tree, not a single flat
playlist) instead of `writer.apply_playlist`.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from companion.api import events
from companion.api.collection import _MAX_LIMIT, _page_body
from companion.bookings.models import suggestions_for_node
from companion.config import BACKUP_DIR
from companion.db.models import (
    BookingProfile,
    BookingProfileGenreTag,
    Structure,
    StructureNode,
    StructureTrack,
    SuggestionDismissal,
    WriteLog,
)
from companion.db.session import get_db
from companion.rb import backup, guard, reader, writer

router = APIRouter()


def _utcnow() -> datetime:
    # Naive UTC: one clock, one machine (same convention as
    # integrations.spotify._utcnow -- kept local rather than importing a
    # private cross-module helper).
    return datetime.now(UTC).replace(tzinfo=None)


def _structure_dict(structure: Structure) -> dict:
    return {
        "id": structure.id,
        "name": structure.name,
        "booking_profile_id": structure.booking_profile_id,
        "created_at": structure.created_at.isoformat(),
        "last_applied_at": structure.last_applied_at.isoformat()
        if structure.last_applied_at
        else None,
    }


def _node_dict(node: StructureNode) -> dict:
    return {
        "id": node.id,
        "structure_id": node.structure_id,
        "parent_id": node.parent_id,
        "kind": node.kind,
        "name": node.name,
        "position": node.position,
        "set_phase": node.set_phase,
        "rb_ref": node.rb_ref,
    }


def _get_structure_or_404(db: Session, structure_id: int) -> Structure:
    structure = db.get(Structure, structure_id)
    if structure is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "structure_not_found",
                "message": f"no Structure with id {structure_id}",
            },
        )
    return structure


def _get_node_or_404(db: Session, structure_id: int, node_id: int) -> StructureNode:
    node = db.get(StructureNode, node_id)
    if node is None or node.structure_id != structure_id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "node_not_found",
                "message": f"no node {node_id} in Structure {structure_id}",
            },
        )
    return node


class StructureBody(BaseModel):
    name: str
    booking_profile_id: int | None = None


@router.get("/structures")
def list_structures(db: Session = Depends(get_db)):
    structures = db.query(Structure).order_by(Structure.name).all()
    return [_structure_dict(s) for s in structures]


@router.post("/structures")
def create_structure(body: StructureBody, db: Session = Depends(get_db)):
    structure = Structure(
        name=body.name, booking_profile_id=body.booking_profile_id, created_at=_utcnow()
    )
    db.add(structure)
    db.commit()
    return _structure_dict(structure)


@router.put("/structures/{structure_id}")
def update_structure(structure_id: int, body: StructureBody, db: Session = Depends(get_db)):
    structure = _get_structure_or_404(db, structure_id)
    structure.name = body.name
    structure.booking_profile_id = body.booking_profile_id
    db.commit()
    return _structure_dict(structure)


@router.delete("/structures/{structure_id}")
def delete_structure(structure_id: int, db: Session = Depends(get_db)):
    structure = _get_structure_or_404(db, structure_id)
    node_ids = [n.id for n in db.query(StructureNode.id).filter_by(structure_id=structure_id).all()]
    db.query(StructureTrack).filter(StructureTrack.node_id.in_(node_ids)).delete(
        synchronize_session=False
    )
    db.query(SuggestionDismissal).filter(SuggestionDismissal.node_id.in_(node_ids)).delete(
        synchronize_session=False
    )
    db.query(StructureNode).filter_by(structure_id=structure_id).delete()
    db.delete(structure)
    db.commit()
    return {"deleted": True}


class NodeBody(BaseModel):
    kind: str
    name: str
    parent_id: int | None = None
    position: int
    set_phase: str | None = None


@router.get("/structures/{structure_id}/nodes")
def list_nodes(structure_id: int, db: Session = Depends(get_db)):
    # Not in contracts/api.md's table explicitly, but required for any
    # client to render/edit a tree at all -- the same "fetch one resource
    # with its children" shape as GET /api/sync/sessions/{id}, just as its
    # own endpoint rather than nested in GET /api/structures/{id} (T087/T088
    # build finding).
    _get_structure_or_404(db, structure_id)
    nodes = (
        db.query(StructureNode)
        .filter_by(structure_id=structure_id)
        .order_by(StructureNode.position)
        .all()
    )
    return [_node_dict(n) for n in nodes]


@router.post("/structures/{structure_id}/nodes")
def create_node(structure_id: int, body: NodeBody, db: Session = Depends(get_db)):
    _get_structure_or_404(db, structure_id)
    node = StructureNode(
        structure_id=structure_id,
        parent_id=body.parent_id,
        kind=body.kind,
        name=body.name,
        position=body.position,
        set_phase=body.set_phase,
    )
    db.add(node)
    db.commit()
    return _node_dict(node)


def _validate_new_parent(
    db: Session, structure_id: int, node: StructureNode, parent_id: int | None
) -> None:
    """Refuse a re-parent that would corrupt the tree, at edit time.

    Three ways it can: a parent from another Structure, the node itself, or
    one of its own descendants. All three used to be accepted here and only
    surfaced from `writer.apply_structure`'s cycle detection -- as a 500,
    AFTER `backup.create()` had already run. A 422 before anything is stored
    keeps the guarded write path from ever seeing an impossible tree.
    """
    if parent_id is None:
        return
    parent = db.get(StructureNode, parent_id)
    if parent is None or parent.structure_id != structure_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_parent",
                "message": f"no node {parent_id} in Structure {structure_id}",
                "field": "parent_id",
            },
        )

    # Walk up from the proposed parent: meeting the node itself means the
    # node would become its own ancestor. `seen` only guards against a
    # pre-existing cycle in stored data, so the walk can't loop forever.
    seen: set[int] = set()
    current: StructureNode | None = parent
    while current is not None and current.id not in seen:
        if current.id == node.id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "parent_cycle",
                    "message": "a node cannot be moved inside itself or one of its own children",
                    "field": "parent_id",
                },
            )
        seen.add(current.id)
        current = db.get(StructureNode, current.parent_id) if current.parent_id else None


class NodeUpdateBody(BaseModel):
    name: str
    parent_id: int | None = None
    position: int
    set_phase: str | None = None


@router.put("/structures/{structure_id}/nodes/{node_id}")
def update_node(
    structure_id: int, node_id: int, body: NodeUpdateBody, db: Session = Depends(get_db)
):
    node = _get_node_or_404(db, structure_id, node_id)
    # FR-032 edge case: a node already applied to Rekordbox is rename-locked
    # -- its name is owned by Rekordbox from the first Apply on. Every other
    # field (parent_id/position/set_phase, i.e. moving and nesting) stays
    # editable; only the name is locked.
    if node.rb_ref is not None and body.name != node.name:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "node_name_locked",
                "message": "this node was already applied to Rekordbox; rename it there instead",
                "field": "name",
            },
        )
    _validate_new_parent(db, structure_id, node, body.parent_id)
    node.name = body.name
    node.parent_id = body.parent_id
    node.position = body.position
    node.set_phase = body.set_phase
    db.commit()
    return _node_dict(node)


@router.delete("/structures/{structure_id}/nodes/{node_id}")
def delete_node(structure_id: int, node_id: int, db: Session = Depends(get_db)):
    _get_node_or_404(db, structure_id, node_id)
    db.query(StructureTrack).filter_by(node_id=node_id).delete()
    db.query(SuggestionDismissal).filter_by(node_id=node_id).delete()
    db.query(StructureNode).filter_by(id=node_id).delete()
    db.commit()
    return {"deleted": True}


@router.get("/structures/{structure_id}/nodes/{node_id}/suggestions")
def get_suggestions(
    structure_id: int,
    node_id: int,
    request: Request,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    structure = _get_structure_or_404(db, structure_id)
    _get_node_or_404(db, structure_id, node_id)

    genre_tags: list[str] = []
    bpm_min = bpm_max = None
    if structure.booking_profile_id is not None:
        genre_tags = [
            t[0]
            for t in db.query(BookingProfileGenreTag.tag)
            .filter_by(profile_id=structure.booking_profile_id)
            .all()
        ]
        row = db.get(BookingProfile, structure.booking_profile_id)
        if row is not None:
            bpm_min, bpm_max = row.bpm_min, row.bpm_max

    entries = request.app.state.collection_index.entries
    suggestions, _ = suggestions_for_node(
        db, entries, node_id, genre_tags, bpm_min, bpm_max, limit=limit
    )
    return [
        {
            "rb_content_id": s.rb_content_id,
            "artist": s.artist,
            "title": s.title,
            "bpm": s.bpm,
            "play_count": s.play_count,
            "already_in_playlist": s.already_in_playlist,
        }
        for s in suggestions
    ]


@router.get("/structures/{structure_id}/nodes/{node_id}/tracks")
def get_node_tracks(
    structure_id: int,
    node_id: int,
    request: Request,
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """The node's own stored tracks (`structure_track`), in their stored
    `position` order -- the same `{total, items: [CollectionTrack]}` shape
    `GET /api/collection` and `GET /api/playlists/{id}/tracks` return, so the
    client reuses one row type and one table.

    Deliberately NOT the Suggestions query (`GET .../suggestions`): that one
    is filtered by the structure's profile (genre tags, BPM) and ranked by
    play count, so a member the filter excludes -- or a manually-added track
    outside the profile -- would be invisible there. This endpoint is the
    only way to see everything a node actually holds, in the order the DJ
    built it.

    Every track field is served from the in-memory index (ADR 0012), same as
    the playlist-tracks endpoint, which is why an unindexed collection is a
    documented 409 rather than an empty page, and why a `structure_track` row
    the index no longer knows (removed from Rekordbox since the last scan) is
    skipped rather than rendered as an empty row.
    """
    _get_structure_or_404(db, structure_id)
    _get_node_or_404(db, structure_id, node_id)

    entries_by_id = {e.rb_content_id: e for e in request.app.state.collection_index.entries}
    if not entries_by_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "collection_not_indexed",
                "message": "the collection has not been indexed yet; "
                "run POST /api/collection/reindex first",
            },
        )

    track_rows = (
        db.query(StructureTrack).filter_by(node_id=node_id).order_by(StructureTrack.position).all()
    )
    entries = [
        entries_by_id[row.rb_content_id] for row in track_rows if row.rb_content_id in entries_by_id
    ]
    return _page_body(db, entries, limit, offset)


class TrackBody(BaseModel):
    rb_content_id: str
    origin: str = "suggestion"


@router.post("/structures/{structure_id}/nodes/{node_id}/tracks")
def add_track(structure_id: int, node_id: int, body: TrackBody, db: Session = Depends(get_db)):
    _get_node_or_404(db, structure_id, node_id)
    existing = db.get(StructureTrack, {"node_id": node_id, "rb_content_id": body.rb_content_id})
    if existing is not None:
        return {"added": False}
    # max()+1, not count(): a count would reassign an already-used position
    # once a non-trailing track has been removed (e.g. add A, B; remove A;
    # add C -- count() gives C position 1, colliding with B).
    max_position = db.query(func.max(StructureTrack.position)).filter_by(node_id=node_id).scalar()
    next_position = 0 if max_position is None else max_position + 1
    db.add(
        StructureTrack(
            node_id=node_id,
            rb_content_id=body.rb_content_id,
            position=next_position,
            origin=body.origin,
        )
    )
    db.commit()
    return {"added": True}


@router.delete("/structures/{structure_id}/nodes/{node_id}/tracks/{rb_content_id}")
def remove_track(
    structure_id: int, node_id: int, rb_content_id: str, db: Session = Depends(get_db)
):
    node = _get_node_or_404(db, structure_id, node_id)
    if node.rb_ref is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "node_already_applied",
                "message": "playlist already applied to Rekordbox; remove tracks there instead",
            },
        )
    db.query(StructureTrack).filter_by(node_id=node_id, rb_content_id=rb_content_id).delete()
    db.commit()
    return {"removed": True}


class DismissalBody(BaseModel):
    rb_content_id: str


@router.post("/structures/{structure_id}/nodes/{node_id}/dismissals")
def dismiss_suggestion(
    structure_id: int, node_id: int, body: DismissalBody, db: Session = Depends(get_db)
):
    _get_node_or_404(db, structure_id, node_id)
    existing = db.get(
        SuggestionDismissal, {"node_id": node_id, "rb_content_id": body.rb_content_id}
    )
    if existing is None:
        db.add(SuggestionDismissal(node_id=node_id, rb_content_id=body.rb_content_id))
        db.commit()
    return {"dismissed": True}


def _node_specs_for_structure(db: Session, structure_id: int) -> list[writer.NodeSpec]:
    """Build the flat `NodeSpec` list `writer.apply_structure` resolves into a
    tree: one spec per `structure_node`, its `StructureTrack.rb_content_id`
    rows (playlist nodes only) ordered by `position`. `apply_structure` does
    its own topological ordering, so the query order here is irrelevant."""
    nodes = db.query(StructureNode).filter_by(structure_id=structure_id).all()
    specs = []
    for node in nodes:
        if node.kind == "playlist":
            content_ids = [
                row[0]
                for row in db.query(StructureTrack.rb_content_id)
                .filter_by(node_id=node.id)
                .order_by(StructureTrack.position)
                .all()
            ]
        else:
            content_ids = []
        specs.append(
            writer.NodeSpec(
                node_id=node.id,
                kind=node.kind,
                name=node.name,
                parent_node_id=node.parent_id,
                rb_ref=node.rb_ref,
                rb_content_ids=content_ids,
            )
        )
    return specs


def _node_result_dict(result: writer.NodeWriteResult) -> dict:
    return {
        "node_id": result.node_id,
        "rb_ref": result.rb_ref,
        "created": result.created,
        "tracks_added": result.tracks_added,
        "tracks_already_present": result.tracks_already_present,
        "readback_ok": result.readback_ok,
    }


@router.post("/structures/{structure_id}/apply")
def apply_structure(structure_id: int, db: Session = Depends(get_db)):
    """FR-035/FR-018: guard -> backup -> write -> readback -> write_log ->
    per-node ApplyResult (contracts/api.md), emitting `apply_done` on
    `/api/events`. The exact same guarded write path as
    `sync.apply_sync_session`, calling `writer.apply_structure` for a whole
    folder/playlist tree instead of `writer.apply_playlist` for one playlist.

    A pre-write refusal (guard or backup_failed) is a 409, nothing touched. A
    write whose readback fails is a 200 -- the write and its backup are real,
    only verification didn't confirm every node; `StructureNode.rb_ref` and
    `structure.last_applied_at` are updated only when EVERY node verified, so a
    partially-verified apply never falsely reads as fully owned by Rekordbox.
    """
    _get_structure_or_404(db, structure_id)

    # guard.check() refuses cleanly (version_mismatch) when Rekordbox isn't
    # installed or its db file can't be found, so passing detection.db_path
    # straight through -- even when None -- is safe (same as sync apply).
    detection = reader.detect_rekordbox()
    guard_result = guard.check(detection.db_path)
    if not guard_result.ok:
        raise HTTPException(
            status_code=409,
            detail={"code": guard_result.code, "message": guard_result.message},
        )

    backup_result = backup.create(detection.db_path, BACKUP_DIR)
    if not backup_result.ok:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "backup_failed",
                "message": f"Backup could not be verified: {backup_result.error}",
            },
        )

    node_specs = _node_specs_for_structure(db, structure_id)

    try:
        node_results = writer.apply_structure(detection.db_path, node_specs)
    except Exception as exc:
        # A genuine write failure must still leave an audit trail: the backup
        # already exists, so there needs to be a durable record of where to
        # restore from even though the write never confirmed (same pattern as
        # sync.apply_sync_session).
        db.add(
            WriteLog(
                kind="structure_apply",
                subject_id=structure_id,
                backup_path=str(backup_result.path),
                readback_ok=False,
                detail={"error": str(exc)},
                created_at=_utcnow(),
            )
        )
        db.commit()
        raise

    overall_readback_ok = all(result.readback_ok for result in node_results)

    db.add(
        WriteLog(
            kind="structure_apply",
            subject_id=structure_id,
            backup_path=str(backup_result.path),
            readback_ok=overall_readback_ok,
            detail={"nodes": [_node_result_dict(result) for result in node_results]},
            created_at=_utcnow(),
        )
    )

    # Persist every node's real Rekordbox id, so a re-apply reuses it (add-only,
    # FR-018) and the rename-lock in update_node kicks in. Done per-node
    # regardless of overall readback: the id is real the moment writer created
    # it, and re-running against a stale None would create a duplicate.
    nodes_by_id = {
        node.id: node for node in db.query(StructureNode).filter_by(structure_id=structure_id).all()
    }
    for result in node_results:
        node = nodes_by_id.get(result.node_id)
        if node is not None:
            node.rb_ref = result.rb_ref

    if overall_readback_ok:
        structure = db.get(Structure, structure_id)
        structure.last_applied_at = _utcnow()
    db.commit()

    events.publish(
        "apply_done",
        {
            "structure_id": structure_id,
            "readback_ok": overall_readback_ok,
            "nodes": [_node_result_dict(result) for result in node_results],
        },
    )

    return {
        "nodes": [_node_result_dict(result) for result in node_results],
        "backup_path": str(backup_result.path),
        "readback_ok": overall_readback_ok,
    }
