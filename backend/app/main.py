from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import albums, audit, backups, health, jobs, plans, roots, settings as settings_api, stats
from .core.config import get_settings
from .core.logging import setup_logging, trace_id_var
from .core.paths import PathViolation
from .db.session import get_session_factory, init_db
from .jobs.runner import JobRunner, set_runner

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db()
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(25.0, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": settings.musicbrainz_user_agent},
    )
    runner = JobRunner(get_session_factory(), client)
    await runner.start()
    set_runner(runner)
    app.state.client = client
    logger.info("music-scrap started")
    try:
        yield
    finally:
        await runner.stop()
        await client.aclose()
        set_runner(None)
        logger.info("music-scrap stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="music-scrap", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = uuid.uuid4().hex[:12]
        token = trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            trace_id_var.reset(token)
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": f"http_{exc.status_code}",
                "message": str(exc.detail),
                "details": None,
                "trace_id": trace_id_var.get(),
            },
        )

    @app.exception_handler(PathViolation)
    async def path_error(request: Request, exc: PathViolation):
        return JSONResponse(
            status_code=400,
            content={
                "code": "path_violation",
                "message": str(exc),
                "details": None,
                "trace_id": trace_id_var.get(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "invalid request",
                "details": exc.errors(),
                "trace_id": trace_id_var.get(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": str(exc),
                "details": None,
                "trace_id": trace_id_var.get(),
            },
        )

    for router in [
        health.router,
        stats.router,
        roots.router,
        jobs.router,
        albums.router,
        plans.router,
        backups.router,
        settings_api.router,
        audit.router,
    ]:
        app.include_router(router, prefix="/api")

    dist = Path(get_settings().frontend_dist)
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        index = dist / "index.html"
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {
                "name": "music-scrap",
                "message": "frontend build not found; run npm run build in frontend/",
                "docs": "/docs",
            }
        )

    return app


app = create_app()
