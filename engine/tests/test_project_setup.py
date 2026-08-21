"""T001: the companion package exists and declares its pinned dependencies."""

import tomllib
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def pyproject():
    return tomllib.loads((ENGINE_ROOT / "pyproject.toml").read_text())


def test_companion_package_is_importable():
    import companion  # noqa: F401


def test_pyproject_declares_required_dependencies(pyproject):
    declared = " ".join(pyproject["project"]["dependencies"]).lower()

    for package in (
        "fastapi",
        "uvicorn",
        "pyrekordbox",
        "rapidfuzz",
        "sqlalchemy",
        "alembic",
        "httpx",
    ):
        assert package in declared, f"{package} missing from engine/pyproject.toml dependencies"


def test_pyproject_pins_python_3_12(pyproject):
    assert pyproject["project"]["requires-python"] == "==3.12.*"
