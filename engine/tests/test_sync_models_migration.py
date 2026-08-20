"""T027: the playlist_link/sync_session/sync_track Alembic migration.

`playlist_link` moved here from its original task, T049 (tasks.md build
finding): `sync_session` FKs into it and T028 needs it for FR-010's lineage
reuse, both landing in User Story 1, before User Story 3 (where T049 would
otherwise have created it) exists.
"""

import subprocess
from pathlib import Path

import sqlalchemy as sa

ENGINE_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_TABLES = {
    "playlist_link": {
        "id",
        "spotify_playlist_id",
        "rb_playlist_id",
        "rb_playlist_name",
        "created_at",
        "last_applied_at",
    },
    "sync_session": {
        "id",
        "playlist_link_id",
        "spotify_snapshot_id",
        "name",
        "status",
        "created_at",
    },
    "sync_track": {
        "id",
        "sync_session_id",
        "position",
        "spotify_track_id",
        "isrc",
        "artist",
        "title",
        "duration_ms",
        "status",
        "rb_content_id",
        "match_score",
        "candidates",
        "matched_at",
    },
}


def _alembic(tmp_path, monkeypatch, *args):
    db_path = tmp_path / "migration_smoke.sqlite"
    monkeypatch.setenv("COMPANION_DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", *args], cwd=ENGINE_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db_path


def test_upgrade_head_creates_all_three_tables(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()

    for table_name, expected_columns in _EXPECTED_TABLES.items():
        assert table_name in tables
        columns = {c["name"] for c in inspector.get_columns(table_name)}
        assert columns == expected_columns


def test_downgrade_removes_only_these_three_tables(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    # Target this migration's own revision explicitly, not "-1": head has
    # grown further migrations since (T037's missing_track), so "-1 from
    # head" no longer lands on this migration's own down_revision (same
    # fix as T027's finding on the spotify_auth migration test).
    _alembic(tmp_path, monkeypatch, "downgrade", "f2a9c1b47e30")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()

    assert "playlist_link" not in tables
    assert "sync_session" not in tables
    assert "sync_track" not in tables
    assert "spotify_auth" in tables
    assert "app_config" in tables
