"""T049: the write_log Alembic migration (built alongside T044/T096's RED
contract tests so they fail on missing behaviour, not a missing import)."""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_COLUMNS = {
    "id",
    "kind",
    "subject_id",
    "backup_path",
    "readback_ok",
    "detail",
    "created_at",
}


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_the_write_log_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "write_log" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("write_log")}
    assert columns == _EXPECTED_COLUMNS


def test_downgrade_removes_only_the_write_log_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", "02cfda8ae0ce")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "write_log" not in tables
    assert "missing_track" in tables
