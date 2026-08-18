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


class AppConfig(Base):
    """Key/value config: paths, pinned Rekordbox version, auto-match bar
    overrides if ever needed (data-model.md). A missing key means "use the
    default"; there is no NULL-value state, so absence, not NULL, is how a
    config entry says "not overridden"."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
