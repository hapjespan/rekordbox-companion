"""T010: the app_config Alembic migration creates and reverses the table."""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_the_app_config_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "app_config" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("app_config")}
    assert columns == {"key", "value"}


def test_downgrade_base_removes_the_app_config_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", "base")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "app_config" not in inspector.get_table_names()
