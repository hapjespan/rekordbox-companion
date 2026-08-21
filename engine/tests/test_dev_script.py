"""T006: scripts/dev.sh launches uvicorn --reload and the Vite dev proxy together."""

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEV_SCRIPT = REPO_ROOT / "scripts" / "dev.sh"


def test_dev_script_exists_and_is_executable():
    assert DEV_SCRIPT.exists()
    mode = DEV_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def test_dev_script_fails_loudly_without_the_uvicorn_command():
    # Real invocation, not text matching: no hardcoded fallback exists, so a
    # missing argument must fail fast rather than silently drift from the
    # Makefile's UVICORN variable (review finding on an earlier draft).
    result = subprocess.run([str(DEV_SCRIPT)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()


def test_dev_script_appends_reload_to_the_given_uvicorn_command():
    content = DEV_SCRIPT.read_text()
    assert "$UVICORN_CMD --reload" in content


def test_dev_script_launches_the_vite_dev_proxy():
    content = DEV_SCRIPT.read_text()
    assert "pnpm dev" in content


def test_dev_script_cleans_up_both_processes_on_exit():
    content = DEV_SCRIPT.read_text()
    assert "trap" in content


def test_dev_script_backgrounds_both_processes_and_waits():
    # Cheap structural check for the exact bug the trap exists to prevent: if
    # a future edit drops `&`/`wait`, the two servers would run sequentially
    # (the first blocking forever) instead of side by side.
    content = DEV_SCRIPT.read_text()
    launch_lines = [
        line for line in content.splitlines() if "cd engine" in line or "cd web" in line
    ]
    assert len(launch_lines) == 2
    assert all(line.rstrip().endswith("&") for line in launch_lines)
    assert "wait" in content


def test_makefile_dev_target_delegates_to_the_script_with_the_shared_command():
    makefile = (REPO_ROOT / "Makefile").read_text()
    dev_recipe = makefile.split("dev:")[1].split("\n\n")[0]
    assert "scripts/dev.sh" in dev_recipe
    assert "$(UVICORN)" in dev_recipe
