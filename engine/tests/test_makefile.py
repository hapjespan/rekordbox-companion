"""T005: the root Makefile declares the quickstart targets correctly."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _make_dry_run(target: str) -> str:
    result = subprocess.run(
        ["make", "-n", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_declares_all_quickstart_targets():
    for target in ("setup", "dev", "test", "build", "run"):
        _make_dry_run(target)


def test_setup_target_syncs_both_projects():
    plan = _make_dry_run("setup")
    assert "uv sync" in plan
    assert "pnpm install" in plan


def test_setup_target_installs_the_pre_commit_hook():
    plan = _make_dry_run("setup")
    assert "pre-commit-hook.sh" in plan
    assert ".git/hooks/pre-commit" in plan


def test_dev_target_delegates_to_the_dev_script():
    # The actual uvicorn+Vite orchestration lives in scripts/dev.sh (T006),
    # passed the shared UVICORN command so it never drifts from `run`.
    plan = _make_dry_run("dev")
    assert "scripts/dev.sh" in plan
    assert "uvicorn" in plan
    assert "127.0.0.1" in plan
    assert "8787" in plan


def test_test_target_runs_both_suites():
    # Dry-run only: invoking `make test` for real from inside a test that
    # `make test` itself would run recurses into the whole suite.
    plan = _make_dry_run("test")
    assert "uv run pytest" in plan
    assert "pnpm test" in plan


def test_build_target_builds_the_spa():
    plan = _make_dry_run("build")
    assert "pnpm build" in plan


def test_run_target_serves_production_mode():
    plan = _make_dry_run("run")
    assert "uvicorn" in plan
    assert "--reload" not in plan


def test_dev_and_run_share_the_same_uvicorn_invocation():
    base_command = "uv run uvicorn companion.main:app --host 127.0.0.1 --port 8787"
    assert base_command in _make_dry_run("dev")
    assert base_command in _make_dry_run("run")
