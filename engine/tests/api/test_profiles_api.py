"""T082: GET/POST /api/profiles, PUT/DELETE /api/profiles/{id} (FR-031)."""

from datetime import datetime

from fastapi.testclient import TestClient

from companion.db.models import BookingProfile, Structure
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app


def _client():
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


def test_get_profiles_lists_the_four_seeded_profiles_with_no_genre_tags():
    # The migration seeds these (T081); this app db is a fresh in-memory
    # one for the test, seeded the same way real Alembic upgrades would --
    # replicated here directly rather than depending on a migration run.
    client, session_local = _client()
    with session_local() as db:
        db.add_all(
            [
                BookingProfile(name="Horeca", slug="horeca", bpm_min=None, bpm_max=None),
                BookingProfile(name="Bruiloft", slug="bruiloft", bpm_min=None, bpm_max=None),
            ]
        )
        db.commit()

    response = client.get("/api/profiles")

    assert response.status_code == 200
    body = response.json()
    assert {p["slug"] for p in body} == {"horeca", "bruiloft"}
    assert body[0]["genre_tags"] == []


def test_post_creates_a_profile_with_a_derived_slug_and_genre_tags():
    client, _ = _client()

    response = client.post(
        "/api/profiles",
        json={
            "name": "Zomerfeest",
            "bpm_min": 120,
            "bpm_max": 128,
            "genre_tags": ["house", "disco"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Zomerfeest"
    assert body["slug"] == "zomerfeest"
    assert body["bpm_min"] == 120
    assert body["bpm_max"] == 128
    assert set(body["genre_tags"]) == {"house", "disco"}


def test_post_rejects_a_duplicate_name_with_a_field_naming_error():
    client, _ = _client()
    client.post("/api/profiles", json={"name": "Zomerfeest"})

    response = client.post("/api/profiles", json={"name": "Zomerfeest"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "duplicate_name"
    assert body["field"] == "name"


def test_put_updates_name_bpm_range_and_genre_tags():
    client, _ = _client()
    created = client.post(
        "/api/profiles", json={"name": "Zomerfeest", "genre_tags": ["house"]}
    ).json()

    response = client.put(
        f"/api/profiles/{created['id']}",
        json={"name": "Winterfeest", "bpm_min": 100, "bpm_max": 110, "genre_tags": ["techno"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Winterfeest"
    assert body["bpm_min"] == 100
    assert body["genre_tags"] == ["techno"]


def test_put_rejects_renaming_onto_a_name_another_profile_already_has():
    """Regression (phase 7 review): update skipped the duplicate-name check
    create performs, so a rename onto a taken name hit the unique index and
    surfaced as a 500 IntegrityError instead of the contract's 422."""
    client, _ = _client()
    client.post("/api/profiles", json={"name": "Zomerfeest"})
    other = client.post("/api/profiles", json={"name": "Winterfeest"}).json()

    response = client.put(f"/api/profiles/{other['id']}", json={"name": "Zomerfeest"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "duplicate_name"
    assert body["field"] == "name"


def test_put_allows_keeping_a_profiles_own_name():
    """The duplicate check must not fire on the profile's own row -- saving a
    BPM range without touching the name is the common case."""
    client, _ = _client()
    created = client.post("/api/profiles", json={"name": "Zomerfeest"}).json()

    response = client.put(
        f"/api/profiles/{created['id']}", json={"name": "Zomerfeest", "bpm_min": 120}
    )

    assert response.status_code == 200
    assert response.json()["bpm_min"] == 120


def test_put_regenerates_the_slug_on_a_rename():
    """Regression (phase 7 review): the slug is server-derived from the name,
    so it must follow a rename rather than keep pointing at the old name."""
    client, _ = _client()
    created = client.post("/api/profiles", json={"name": "Zomerfeest"}).json()

    response = client.put(f"/api/profiles/{created['id']}", json={"name": "Winter Feest"})

    assert response.status_code == 200
    assert response.json()["slug"] == "winter-feest"


def test_put_returns_404_for_an_unknown_profile():
    client, _ = _client()

    response = client.put("/api/profiles/999", json={"name": "X"})

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"


def test_delete_removes_the_profile_and_unlinks_referencing_structures():
    client, session_local = _client()
    created = client.post("/api/profiles", json={"name": "Zomerfeest"}).json()
    with session_local() as db:
        db.add(
            Structure(
                name="Bruiloft 2026",
                booking_profile_id=created["id"],
                created_at=datetime(2026, 8, 18),
            )
        )
        db.commit()

    response = client.delete(f"/api/profiles/{created['id']}")

    assert response.status_code == 200
    with session_local() as db:
        structure = db.query(Structure).filter_by(name="Bruiloft 2026").one()
        assert structure.booking_profile_id is None
    assert client.get("/api/profiles").json() == []


def test_delete_returns_404_for_an_unknown_profile():
    client, _ = _client()

    response = client.delete("/api/profiles/999")

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"
