"""T015: GET /api/health -- guard visibility (FR-015, contracts/api.md)."""

from fastapi.testclient import TestClient

from companion.main import create_app


def _client():
    return TestClient(create_app())


def test_health_returns_the_documented_shape():
    response = _client().get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "status",
        "rekordbox_version",
        "version_pin_ok",
        "db_path",
        "rekordbox_running",
        "ffmpeg_ok",
    }


def test_health_reports_degraded_when_rekordbox_is_not_installed():
    # Real assertion, not mocked: this dev container genuinely has no
    # Rekordbox install (edge case: degraded state, not a crash).
    body = _client().get("/api/health").json()

    assert body["status"] == "degraded"
    assert body["rekordbox_version"] is None
    assert body["version_pin_ok"] is False
    assert body["db_path"] is None
    assert body["rekordbox_running"] is False


def test_health_reports_ok_when_rekordbox_matches_the_pinned_version_and_db_file_exists(
    monkeypatch, tmp_path
):
    from companion.rb.reader import RekordboxDetection

    db_path = tmp_path / "master.db"
    db_path.write_bytes(b"")
    monkeypatch.setattr(
        "companion.api.health.detect_rekordbox",
        lambda: RekordboxDetection(
            installed=True,
            version="7.2.17",
            version_pin_ok=True,
            db_path=db_path,
            db_file_exists=True,
        ),
    )

    body = _client().get("/api/health").json()

    assert body["status"] == "ok"
    assert body["rekordbox_version"] == "7.2.17"
    assert body["version_pin_ok"] is True


def test_health_reports_degraded_when_the_db_file_has_moved_or_been_deleted(monkeypatch):
    # Spec edge case: Rekordbox is installed and pinned, but its configured
    # database file no longer exists at that path.
    from companion.rb.reader import RekordboxDetection

    monkeypatch.setattr(
        "companion.api.health.detect_rekordbox",
        lambda: RekordboxDetection(
            installed=True,
            version="7.2.17",
            version_pin_ok=True,
            db_path="/some/path/master.db",
            db_file_exists=False,
        ),
    )

    body = _client().get("/api/health").json()

    assert body["status"] == "degraded"


def test_health_reports_ffmpeg_availability_from_the_real_container():
    # ffmpeg ships in the dev image (CLAUDE.md); real assertion, no mocking.
    body = _client().get("/api/health").json()

    assert body["ffmpeg_ok"] is True
