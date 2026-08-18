"""T044/T096/T106: API contract tests for `POST /api/sync/sessions/{id}/apply`
(FR-015..FR-019, contracts/api.md).

This file tests the ENDPOINT's own orchestration (guard -> backup -> write ->
write_log -> ApplyResult, refusal mapping, dedup-before-write) against a
seeded in-memory companion DB. It does not touch the real Rekordbox fixture
DB -- that's `test_writer_integration.py`'s job (T043/T045/T096-integration).
`guard.check`/`backup.create`/`writer.apply_playlist` are the seam: refusal
tests monkeypatch guard.check's own OS-level dependencies (`is_rekordbox_running`,
`detect_rekordbox`, disk usage) so guard.py's real logic runs; backup_failed
and readback-failure tests monkeypatch `backup.create`/`writer.apply_playlist`
directly, since their own failure mechanics are covered for real in
`test_writer_integration.py`.

Committed RED: `POST .../apply` doesn't exist until T050 builds it, and
`companion.rb.guard`/`backup`/`writer` don't exist until T046/T047/T048.
"""

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from companion.db.models import PlaylistLink, SyncSession, SyncTrack, WriteLog
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb import backup, writer


def _seed_ready_session(session_local, *, tracks=None, playlist_id="abc123"):
    with session_local() as db:
        link = PlaylistLink(
            spotify_playlist_id=playlist_id,
            rb_playlist_id=None,
            rb_playlist_name="Booking 2026",
            created_at=datetime(2026, 8, 17),
            last_applied_at=None,
        )
        db.add(link)
        db.flush()
        session = SyncSession(
            playlist_link_id=link.id,
            spotify_snapshot_id="snap-1",
            name="Booking 2026",
            status="ready",
            created_at=datetime(2026, 8, 17),
        )
        db.add(session)
        db.flush()
        for track in tracks or [{"rb_content_id": "rb-a", "position": 1}]:
            db.add(
                SyncTrack(
                    sync_session_id=session.id,
                    position=track["position"],
                    spotify_track_id=f"sp{track['position']}",
                    isrc=None,
                    artist="Daft Punk",
                    title="One More Time",
                    duration_ms=210_000,
                    status="matched",
                    rb_content_id=track["rb_content_id"],
                    match_score=95.0,
                    candidates=[],
                    matched_at=datetime(2026, 8, 17),
                )
            )
        db.commit()
        return link.id, session.id


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


def _stub_backup_and_writer(monkeypatch, *, readback_ok=True, playlist_id="rb-playlist-1"):
    monkeypatch.setattr(
        "companion.rb.backup.create",
        lambda db_path, backup_dir: backup.BackupResult(
            ok=True, path=Path("/tmp/backup-1.db.zip"), error=None
        ),
    )
    captured = {}

    def fake_apply_playlist(db_path, rb_playlist_id, playlist_name, rb_content_ids):
        captured["rb_content_ids"] = list(rb_content_ids)
        return writer.WriteResult(
            rb_playlist_id=rb_playlist_id or playlist_id,
            created=rb_playlist_id is None,
            tracks_added=len(set(rb_content_ids)),
            tracks_already_present=0,
            readback_ok=readback_ok,
        )

    monkeypatch.setattr("companion.rb.writer.apply_playlist", fake_apply_playlist)
    return captured


