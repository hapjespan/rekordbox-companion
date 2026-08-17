"""SQLAlchemy models for the companion-owned data/app.sqlite store.

Never confused with `rb/` (Rekordbox's master.db): every table here is
app-side state, per data-model.md.
"""

from sqlalchemy.orm import Mapped, mapped_column

from companion.db.session import Base


class AppConfig(Base):
    """Key/value config: paths, pinned Rekordbox version, auto-match bar
    overrides if ever needed (data-model.md). A missing key means "use the
    default"; there is no NULL-value state, so absence, not NULL, is how a
    config entry says "not overridden"."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
