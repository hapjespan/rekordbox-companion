"""T074: the enriched_genre/enrichment_state Alembic migration (data-model.md)."""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_ENRICHED_GENRE_COLUMNS = {"id", "rb_content_id", "genre", "source", "updated_at"}
_EXPECTED_ENRICHMENT_STATE_COLUMNS = {"rb_content_id", "status", "attempted_at", "last_source"}


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_the_enrichment_tables(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "enriched_genre" in tables
    assert "enrichment_state" in tables
    assert {c["name"] for c in inspector.get_columns("enriched_genre")} == (
        _EXPECTED_ENRICHED_GENRE_COLUMNS
    )
    assert {c["name"] for c in inspector.get_columns("enrichment_state")} == (
        _EXPECTED_ENRICHMENT_STATE_COLUMNS
    )


def test_downgrade_removes_only_the_enrichment_tables(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", "7c1cc1025c1f")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "enriched_genre" not in tables
    assert "enrichment_state" not in tables
    assert "write_log" in tables
