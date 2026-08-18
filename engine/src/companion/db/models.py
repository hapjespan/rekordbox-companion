"""SQLAlchemy models for the companion-owned data/app.sqlite store.

Never confused with `rb/` (Rekordbox's master.db): every table here is
app-side state, per data-model.md.
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from companion.db.session import Base


class SpotifyAuth(Base):
    """The operator's single Spotify session (data-model.md `spotify_auth`).

    Single row, `id` always 1: one operator, one machine, one Spotify account
    (constraints.md load line). `access_token`/`refresh_token` are PII held on
    the operator's own machine under consent (pii-inventory.md #1) and are
    NEVER logged (constraints.md NIS2 / ASVS V3); the redacting formatter in
    `companion.logging` catches them by field name, but this integration also
    simply never logs them. Deleted whole on disconnect -- that delete IS the
    AVG/GDPR deletion path (pii-inventory.md), so the row must actually be
    removed, not flagged inactive.
    """

    __tablename__ = "spotify_auth"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1
    access_token: Mapped[str]
    refresh_token: Mapped[str]
    # Stored as naive UTC (see integrations/spotify.py `_utcnow`): one clock,
    # one machine, so a single convention avoids tz-aware/naive comparison bugs.
    token_expires_at: Mapped[datetime]
    account_id: Mapped[str]
    display_name: Mapped[str | None]
    product: Mapped[str | None]  # `premium` gates embedded playback (ADR 0009)


class PlaylistLink(Base):
    """The Target Playlist lineage (FR-010, FR-019, ADR 0006; data-model.md).

    One row per Spotify playlist URL ever applied, so a re-sync re-uses the
    same lineage instead of creating a second, unrelated Target Playlist
    (FR-010). Moved here from its original task (T049) because `sync_session`
    FKs into it and `POST /api/sync/sessions` (T028, User Story 1) needs it
    for FR-010's lineage reuse -- both land before User Story 3, where T049
    otherwise would have created this table (T027 build finding).
    """

    __tablename__ = "playlist_link"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Parsed server-side from the pasted URL; the raw URL itself is never
    # stored (constraints.md ASVS V5).
    spotify_playlist_id: Mapped[str] = mapped_column(unique=True)
    rb_playlist_id: Mapped[str | None]  # NULL until the first Apply
    rb_playlist_name: Mapped[str]  # last name written
    created_at: Mapped[datetime]
    last_applied_at: Mapped[datetime | None]


class SyncSession(Base):
    """One Spotify-playlist fetch+match run (data-model.md `sync_session`)."""

    __tablename__ = "sync_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_link_id: Mapped[int] = mapped_column(sa.ForeignKey("playlist_link.id"))
    spotify_snapshot_id: Mapped[str]
    name: Mapped[str]  # playlist name at fetch time
    # fetching -> matching -> ready -> applied; failed from any. A write
    # whose readback verification fails does NOT transition to applied -- it
    # stays ready, reported via the write_log row's backup_path (US3
    # scenario 7, data-model.md).
    status: Mapped[str]
    created_at: Mapped[datetime]


class SyncTrack(Base):
    """One playlist position within a Sync Session (data-model.md `sync_track`).

    One row per playlist POSITION, not per distinct track: a playlist
    containing the same track twice stays visible as two rows (spec edge
    case); Apply is what de-duplicates, not the report.
    """

    __tablename__ = "sync_track"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_session_id: Mapped[int] = mapped_column(sa.ForeignKey("sync_session.id"))
    position: Mapped[int]  # playlist order
    spotify_track_id: Mapped[str | None]  # NULL for local/unavailable tracks
    isrc: Mapped[str | None]
    artist: Mapped[str]
    title: Mapped[str]
    duration_ms: Mapped[int | None]
    # matched, review, missing, rejected, unmatchable. Transitions:
    # review -> matched (accept), review -> rejected (reject, spawns
    # missing_track), missing -> matched (auto, re-sync, FR-023). unmatchable
    # is terminal (no identifiers). matched never transitions away.
    status: Mapped[str]
    rb_content_id: Mapped[str | None]  # set when matched/accepted
    match_score: Mapped[float | None]
    candidates: Mapped[list] = mapped_column(sa.JSON, default=list)  # top 3 for review items
    matched_at: Mapped[datetime | None]


class MissingTrack(Base):
    """A Spotify Track rejected or scored below threshold (data-model.md
    `missing_track`). Moved here from its original task (T056, User Story 4)
    because reject (T037, User Story 2) must spawn a real row the moment it
    happens (FR-012) -- before User Story 4 exists, the same playlist_link-
    ahead-of-T049 pattern from T027 (T036 build finding).
    """

    __tablename__ = "missing_track"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_track_id: Mapped[int] = mapped_column(sa.ForeignKey("sync_track.id"), unique=True)
    itunes_track_id: Mapped[str | None]
    itunes_url_auto: Mapped[str | None]  # best-effort pick (FR-022 keeps it)
    itunes_url_chosen: Mapped[str | None]  # manual override wins when set
    # open -> acquired / ignored; open -> closed via FR-023 auto-match.
    # `ignored` is sticky across re-syncs of the same playlist (US4 scenario 3).
    status: Mapped[str] = mapped_column(default="open")
    resolved_at: Mapped[datetime | None]


class WriteLog(Base):
    """Audit trail for every guarded write to `master.db` (data-model.md
    `write_log`; NIS2 logging, SC-006). T049 (US3): built alongside T044/T096's
    RED contract tests so they fail on missing behaviour (no route yet),
    not a missing model import.
    """

    __tablename__ = "write_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # sync_apply, structure_apply
    subject_id: Mapped[int]  # session id or structure id, per `kind`
    backup_path: Mapped[str]
    readback_ok: Mapped[bool]
    detail: Mapped[dict] = mapped_column(sa.JSON, default=dict)  # counts written, ids created
    created_at: Mapped[datetime]


class AppConfig(Base):
    """Key/value config: paths, pinned Rekordbox version, auto-match bar
    overrides if ever needed (data-model.md). A missing key means "use the
    default"; there is no NULL-value state, so absence, not NULL, is how a
    config entry says "not overridden"."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]


