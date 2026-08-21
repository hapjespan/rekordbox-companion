"""T101: GET/PUT /api/config -- the app_config key/value store (data-model.md)."""

from fastapi.testclient import TestClient

from companion.db.models import AppConfig
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app


def _client_with_isolated_db():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_local


def test_get_config_returns_empty_when_no_rows_exist():
    client, _ = _client_with_isolated_db()

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {}


def test_get_config_returns_existing_rows_as_key_value_pairs():
    client, session_local = _client_with_isolated_db()
    with session_local() as db:
        db.add(AppConfig(key="rekordbox_version_pin", value="7.2.17"))
        db.commit()

    response = client.get("/api/config")

    assert response.json() == {"rekordbox_version_pin": "7.2.17"}


def test_put_config_creates_new_keys():
    client, session_local = _client_with_isolated_db()

    response = client.put("/api/config", json={"auto_match_bar": "92"})

    assert response.status_code == 200
    assert response.json() == {"auto_match_bar": "92"}
    with session_local() as db:
        assert db.get(AppConfig, "auto_match_bar").value == "92"


def test_put_config_updates_existing_keys_without_duplicating():
    client, session_local = _client_with_isolated_db()
    with session_local() as db:
        db.add(AppConfig(key="auto_match_bar", value="92"))
        db.commit()

    response = client.put("/api/config", json={"auto_match_bar": "90"})

    assert response.json() == {"auto_match_bar": "90"}
    with session_local() as db:
        assert db.query(AppConfig).count() == 1
        assert db.get(AppConfig, "auto_match_bar").value == "90"
