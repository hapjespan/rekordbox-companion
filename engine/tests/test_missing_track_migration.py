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
    # FR-041 (revision 4b90651e66b4): the automatic pick's preview and price.
    "itunes_preview_url",
    "itunes_price",
    "itunes_currency",
}

# The revision that adds FR-041's three columns, and the one before it.
_PREVIEW_PRICE_REVISION = "4b90651e66b4"
_BEFORE_PREVIEW_PRICE = "8cd0cf8178d6"
_PREVIEW_PRICE_COLUMNS = {"itunes_preview_url", "itunes_price", "itunes_currency"}


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


def test_the_preview_and_price_columns_are_typed_for_a_url_an_amount_and_a_code(
    tmp_path, monkeypatch
):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    columns = sa.inspect(engine).get_columns("missing_track")
    types = {c["name"]: type(c["type"]).__name__ for c in columns}
    # A price is an amount, not text: the UI formats it for the Dutch locale.
    assert types["itunes_price"] == "FLOAT"
    assert types["itunes_preview_url"] == "VARCHAR"
    assert types["itunes_currency"] == "VARCHAR"


def test_downgrade_of_the_preview_price_revision_drops_only_those_three_columns(
    tmp_path, monkeypatch
):
    # Reversible like its siblings: stepping back one revision leaves the
    # table and every pre-FR-041 column intact.
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", _BEFORE_PREVIEW_PRICE)
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    assert "missing_track" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("missing_track")}
    assert columns == _EXPECTED_COLUMNS - _PREVIEW_PRICE_COLUMNS

    # And forward again, so the pair is genuinely round-trippable.
    _alembic(tmp_path, monkeypatch, "upgrade", _PREVIEW_PRICE_REVISION)
    reopened = sa.create_engine(f"sqlite:///{db_path}")
    columns = {c["name"] for c in sa.inspect(reopened).get_columns("missing_track")}
    assert columns == _EXPECTED_COLUMNS


def test_downgrade_removes_only_the_missing_track_table(tmp_path, monkeypatch):
    db_path = _alembic(tmp_path, monkeypatch, "upgrade", "head")
    _alembic(tmp_path, monkeypatch, "downgrade", "855efacd231b")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    assert "missing_track" not in tables
    assert "sync_track" in tables