class EnrichedGenre(Base):
    """One genre tag for one track, from one source (data-model.md
    `enriched_genre`). Multiple rows per `rb_content_id` allowed (multiple
    genres per track). `source == "manual"` is the permanent override: any
    track with a manual row is never touched by an enrichment run again
    (FR-028), enforced by `enrichment.source.has_manual_override`.
    """

    __tablename__ = "enriched_genre"

    id: Mapped[int] = mapped_column(primary_key=True)
    rb_content_id: Mapped[str] = mapped_column(index=True)
    genre: Mapped[str]  # normalised lowercase tag
    source: Mapped[str]  # spotify, musicbrainz, manual
    updated_at: Mapped[datetime]


class EnrichmentState(Base):
    """Per-track enrichment queue state (data-model.md `enrichment_state`),
    what makes a run incremental and resumable (ADR 0013): a run only
    processes tracks whose state is missing or `pending`/`failed`, never
    tracks already `done` or `none_found`.
    """

    __tablename__ = "enrichment_state"

    rb_content_id: Mapped[str] = mapped_column(primary_key=True)
    # pending -> done | none_found | failed. failed is retryable (re-enqueued
    # the same as pending); done and none_found are terminal for a run.
    status: Mapped[str] = mapped_column(default="pending")
    attempted_at: Mapped[datetime | None]
    last_source: Mapped[str | None]


class BookingProfile(Base):
    """A named filter preset for Suggestions (data-model.md `booking_profile`,
    FR-031). Seeded rows (horeca, bruiloft, prive, thema) start with no genre
    tags and no BPM range -- ADR 0008/FR-036 forbid the system having an
    opinion about what genres or tempo belong to a booking type; the DJ
    configures each profile themselves.
    """

    __tablename__ = "booking_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    bpm_min: Mapped[int | None]
    bpm_max: Mapped[int | None]


class BookingProfileGenreTag(Base):
    """Many genre tags per profile (data-model.md `booking_profile_genre_tag`)."""

    __tablename__ = "booking_profile_genre_tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(sa.ForeignKey("booking_profile.id"))
    tag: Mapped[str]


class Structure(Base):
    """One designed Booking Structure (data-model.md `structure`, ADR 0008):
    a folder/playlist tree the DJ builds by hand, never generated."""

    __tablename__ = "structure"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    booking_profile_id: Mapped[int | None] = mapped_column(sa.ForeignKey("booking_profile.id"))
    created_at: Mapped[datetime]
    last_applied_at: Mapped[datetime | None]


class StructureNode(Base):
    """One folder or playlist in a Structure's tree (data-model.md
    `structure_node`, FR-032). `rb_ref` is set once Apply creates the real
    Rekordbox folder/playlist for this node, which is what makes a re-apply
    add-only (FR-018) instead of creating duplicates, and what triggers the
    rename-lock (FR-032 edge case: an applied node's name is owned by
    Rekordbox from that point on). `set_phase` is a label shown in the UI
    (vooravond/mid/prime/sluit) -- never logic, per ADR 0008.
    """

    __tablename__ = "structure_node"

    id: Mapped[int] = mapped_column(primary_key=True)
    structure_id: Mapped[int] = mapped_column(sa.ForeignKey("structure.id"))
    parent_id: Mapped[int | None] = mapped_column(sa.ForeignKey("structure_node.id"))
    kind: Mapped[str]  # folder, playlist
    name: Mapped[str]
    position: Mapped[int]
    set_phase: Mapped[str | None]
    rb_ref: Mapped[str | None]


class StructureTrack(Base):
    """One track in a playlist node (data-model.md `structure_track`).
    Composite PK, not a synthetic id: a track appears at most once per
    playlist node, which the PK enforces rather than a separate check.
    `origin` distinguishes a DJ-accepted Suggestion from a manually-added
    track -- both are equally real playlist contents, this is display-only.
    """

    __tablename__ = "structure_track"

    node_id: Mapped[int] = mapped_column(sa.ForeignKey("structure_node.id"), primary_key=True)
    rb_content_id: Mapped[str] = mapped_column(primary_key=True)
    position: Mapped[int]
    origin: Mapped[str]  # suggestion, manual


class SuggestionDismissal(Base):
    """A Suggestion the DJ dismissed for one playlist node (data-model.md
    `suggestion_dismissal`, FR-034): excluded from that node's Suggestions
    forever, since Suggestions are computed fresh every time, never stored.
    Composite PK: dismissing the same track twice for the same node is
    idempotent, not a second row.
    """

    __tablename__ = "suggestion_dismissal"

    node_id: Mapped[int] = mapped_column(sa.ForeignKey("structure_node.id"), primary_key=True)
    rb_content_id: Mapped[str] = mapped_column(primary_key=True)
