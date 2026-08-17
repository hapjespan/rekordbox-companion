"""T009: SQLAlchemy engine/session setup, overridable via COMPANION_DATABASE_URL.

Uses `create_session_factory` directly rather than `importlib.reload`, so
these tests never mutate the process-global `companion.db.session.engine`
other tests or modules import (review finding: reload-based state leaks
across test order and pytest-xdist workers).
"""

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

from companion.db.session import Base, create_session_factory, default_database_url


def test_create_session_factory_honours_the_given_url():
    engine, _ = create_session_factory("sqlite:///:memory:")
    assert str(engine.url) == "sqlite:///:memory:"


def test_sessionlocal_produces_a_working_session():
    _, session_local = create_session_factory("sqlite:///:memory:")
    with session_local() as db:
        assert db.execute(text("SELECT 1")).scalar() == 1


def test_base_is_a_declarative_base_models_can_subclass():
    assert issubclass(Base, DeclarativeBase)


def test_default_database_url_points_at_the_repo_data_directory():
    url = default_database_url()
    assert url.startswith("sqlite:///")
    assert url.endswith("data/app.sqlite")


def test_create_session_factory_falls_back_to_database_url_env(monkeypatch):
    monkeypatch.setenv("COMPANION_DATABASE_URL", "sqlite:///:memory:")
    engine, _ = create_session_factory()
    assert str(engine.url) == "sqlite:///:memory:"


def test_create_session_factory_ignores_the_generic_database_url_env(monkeypatch):
    # The repo's own .env sets DATABASE_URL to the reserved central Postgres
    # database (unused in v1, plan.md); config.py loads that .env file, so a
    # plain DATABASE_URL must never leak into this SQLite store (regression:
    # config.py's load_dotenv made this collision live during phase 6 build).
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/should-not-be-used")
    monkeypatch.delenv("COMPANION_DATABASE_URL", raising=False)
    engine, _ = create_session_factory()
    assert str(engine.url).startswith("sqlite:///")
