"""GET /api/health: guard visibility (FR-015, contracts/api.md)."""

import shutil

from fastapi import APIRouter

from companion.rb.reader import detect_rekordbox, is_rekordbox_running

router = APIRouter()


@router.get("/health")
def get_health():
    detection = detect_rekordbox()
    # "degraded", not an error, when Rekordbox isn't installed, doesn't
    # match the pin, or its database file has moved/been deleted since
    # Rekordbox was configured (spec edge case): the spec names this a
    # startup state the app runs in, not a crash.
    status = (
        "ok"
        if detection.installed and detection.version_pin_ok and detection.db_file_exists
        else "degraded"
    )
    return {
        "status": status,
        "rekordbox_version": detection.version,
        "version_pin_ok": detection.version_pin_ok,
        "db_path": str(detection.db_path) if detection.db_path else None,
        "rekordbox_running": is_rekordbox_running(),
        "ffmpeg_ok": shutil.which("ffmpeg") is not None,
    }
