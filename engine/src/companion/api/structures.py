"""Structure/node tree CRUD, Suggestions, tracks and dismissals
(contracts/api.md "Profiles and structures", FR-032/FR-033/FR-034).

Apply (`POST /api/structures/{id}/apply`, T086) is deliberately not in this
module's first cut -- it reuses the guarded write path (`rb/writer.py` +
`rb/guard.py` + `rb/backup.py`) and lands as its own task/commit given the
security-sensitive nature of anything that writes to `master.db` (project
rule 2).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from companion.bookings.models import suggestions_for_node
from companion.db.models import (
    BookingProfile,
    BookingProfileGenreTag,
    Structure,
    StructureNode,
    StructureTrack,
    SuggestionDismissal,
)
from companion.db.session import get_db

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
