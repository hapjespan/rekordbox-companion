"""T081: booking_profile/structure Alembic migration (data-model.md), plus
the seeded profiles (FR-031)."""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_COLUMNS = {
    "booking_profile": {"id", "name", "slug", "bpm_min", "bpm_max"},
    "booking_profile_genre_tag": {"id", "profile_id", "tag"},
    "structure": {"id", "name", "booking_profile_id", "created_at", "last_applied_at"},
    "structure_node": {
        "id",
        "structure_id",
        "parent_id",
        "kind",
        "name",
        "position",
        "set_phase",
        "rb_ref",
    },
    "structure_track": {"node_id", "rb_content_id", "position", "origin"},
    "suggestion_dismissal": {"node_id", "rb_content_id"},
}


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_every_booking_table_with_the_documented_columns(
    tmp_path, monkeypatch
):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    for table, expected_columns in _EXPECTED_COLUMNS.items():
        assert table in tables
        assert {c["name"] for c in inspector.get_columns(table)} == expected_columns


def test_upgrade_head_seeds_the_four_booking_profiles(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT name, slug, bpm_min, bpm_max FROM booking_profile"))
        profiles = {row.slug: row for row in rows}
    assert set(profiles) == {"horeca", "bruiloft", "prive", "thema"}
    for row in profiles.values():
        assert row.bpm_min is None
        assert row.bpm_max is None


def test_downgrade_removes_only_the_booking_tables(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", "897efaa0742a")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    for table in _EXPECTED_COLUMNS:
        assert table not in tables
    assert "enrichment_state" in tables
