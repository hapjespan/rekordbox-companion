"""FastAPI app factory: serves the built SPA and mounts the API routers.

FR-037 (reachable only from the machine it runs on) is enforced at the
process level -- uvicorn binds `127.0.0.1:8787` (Makefile, scripts/dev.sh,
T005/T006) -- not re-implemented here as app-level middleware; nothing in
constraints.md/architecture.md asks for a second enforcement layer, and
there is no app auth surface to protect (constraints.md).
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from companion.api import auth, collection, config, events, health, player, sync
from companion.config import REPO_ROOT
from companion.logging import configure_logging
from companion.rb.index import CollectionIndex

WEB_DIST = REPO_ROOT / "web" / "dist"


async def _flat_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """FastAPI's default handler wraps `HTTPException.detail` as
    `{"detail": ...}`; contracts/api.md's error convention is the flat
    `{code, message, field?}` shape instead. Endpoints raise
    `HTTPException(detail={"code": ..., "message": ...})`; anything that
    raises with a plain string detail (FastAPI's own built-in exceptions)
    falls back to a generic code rather than breaking the envelope."""
    body = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "http_error", "message": str(exc.detail)}
    )
    # Preserve any headers the raising endpoint set (e.g. the RFC 7233
    # `Content-Range` on a 416 from the audio stream); endpoints that set none
    # pass `None`, leaving the envelope unchanged.
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


def create_app() -> FastAPI:
    # Idempotent; also runs at `rb/reader.py` import time (the module that
    # actually imports pyrekordbox, rule 1) so the guarantee holds even for
    # code paths that never build an app -- calling it again here just
    # documents the intent explicitly at the process entrypoint (T018).
    configure_logging()

    app = FastAPI(title="Rekordbox Companion")
    app.state.collection_index = CollectionIndex()
    app.add_exception_handler(HTTPException, _flat_http_exception)

    # API routers must be included above this line: Starlette matches
    # routes in registration order, and a Mount("/") matches any path under
    # it, so mounting the SPA first would swallow /api/... too.
    app.include_router(health.router, prefix="/api")
    app.include_router(collection.router, prefix="/api")
    app.include_router(config.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(sync.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(player.router, prefix="/api")

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")

    return app


# The Makefile's UVICORN var and scripts/dev.sh both invoke
# `companion.main:app` (T005/T006); tests always call `create_app()`
# directly instead (a fresh instance per test), so this module-level
# instance had never actually been exercised until something tried to run
# the real server -- found while regenerating the OpenAPI schema for T031.
app = create_app()
