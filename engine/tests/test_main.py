"""T014: FastAPI app factory, static SPA mount.

FR-037 (reachable only from the machine it runs on) is enforced by the
uvicorn `--host 127.0.0.1` invocation (Makefile/scripts/dev.sh, T005/T006),
already tested there -- not re-implemented as app-level middleware, since
nothing in constraints.md/architecture.md asks for that (no app auth,
network binding is the whole boundary).
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from companion.main import create_app


def test_create_app_returns_a_fastapi_instance():
    assert isinstance(create_app(), FastAPI)


def test_create_app_instances_are_independent():
    # Not just "different objects" (true of any two constructor calls
    # regardless of correctness) -- a route added to one app must not leak
    # into another, so tests that build their own app stay isolated.
    first = create_app()
    second = create_app()

    first.get("/only-on-first")(lambda: {"ok": True})

    # Not every entry in .routes has a .path (e.g. included sub-routers),
    # so only compare the ones that do.
    first_paths = {route.path for route in first.routes if hasattr(route, "path")}
    second_paths = {route.path for route in second.routes if hasattr(route, "path")}
    assert "/only-on-first" in first_paths
    assert "/only-on-first" not in second_paths


def test_serves_the_built_spa_when_web_dist_exists(tmp_path, monkeypatch):
    web_dist = tmp_path / "web" / "dist"
    web_dist.mkdir(parents=True)
    (web_dist / "index.html").write_text("<html>companion</html>")

    monkeypatch.setattr("companion.main.WEB_DIST", web_dist)
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "companion" in response.text


def test_starts_without_a_built_spa_present(tmp_path, monkeypatch):
    # web/dist doesn't exist until `make build` runs (T005); the app must
    # still start (e.g. for API-only dev against the Vite dev server).
    monkeypatch.setattr("companion.main.WEB_DIST", tmp_path / "nonexistent")

    client = TestClient(create_app())

    assert client.app is not None


def test_http_exceptions_return_the_flat_error_shape():
    # contracts/api.md's convention is {code, message, field?}, not
    # FastAPI's default {"detail": {...}} envelope (T016 review finding:
    # the first error path in the API set the wrong precedent for it).
    app = create_app()

    @app.get("/raises-for-test")
    def _raises():
        raise HTTPException(status_code=409, detail={"code": "example", "message": "why"})

    client = TestClient(app)
    response = client.get("/raises-for-test")

    assert response.status_code == 409
    assert response.json() == {"code": "example", "message": "why"}


def test_http_exceptions_with_a_plain_string_detail_still_get_a_code():
    # Not every HTTPException raised in this codebase is guaranteed to use
    # the {code, message} dict convention (e.g. a future call to FastAPI's
    # own shorthand `HTTPException(404, "not found")`); the fallback branch
    # must still produce a valid, flat envelope rather than leaking a bare
    # string or crashing.
    app = create_app()

    @app.get("/raises-plain-string-for-test")
    def _raises():
        raise HTTPException(status_code=404, detail="not found")

    client = TestClient(app)
    response = client.get("/raises-plain-string-for-test")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "http_error"
    assert body["message"] == "not found"
