"""T086 (US7): API contract tests for `POST /api/structures/{id}/apply`
(FR-035/FR-018, contracts/api.md "ApplyResult variant with per-node results").

This file tests the ENDPOINT's own orchestration (guard -> backup ->
writer.apply_structure -> write_log -> per-node ApplyResult, refusal mapping,
rb_ref persistence) against a seeded in-memory companion DB. It does not touch
the real Rekordbox fixture DB -- that's `tests/bookings/test_structure_apply.py`'s
job (T080 integration). `guard.check`/`backup.create`/`writer.apply_structure`
are the seam: refusal tests monkeypatch guard.check's own OS-level dependencies
so guard.py's real logic runs; backup_failed and success tests monkeypatch
`backup.create`/`writer.apply_structure` directly, mirroring
`test_sync_apply.py`.
"""

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from companion.db.models import Structure, StructureNode, StructureTrack, WriteLog
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb import backup, writer


def _seed_structure(session_local):
    """A folder with one nested playlist holding two tracks. Returns
    (structure_id, folder_node_id, playlist_node_id)."""
    with session_local() as db:
        structure = Structure(
            name="Booking 2026",
            booking_profile_id=None,
            created_at=datetime(2026, 8, 17),
            last_applied_at=None,
        )
        db.add(structure)
        db.flush()
        folder = StructureNode(
            structure_id=structure.id,
            parent_id=None,
            kind="folder",
            name="Run of Show",
            position=0,
            set_phase=None,
            rb_ref=None,
        )
        db.add(folder)
        db.flush()
        playlist = StructureNode(
            structure_id=structure.id,
            parent_id=folder.id,
            kind="playlist",
            name="Vooravond",
            position=0,
            set_phase="vooravond",
            rb_ref=None,
        )
        db.add(playlist)
        db.flush()
        db.add(
            StructureTrack(
                node_id=playlist.id, rb_content_id="rb-a", position=0, origin="suggestion"
            )
        )
        db.add(
            StructureTrack(node_id=playlist.id, rb_content_id="rb-b", position=1, origin="manual")
        )
        db.commit()
        return structure.id, folder.id, playlist.id


def _client(tmp_path):
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    dummy_db = tmp_path / "master.db"
    dummy_db.write_bytes(b"0" * 1024)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_local, dummy_db


def _detection(db_path: Path, *, version="7.2.17", version_pin_ok=True):
    from companion.rb.reader import RekordboxDetection

    return RekordboxDetection(
        installed=True,
        version=version,
        version_pin_ok=version_pin_ok,
        db_path=db_path,
        db_file_exists=True,
    )


def _stub_backup_and_writer(monkeypatch, *, readback_ok=True):
    """Stub the write path: backup succeeds, and apply_structure echoes each
    NodeSpec back as a NodeWriteResult (created when it had no rb_ref, reusing
    the caller's rb_ref otherwise, so re-apply is observable). Captures the
    NodeSpec list the endpoint built for assertions."""
    monkeypatch.setattr(
        "companion.rb.backup.create",
        lambda db_path, backup_dir: backup.BackupResult(
            ok=True, path=Path("/tmp/backup-1.db.zip"), error=None
        ),
    )
    captured = {}

    def fake_apply_structure(db_path, nodes):
        captured["nodes"] = list(nodes)
        results = []
        for node in nodes:
            rb_ref = node.rb_ref if node.rb_ref is not None else f"rb-node-{node.node_id}"
            results.append(
                writer.NodeWriteResult(
                    node_id=node.node_id,
                    rb_ref=rb_ref,
                    created=node.rb_ref is None,
                    tracks_added=len(node.rb_content_ids),
                    tracks_already_present=0,
                    readback_ok=readback_ok,
                )
            )
        return results

    monkeypatch.setattr("companion.rb.writer.apply_structure", fake_apply_structure)
    return captured


