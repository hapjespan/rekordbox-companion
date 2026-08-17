"""SQLAlchemy engine/session for the companion-owned data/app.sqlite store.

Never confused with `rb/` (Rekordbox's master.db, read + guarded writes only,
project rule 1/2): this module owns the companion's own tables exclusively.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from companion.config import DATA_DIR


class Base(DeclarativeBase):
    pass


def default_database_url() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATA_DIR / 'app.sqlite'}"


def create_session_factory(database_url: str | None = None):
    """Build a fresh (engine, SessionLocal) pair for the given URL.

    Independent of module-level state on purpose: tests exercise a different
    COMPANION_DATABASE_URL by calling this directly, instead of `importlib.reload`
    mutating process-global objects other imports of this module rely on.
    """
    url = database_url or os.environ.get("COMPANION_DATABASE_URL") or default_database_url()
    engine_kwargs = {}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            # SQLAlchemy's default pooling gives sqlite:///:memory: one
            # connection PER THREAD, so a request FastAPI runs off the main
            # thread (run_in_threadpool, every sync route handler) would
            # silently get a brand-new, empty database. StaticPool shares
            # the one open connection across every thread instead.
            engine_kwargs["poolclass"] = StaticPool
    session_engine = create_engine(url, **engine_kwargs)
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
