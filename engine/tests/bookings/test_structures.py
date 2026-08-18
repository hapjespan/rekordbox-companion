"""T079/T084/T085: structure/node tree CRUD, suggestions, tracks and
dismissals (FR-032, FR-033, FR-034, FR-032 rename-lock edge case)."""

from datetime import datetime

from fastapi.testclient import TestClient

from companion.db.models import (
    BookingProfile,
    BookingProfileGenreTag,
    EnrichedGenre,
    StructureNode,
    StructureTrack,
)
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack


def _track(rb_content_id: str, artist: str, title: str, bpm: float | None, play_count: int):
    return CollectionTrack(
        rb_content_id=rb_content_id,
        artist=artist,
        title=title,
        duration_ms=200_000,
        bpm=bpm,
        isrc=None,
        play_count=play_count,
        location=None,
    )


def _client(tracks=()):
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
    app.state.collection_index.rebuild(list(tracks))
    return TestClient(app), session_local


def test_post_creates_a_structure():
    client, _ = _client()

    response = client.post("/api/structures", json={"name": "Bruiloft Jansen"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Bruiloft Jansen"
    assert body["booking_profile_id"] is None


def test_get_structures_lists_them():
    client, _ = _client()
    client.post("/api/structures", json={"name": "A"})
    client.post("/api/structures", json={"name": "B"})

    response = client.get("/api/structures")

    assert {s["name"] for s in response.json()} == {"A", "B"}


def test_put_updates_name_and_profile():
    client, session_local = _client()
    with session_local() as db:
        db.add(BookingProfile(name="Bruiloft", slug="bruiloft", bpm_min=None, bpm_max=None))
        db.commit()
    structure = client.post("/api/structures", json={"name": "A"}).json()

    response = client.put(
        f"/api/structures/{structure['id']}", json={"name": "B", "booking_profile_id": 1}
    )

    assert response.json()["name"] == "B"
    assert response.json()["booking_profile_id"] == 1


def test_delete_removes_the_structure():
    client, _ = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()

    response = client.delete(f"/api/structures/{structure['id']}")

    assert response.status_code == 200
    assert client.get("/api/structures").json() == []


def test_post_node_creates_a_folder_or_playlist():
    client, _ = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()

    response = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={
            "kind": "folder",
            "name": "Vooravond",
            "parent_id": None,
            "position": 0,
            "set_phase": None,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "folder"
    assert body["name"] == "Vooravond"
    assert body["rb_ref"] is None


def test_nodes_can_nest_under_a_parent():
    client, _ = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()
    folder = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "folder", "name": "Vooravond", "parent_id": None, "position": 0},
    ).json()

    response = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={
            "kind": "playlist",
            "name": "Ontvangst",
            "parent_id": folder["id"],
            "position": 0,
            "set_phase": "vooravond",
        },
    )

    assert response.json()["parent_id"] == folder["id"]


def test_put_node_renames_it_when_not_yet_applied():
    client, _ = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "Old Name", "parent_id": None, "position": 0},
    ).json()

    response = client.put(
        f"/api/structures/{structure['id']}/nodes/{node['id']}",
        json={"name": "New Name", "position": 0},
    )

    assert response.json()["name"] == "New Name"


def test_put_node_refuses_a_rename_once_applied():
    """FR-032 edge case: a node already applied to Rekordbox is
    rename-locked -- its name is owned by Rekordbox from that point on."""
    client, session_local = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "Old Name", "parent_id": None, "position": 0},
    ).json()
    with session_local() as db:
        db.query(StructureNode).filter_by(id=node["id"]).update({"rb_ref": "rb-playlist-1"})
        db.commit()

    response = client.put(
        f"/api/structures/{structure['id']}/nodes/{node['id']}",
        json={"name": "New Name", "position": 0},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "node_name_locked"
    assert body["field"] == "name"


def test_put_node_still_allows_position_change_once_applied():
    client, session_local = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "Same Name", "parent_id": None, "position": 0},
    ).json()
    with session_local() as db:
        db.query(StructureNode).filter_by(id=node["id"]).update({"rb_ref": "rb-playlist-1"})
        db.commit()

    response = client.put(
        f"/api/structures/{structure['id']}/nodes/{node['id']}",
        json={"name": "Same Name", "position": 3},
    )

    assert response.status_code == 200
    assert response.json()["position"] == 3


def test_delete_node_removes_it():
    client, _ = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()

    response = client.delete(f"/api/structures/{structure['id']}/nodes/{node['id']}")

    assert response.status_code == 200


