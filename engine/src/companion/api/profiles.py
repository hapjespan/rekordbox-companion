"""Booking Profile CRUD (contracts/api.md "Profiles and structures", FR-031).

`slug` is server-derived from `name`, never client input: the request shape
contracts/api.md documents (`name, bpm range, genre_tags`) has no `slug`
field, and the four seeded profiles (T081) already establish the
lowercase-name convention this follows.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from companion.db.models import BookingProfile, BookingProfileGenreTag, Structure
from companion.db.session import get_db

router = APIRouter()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "profile"


def _profile_dict(db: Session, profile: BookingProfile) -> dict:
    tags = (
        db.query(BookingProfileGenreTag.tag).filter_by(profile_id=profile.id).order_by("tag").all()
    )
    return {
        "id": profile.id,
        "name": profile.name,
        "slug": profile.slug,
        "bpm_min": profile.bpm_min,
        "bpm_max": profile.bpm_max,
        "genre_tags": [t[0] for t in tags],
    }


def _set_genre_tags(db: Session, profile_id: int, tags: list[str]) -> None:
    db.query(BookingProfileGenreTag).filter_by(profile_id=profile_id).delete()
    for tag in tags:
        db.add(BookingProfileGenreTag(profile_id=profile_id, tag=tag))


def _get_profile_or_404(db: Session, profile_id: int) -> BookingProfile:
    profile = db.get(BookingProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "profile_not_found",
                "message": f"no Booking Profile with id {profile_id}",
            },
        )
    return profile


class ProfileBody(BaseModel):
    name: str
    bpm_min: int | None = None
    bpm_max: int | None = None
    genre_tags: list[str] = []


@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    profiles = db.query(BookingProfile).order_by(BookingProfile.name).all()
    return [_profile_dict(db, p) for p in profiles]


def _reject_duplicate_name(
    db: Session, name: str, slug: str, *, exclude_id: int | None = None
) -> None:
    """`name` and `slug` are both unique columns and `slug` is derived from
    `name`, so either collision is one and the same user-visible problem: the
    name is taken. Without this check the unique index raises IntegrityError,
    i.e. a 500 where the contract promises a 422 field-naming error."""
    query = db.query(BookingProfile.id).filter(
        (BookingProfile.name == name) | (BookingProfile.slug == slug)
    )
    if exclude_id is not None:
        query = query.filter(BookingProfile.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "duplicate_name",
                "message": f"a profile named {name!r} already exists",
                "field": "name",
            },
        )


@router.post("/profiles")
def create_profile(body: ProfileBody, db: Session = Depends(get_db)):
    _reject_duplicate_name(db, body.name, _slugify(body.name))
    profile = BookingProfile(
        name=body.name, slug=_slugify(body.name), bpm_min=body.bpm_min, bpm_max=body.bpm_max
    )
    db.add(profile)
    db.flush()
    _set_genre_tags(db, profile.id, body.genre_tags)
    db.commit()
    return _profile_dict(db, profile)


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileBody, db: Session = Depends(get_db)):
    profile = _get_profile_or_404(db, profile_id)
    slug = _slugify(body.name)
    _reject_duplicate_name(db, body.name, slug, exclude_id=profile_id)
    profile.name = body.name
    # The slug is server-derived from the name, so it follows a rename: a
    # renamed profile whose slug still spells the old name is stale data.
    profile.slug = slug
    profile.bpm_min = body.bpm_min
    profile.bpm_max = body.bpm_max
    _set_genre_tags(db, profile.id, body.genre_tags)
    db.commit()
    return _profile_dict(db, profile)


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = _get_profile_or_404(db, profile_id)
    # Structures keep existing, just lose the profile link: deleting a
    # profile is not a reason to delete a DJ's hand-designed Structure
    # (ADR 0008).
    db.query(Structure).filter_by(booking_profile_id=profile_id).update(
        {"booking_profile_id": None}
    )
    db.query(BookingProfileGenreTag).filter_by(profile_id=profile_id).delete()
    db.delete(profile)
    db.commit()
    return {"deleted": True}
