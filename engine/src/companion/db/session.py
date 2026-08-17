"""SQLAlchemy engine/session for the companion-owned data/app.sqlite store.

Never confused with `rb/` (Rekordbox's master.db, read + guarded writes only,
project rule 1/2): this module owns the companion's own tables exclusively.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the parent of the `engine/` package root.

    Anchored on `engine/pyproject.toml` rather than a fixed parent-count, so
    this keeps working if `db/` ever moves within `engine/src/companion/`.
    """
    for candidate in start.parents:
        if candidate.name == "engine" and (candidate / "pyproject.toml").exists():
            return candidate.parent
    raise RuntimeError(f"could not locate engine/pyproject.toml above {start}")


def default_database_url() -> str:
    data_dir = _find_repo_root(Path(__file__).resolve()) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data_dir / 'app.sqlite'}"


def create_session_factory(database_url: str | None = None):
    """Build a fresh (engine, SessionLocal) pair for the given URL.

    Independent of module-level state on purpose: tests exercise a different
    DATABASE_URL by calling this directly, instead of `importlib.reload`
    mutating process-global objects other imports of this module rely on.
    """
    url = database_url or os.environ.get("DATABASE_URL") or default_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    session_engine = create_engine(url, connect_args=connect_args)
    session_local = sessionmaker(bind=session_engine, autoflush=False, autocommit=False)
    return session_engine, session_local


engine, SessionLocal = create_session_factory()


def get_db():
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
