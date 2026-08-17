"""FastAPI app factory: serves the built SPA and mounts the API routers.

FR-037 (reachable only from the machine it runs on) is enforced at the
process level -- uvicorn binds `127.0.0.1:8787` (Makefile, scripts/dev.sh,
T005/T006) -- not re-implemented here as app-level middleware; nothing in
constraints.md/architecture.md asks for a second enforcement layer, and
there is no app auth surface to protect (constraints.md).
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from companion.api import health
from companion.config import REPO_ROOT

WEB_DIST = REPO_ROOT / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="Rekordbox Companion")

    # API routers must be included above this line: Starlette matches
    # routes in registration order, and a Mount("/") matches any path under
    # it, so mounting the SPA first would swallow /api/... too.
    app.include_router(health.router, prefix="/api")

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")

    return app
