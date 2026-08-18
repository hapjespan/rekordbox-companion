"""T011: app-wide paths, env loading, and the pinned Rekordbox version.

Rekordbox install/version detection is NOT here: it moved to rb/reader.py
(T012) because it requires importing pyrekordbox, which project rule 1
confines to rb/; config.py sits outside rb/.
"""

from companion.config import DATA_DIR, PINNED_REKORDBOX_VERSION, REPO_ROOT, find_repo_root


def test_pinned_rekordbox_version_matches_adr_0002():
    assert PINNED_REKORDBOX_VERSION == "7.2.17"


def test_repo_root_contains_the_engine_and_web_directories():
    assert (REPO_ROOT / "engine").is_dir()
    assert (REPO_ROOT / "web").is_dir()


def test_data_dir_is_a_sibling_of_engine_and_web():
    assert DATA_DIR == REPO_ROOT / "data"


def test_find_repo_root_is_independent_of_the_caller_module_depth(tmp_path):
    fake_engine = tmp_path / "engine"
    (fake_engine / "src" / "companion" / "somewhere" / "deep").mkdir(parents=True)
    (fake_engine / "pyproject.toml").write_text("")
    deep_file = fake_engine / "src" / "companion" / "somewhere" / "deep" / "module.py"
    deep_file.write_text("")

    assert find_repo_root(deep_file) == tmp_path


def test_find_repo_root_raises_when_no_engine_marker_exists(tmp_path):
    lost = tmp_path / "a" / "b" / "c.py"
    lost.parent.mkdir(parents=True)
    lost.write_text("")

    try:
        find_repo_root(lost)
        raise AssertionError("expected a RuntimeError")
    except RuntimeError:
        pass


def test_dotenv_file_is_loaded_if_present(tmp_path, monkeypatch):
    import os

    import companion.config as config_module

    # Phase 7 review finding: this test used to append to and rewrite the
    # repo's real gitignored .env, so a crash before the finally-restore
    # could corrupt the developer's secrets file, and parallel test runs
    # raced on the same file. load_dotenv() takes the path as an argument
    # (see companion.config's own call below `ENV_PATH`), so point it at a
    # throwaway tmp_path file instead -- no real file is ever touched.
    monkeypatch.delenv("COMPANION_TEST_ENV_PROBE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("COMPANION_TEST_ENV_PROBE=present\n")

    config_module.load_dotenv(env_file, override=True)

    assert os.environ["COMPANION_TEST_ENV_PROBE"] == "present"
    monkeypatch.delenv("COMPANION_TEST_ENV_PROBE", raising=False)
