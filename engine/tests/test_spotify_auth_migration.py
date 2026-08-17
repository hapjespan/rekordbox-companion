"""T026: the spotify_auth Alembic migration creates and reverses the table."""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_COLUMNS = {
    "id",
    "access_token",
    "refresh_token",
    "token_expires_at",
    "account_id",
    "display_name",
    "product",
}


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_the_spotify_auth_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "spotify_auth" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("spotify_auth")}
    assert columns == _EXPECTED_COLUMNS


def test_downgrade_removes_only_the_spotify_auth_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    # Target this migration's own revision explicitly, not "-1": head has
    # grown further migrations since (T027), so "-1 from head" no longer
    # lands on spotify_auth's own down_revision (T027 build finding).
    _alembic(tmp_path, monkeypatch, "downgrade", "db38228b032d")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "spotify_auth" not in tables
    assert "app_config" in tables
