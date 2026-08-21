"""T010: the app_config table (data-model.md) stores key/value config rows."""

import pytest
from sqlalchemy.exc import IntegrityError

from companion.db.models import AppConfig
from companion.db.session import Base, create_session_factory


def _fresh_db():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_local


def test_app_config_has_a_key_primary_key_and_value_column():
    columns = {c.name: c for c in AppConfig.__table__.columns}
    assert set(columns) == {"key", "value"}
    assert columns["key"].primary_key is True


def test_app_config_round_trips_a_row():
    session_local = _fresh_db()
    with session_local() as db:
        db.add(AppConfig(key="rekordbox_version_pin", value="7.2.17"))
        db.commit()

    with session_local() as db:
        row = db.get(AppConfig, "rekordbox_version_pin")
        assert row.value == "7.2.17"


def test_app_config_key_is_unique():
    session_local = _fresh_db()
    with session_local() as db:
        db.add(AppConfig(key="auto_match_bar", value="92"))
        db.commit()
        db.add(AppConfig(key="auto_match_bar", value="90"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