def test_suggestions_endpoint_filters_by_the_structures_profile():
    client, session_local = _client(
        tracks=[
            _track("1", "A", "House Track", bpm=None, play_count=10),
            _track("2", "B", "Techno Track", bpm=None, play_count=100),
        ]
    )
    with session_local() as db:
        profile = BookingProfile(name="Bruiloft", slug="bruiloft", bpm_min=None, bpm_max=None)
        db.add(profile)
        db.flush()
        db.add(BookingProfileGenreTag(profile_id=profile.id, tag="house"))
        db.commit()
        profile_id = profile.id
    structure = client.post(
        "/api/structures", json={"name": "A", "booking_profile_id": profile_id}
    ).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()

    with session_local() as db:
        db.add(
            EnrichedGenre(
                rb_content_id="1", genre="house", source="manual", updated_at=datetime.now()
            )
        )
        db.commit()

    response = client.get(f"/api/structures/{structure['id']}/nodes/{node['id']}/suggestions")

    assert response.status_code == 200
    body = response.json()
    assert [s["rb_content_id"] for s in body] == ["1"]


def test_post_track_accepts_a_suggestion_into_the_playlist():
    client, _ = _client(tracks=[_track("1", "A", "Track", bpm=None, play_count=10)])
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()

    response = client.post(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/tracks",
        json={"rb_content_id": "1", "origin": "suggestion"},
    )

    assert response.status_code == 200
    suggestions = client.get(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/suggestions"
    ).json()
    assert suggestions[0]["already_in_playlist"] is True


def test_delete_track_removes_it_from_an_unapplied_node():
    client, _ = _client(tracks=[_track("1", "A", "Track", bpm=None, play_count=10)])
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()
    client.post(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/tracks",
        json={"rb_content_id": "1", "origin": "suggestion"},
    )

    response = client.delete(f"/api/structures/{structure['id']}/nodes/{node['id']}/tracks/1")

    assert response.status_code == 200
    suggestions = client.get(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/suggestions"
    ).json()
    assert suggestions[0]["already_in_playlist"] is False


def test_delete_track_refuses_once_the_node_is_applied():
    """contracts/api.md: "remove from (unapplied) playlist node" -- once
    Rekordbox owns the playlist, tracks are removed there instead."""
    client, session_local = _client(tracks=[_track("1", "A", "Track", bpm=None, play_count=10)])
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()
    client.post(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/tracks",
        json={"rb_content_id": "1", "origin": "suggestion"},
    )
    with session_local() as db:
        db.query(StructureNode).filter_by(id=node["id"]).update({"rb_ref": "rb-playlist-1"})
        db.commit()

    response = client.delete(f"/api/structures/{structure['id']}/nodes/{node['id']}/tracks/1")

    assert response.status_code == 422
    assert response.json()["code"] == "node_already_applied"


def test_add_track_assigns_positions_by_max_not_count_avoiding_collisions():
    """Adding A, removing A, then adding B and C must not give B and C the
    same position -- a plain count() of remaining rows would (T085 review
    finding)."""
    client, session_local = _client(
        tracks=[
            _track("1", "A", "Track A", bpm=None, play_count=10),
            _track("2", "B", "Track B", bpm=None, play_count=10),
            _track("3", "C", "Track C", bpm=None, play_count=10),
        ]
    )
    structure = client.post("/api/structures", json={"name": "S"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()
    add_url = f"/api/structures/{structure['id']}/nodes/{node['id']}/tracks"
    client.post(add_url, json={"rb_content_id": "1", "origin": "suggestion"})
    client.delete(f"{add_url}/1")
    client.post(add_url, json={"rb_content_id": "2", "origin": "suggestion"})
    client.post(add_url, json={"rb_content_id": "3", "origin": "suggestion"})

    with session_local() as db:
        positions = [
            row.position for row in db.query(StructureTrack).filter_by(node_id=node["id"]).all()
        ]
    assert len(positions) == len(set(positions))  # no duplicate positions


def test_put_node_can_move_it_under_a_new_parent():
    client, _ = _client()
    structure = client.post("/api/structures", json={"name": "A"}).json()
    old_parent = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "folder", "name": "Old", "parent_id": None, "position": 0},
    ).json()
    new_parent = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "folder", "name": "New", "parent_id": None, "position": 1},
    ).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": old_parent["id"], "position": 0},
    ).json()

    response = client.put(
        f"/api/structures/{structure['id']}/nodes/{node['id']}",
        json={"name": "X", "parent_id": new_parent["id"], "position": 0},
    )

    assert response.status_code == 200
    assert response.json()["parent_id"] == new_parent["id"]


def test_dismissed_suggestions_never_return_via_the_api():
    """FR-034, tested through the real dismiss-then-suggest round trip."""
    client, _ = _client(tracks=[_track("1", "A", "Track", bpm=None, play_count=10)])
    structure = client.post("/api/structures", json={"name": "A"}).json()
    node = client.post(
        f"/api/structures/{structure['id']}/nodes",
        json={"kind": "playlist", "name": "X", "parent_id": None, "position": 0},
    ).json()

    dismiss_response = client.post(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/dismissals",
        json={"rb_content_id": "1"},
    )
    assert dismiss_response.status_code == 200

    suggestions = client.get(
        f"/api/structures/{structure['id']}/nodes/{node['id']}/suggestions"
    ).json()
    assert suggestions == []