def test_apply_succeeds_guards_backs_up_writes_and_logs(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    link_id, session_id = _seed_ready_session(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    _stub_backup_and_writer(monkeypatch)

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["rb_playlist_id"] == "rb-playlist-1"
    assert body["created"] is True
    assert body["tracks_added"] == 1
    assert body["tracks_already_present"] == 0
    assert body["readback_ok"] is True
    assert body["backup_path"] == "/tmp/backup-1.db.zip"

    with session_local() as db:
        session = db.get(SyncSession, session_id)
        assert session.status == "applied"
        link = db.get(PlaylistLink, link_id)
        assert link.rb_playlist_id == "rb-playlist-1"
        assert link.last_applied_at is not None
        log = db.query(WriteLog).filter_by(subject_id=session_id, kind="sync_apply").one()
        assert log.readback_ok is True
        assert log.backup_path == "/tmp/backup-1.db.zip"


def test_apply_refused_when_rekordbox_is_running(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    _, session_id = _seed_ready_session(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: True)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    monkeypatch.setattr(
        "companion.rb.backup.create", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )
    monkeypatch.setattr(
        "companion.rb.writer.apply_playlist", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "rekordbox_running"
    with session_local() as db:
        assert db.get(SyncSession, session_id).status == "ready"


def test_apply_refused_when_version_does_not_match_the_pin(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    _, session_id = _seed_ready_session(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr(
        "companion.rb.reader.detect_rekordbox",
        lambda: _detection(dummy_db, version="7.1.0", version_pin_ok=False),
    )
    monkeypatch.setattr(
        "companion.rb.backup.create", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "version_mismatch"
    assert "7.1.0" in body["message"]


def test_apply_refused_when_disk_headroom_is_insufficient(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    _, session_id = _seed_ready_session(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    monkeypatch.setattr(
        "companion.rb.guard.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 1})(),  # far below 2x the dummy file's size
    )
    monkeypatch.setattr(
        "companion.rb.backup.create", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_disk"


def test_apply_refused_when_backup_fails_verification(monkeypatch, tmp_path):
    client, session_local, dummy_db = _client(tmp_path)
    _, session_id = _seed_ready_session(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    monkeypatch.setattr(
        "companion.rb.backup.create",
        lambda db_path, backup_dir: backup.BackupResult(
            ok=False, path=None, error="verification failed"
        ),
    )
    monkeypatch.setattr(
        "companion.rb.writer.apply_playlist", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "backup_failed"
    with session_local() as db:
        assert db.get(SyncSession, session_id).status == "ready"


def test_apply_reports_readback_failure_without_marking_the_session_applied(monkeypatch, tmp_path):
    # spec.md US3 scenario 7: the write happened (backup + write_log exist),
    # but verification failed -- a 200 with the failure surfaced in the
    # result, not a 409 refusal (nothing was "refused"; the write itself
    # just didn't verify), and the session stays ready, not applied.
    client, session_local, dummy_db = _client(tmp_path)
    _, session_id = _seed_ready_session(session_local)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    _stub_backup_and_writer(monkeypatch, readback_ok=False)

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["readback_ok"] is False
    assert body["backup_path"] == "/tmp/backup-1.db.zip"

    with session_local() as db:
        session = db.get(SyncSession, session_id)
        assert session.status == "ready"
        log = db.query(WriteLog).filter_by(subject_id=session_id, kind="sync_apply").one()
        assert log.readback_ok is False
        assert log.backup_path == "/tmp/backup-1.db.zip"


def test_apply_writes_a_duplicated_track_to_the_target_playlist_exactly_once(monkeypatch, tmp_path):
    # T106: the same rb_content_id accepted at two different playlist
    # positions (spec.md edge case) is still one Match, so it must be
    # written to the Target Playlist exactly once. Whether the dedup itself
    # happens here or inside writer.apply_playlist is an implementation
    # detail (it's writer.py's job -- see test_writer_integration.py); this
    # contract test only pins the outward-facing outcome: the endpoint must
    # never pass MORE positions worth of the same id than exist, and the
    # reported result must reflect exactly one track.
    client, session_local, dummy_db = _client(tmp_path)
    _, session_id = _seed_ready_session(
        session_local,
        tracks=[
            {"rb_content_id": "rb-dup", "position": 1},
            {"rb_content_id": "rb-dup", "position": 2},
        ],
    )
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(dummy_db))
    captured = _stub_backup_and_writer(monkeypatch)

    response = client.post(f"/api/sync/sessions/{session_id}/apply", json={})

    assert response.status_code == 200
    assert set(captured["rb_content_ids"]) == {"rb-dup"}
    assert response.json()["tracks_added"] == 1
