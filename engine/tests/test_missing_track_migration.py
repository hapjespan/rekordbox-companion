"""T037: the missing_track Alembic migration (moved here from T056, build
finding: reject spawns a real row, FR-012, before User Story 4 exists)."""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_COLUMNS = {
    "id",
    "sync_track_id",
    "itunes_track_id",
    "itunes_url_auto",
    "itunes_url_chosen",
    "status",
    "resolved_at",
}


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_the_missing_track_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "missing_track" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("missing_track")}
    assert columns == _EXPECTED_COLUMNS


def test_downgrade_removes_only_the_missing_track_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", "855efacd231b")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "missing_track" not in tables
    assert "sync_track" in tables
