"""T009: the Alembic migrations framework is wired to companion's own Base."""

import subprocess
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent


def test_alembic_ini_exists_and_points_at_the_alembic_directory():
    ini = (ENGINE_ROOT / "alembic.ini").read_text()
    assert "script_location = %(here)s/alembic" in ini


def test_env_py_targets_the_companion_declarative_base():
    env_py = (ENGINE_ROOT / "alembic" / "env.py").read_text()
    assert "from companion.db.session import Base, default_database_url" in env_py
    assert "target_metadata = Base.metadata" in env_py


def test_env_py_honours_the_database_url_override():
    env_py = (ENGINE_ROOT / "alembic" / "env.py").read_text()
    assert "config.set_main_option(" in env_py
    assert '"sqlalchemy.url"' in env_py
    assert 'os.environ.get("DATABASE_URL") or default_database_url()' in env_py


def test_alembic_current_runs_cleanly_against_an_isolated_database(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_smoke.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    result = subprocess.run(
        ["uv", "run", "alembic", "current"],
        cwd=ENGINE_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
