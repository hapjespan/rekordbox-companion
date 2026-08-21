"""T003: ruff lint/format configuration exists in engine/pyproject.toml."""

import subprocess
import sys
import tomllib
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_declares_ruff_dev_dependency():
    pyproject = tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text())
    dev_deps = " ".join(pyproject["dependency-groups"]["dev"]).lower()
    assert "ruff" in dev_deps


def test_pyproject_configures_ruff():
    pyproject = tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text())
    ruff_config = pyproject["tool"]["ruff"]
    assert ruff_config["target-version"] == "py312"
    assert ruff_config["line-length"] > 0


def test_ruff_check_passes_on_the_current_tree():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(ENGINE_ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_format_check_passes_on_the_current_tree():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(ENGINE_ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
