"""SQLAlchemy models for the companion-owned data/app.sqlite store.

Never confused with `rb/` (Rekordbox's master.db): every table here is
app-side state, per data-model.md.
"""

from datetime import datetime

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


class AppConfig(Base):
    """Key/value config: paths, pinned Rekordbox version, auto-match bar
    overrides if ever needed (data-model.md). A missing key means "use the
    default"; there is no NULL-value state, so absence, not NULL, is how a
    config entry says "not overridden"."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