def test_apply_succeeds_updates_rb_ref_on_every_node_and_last_applied(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, folder_id, playlist_id = _seed_structure(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    captured = _stub_backup_and_writer(monkeypatch)

    response = client.post(f"/api/structures/{structure_id}/apply", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["readback_ok"] is True
    assert body["backup_path"] == "/tmp/backup-1.db.zip"
    by_node = {n["node_id"]: n for n in body["nodes"]}
    assert by_node[folder_id]["created"] is True
    assert by_node[folder_id]["tracks_added"] == 0
    assert by_node[playlist_id]["created"] is True
    assert by_node[playlist_id]["tracks_added"] == 2

    # The endpoint built one NodeSpec per node, with the playlist's tracks
    # ordered by position and folders carrying no tracks.
    specs = {n.node_id: n for n in captured["nodes"]}
    assert specs[folder_id].kind == "folder"
    assert specs[folder_id].parent_node_id is None
    assert specs[folder_id].rb_content_ids == []
    assert specs[playlist_id].parent_node_id == folder_id
    assert specs[playlist_id].rb_content_ids == ["rb-a", "rb-b"]

    with session_local() as db:
        assert db.get(StructureNode, folder_id).rb_ref == f"rb-node-{folder_id}"
        assert db.get(StructureNode, playlist_id).rb_ref == f"rb-node-{playlist_id}"
        assert db.get(Structure, structure_id).last_applied_at is not None
        log = db.query(WriteLog).filter_by(subject_id=structure_id, kind="structure_apply").one()
        assert log.readback_ok is True
        assert log.backup_path == "/tmp/backup-1.db.zip"
        assert len(log.detail["nodes"]) == 2


def test_apply_refused_when_rekordbox_is_running(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, _, _ = _seed_structure(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: True)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    monkeypatch.setattr(
        "companion.rb.backup.create", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )
    monkeypatch.setattr(
        "companion.rb.writer.apply_structure", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/structures/{structure_id}/apply", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "rekordbox_running"
    with session_local() as db:
        assert db.get(Structure, structure_id).last_applied_at is None


def test_apply_refused_when_version_does_not_match_the_pin(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, _, _ = _seed_structure(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr(
        "companion.rb.reader.detect_rekordbox",
        lambda: _detection(dummy_db, version="7.1.0", version_pin_ok=False),
    )
    monkeypatch.setattr(
        "companion.rb.backup.create", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/structures/{structure_id}/apply", json={})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "version_mismatch"
    assert "7.1.0" in body["message"]


def test_apply_refused_when_backup_fails_verification(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, _, _ = _seed_structure(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    monkeypatch.setattr(
        "companion.rb.backup.create",
        lambda db_path, backup_dir: backup.BackupResult(
            ok=False, path=None, error="verification failed"
        ),
    )
    monkeypatch.setattr(
        "companion.rb.writer.apply_structure", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/structures/{structure_id}/apply", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "backup_failed"
    with session_local() as db:
        assert db.get(Structure, structure_id).last_applied_at is None


def test_reapply_reuses_existing_rb_refs_instead_of_creating_fresh(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, folder_id, playlist_id = _seed_structure(session_local)
    # Simulate a prior apply having stamped rb_ref on both nodes.
    with session_local() as db:
        db.get(StructureNode, folder_id).rb_ref = "rb-folder-existing"
        db.get(StructureNode, playlist_id).rb_ref = "rb-playlist-existing"
        db.commit()
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    captured = _stub_backup_and_writer(monkeypatch)

    response = client.post(f"/api/structures/{structure_id}/apply", json={})

    assert response.status_code == 200
    specs = {n.node_id: n for n in captured["nodes"]}
    assert specs[folder_id].rb_ref == "rb-folder-existing"
    assert specs[playlist_id].rb_ref == "rb-playlist-existing"
    body = response.json()
    by_node = {n["node_id"]: n for n in body["nodes"]}
    assert by_node[folder_id]["created"] is False
    assert by_node[playlist_id]["created"] is False
    # rb_ref stays the reused id, not a freshly-created one.
    with session_local() as db:
        assert db.get(StructureNode, folder_id).rb_ref == "rb-folder-existing"
        assert db.get(StructureNode, playlist_id).rb_ref == "rb-playlist-existing"


def test_apply_reports_readback_failure_without_marking_last_applied(monkeypatch, tmp_path):
    # spec.md US3 scenario 7 (structure variant): the write happened (backup +
    # write_log exist), verification failed on a node -> 200 with readback_ok
    # False surfaced, last_applied_at stays None, but rb_ref is still persisted
    # (the write is real, re-running with a stale None would duplicate).
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, folder_id, playlist_id = _seed_structure(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    _stub_backup_and_writer(monkeypatch, readback_ok=False)

    response = client.post(f"/api/structures/{structure_id}/apply", json={})

    assert response.status_code == 200
    assert response.json()["readback_ok"] is False
    with session_local() as db:
        assert db.get(Structure, structure_id).last_applied_at is None
        assert db.get(StructureNode, playlist_id).rb_ref == f"rb-node-{playlist_id}"
        log = db.query(WriteLog).filter_by(subject_id=structure_id, kind="structure_apply").one()
        assert log.readback_ok is False


def test_apply_logs_a_write_attempt_even_when_the_writer_raises(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    structure_id, _, _ = _seed_structure(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    monkeypatch.setattr(
        "companion.rb.backup.create",
        lambda db_path, backup_dir: backup.BackupResult(
            ok=True, path=Path("/tmp/backup-1.db.zip"), error=None
        ),
    )

    def raising_apply_structure(*args, **kwargs):
        raise RuntimeError("Rekordbox is running. Please close Rekordbox before commiting changes.")

    monkeypatch.setattr("companion.rb.writer.apply_structure", raising_apply_structure)

    try:
        client.post(f"/api/structures/{structure_id}/apply", json={})
    except RuntimeError:
        pass  # the TestClient re-raises server exceptions by default; expected here

    with session_local() as db:
        assert db.get(Structure, structure_id).last_applied_at is None
        log = db.query(WriteLog).filter_by(subject_id=structure_id, kind="structure_apply").one()
        assert log.readback_ok is False
        assert log.backup_path == "/tmp/backup-1.db.zip"
        assert "Rekordbox is running" in log.detail["error"]


def test_apply_unknown_structure_returns_404(monkeypatch, tmp_path):
    client, _, _ = _client(tmp_path)
    monkeypatch.setattr(
        "companion.rb.reader.detect_rekordbox", lambda: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post("/api/structures/9999/apply", json={})

    assert response.status_code == 404
    assert response.json()["code"] == "structure_not_found"
