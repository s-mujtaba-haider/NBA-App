"""FastAPI entry point: `uvicorn backend.app.main:app` from the project root. Serves the API and the web app."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import jobs, logbuffer, runner
from .config import WEB_DIST, seed_home, settings
from .db import init_db

logbuffer.install(logging.INFO)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_home()
    init_db()
    jobs.mark_interrupted()
    from .security import private_key
    private_key()
    stop = threading.Event()
    threading.Thread(target=runner.scheduler, args=(stop,), daemon=True, name="scheduler").start()
    logger.info("Baseline %s started (db=%s, auto picks %s)", settings.version, "sqlite" if settings.is_sqlite else "postgres",
                "on" if settings.auto_picks else "off")
    yield
    stop.set()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan,
              description="NBA picks for the six WINNER markets, track record, Monte Carlo bankroll simulation, exports and licensing.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2000)


@app.middleware("http")
async def timing(request: Request, call_next):
    t = time.time()
    response = await call_next(request)
    response.headers["X-Response-Time-ms"] = f"{(time.time() - t) * 1000:.0f}"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Internal error: {type(exc).__name__}"})


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": settings.version}


from .routers import api, auth  # noqa: E402

app.include_router(auth.router)
app.include_router(api.router)

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file() and WEB_DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
