"""
Plant Pal FastAPI entry point.

Run locally: ./run.sh  ->  http://127.0.0.1:8000
Docker: image listens on PLANTPAL_HOST / PLANTPAL_PORT (see Dockerfile).

Structure:
  - FastAPI instance lives here
  - routers in app/routes/ are included below (one feature per module)
  - Jinja2 templates live in app/templates/
  - shared stylesheet and static assets live in app/static/
"""
import logging
import platform
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.error_handlers import register_exception_handlers
from app.logging_config import configure_logging
from app.security import install_security_middleware
from app.version_info import get_package_version
from core.db import ensure_seeded, init_db
from core.db.connection import DATA_DIR

configure_logging()
logger = logging.getLogger("plantpal.main")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = Path(DATA_DIR) / "uploads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations + seed templates once at startup.

    The routes still call ``init_db()`` / ``ensure_seeded()`` defensively
    because tests that hit routes directly (without using TestClient as
    a context manager) would otherwise see an empty DB. Both paths are
    idempotent — the lifespan is the canonical one, the per-request
    calls are a safety net.
    """
    import time

    t0 = time.time()
    app.state.started_at = t0
    logger.info(
        "plantpal startup version=%s python=%s platform=%s",
        get_package_version(),
        sys.version.split()[0],
        platform.platform(),
    )
    logger.info("plantpal: running migrations + seed")
    init_db()
    ensure_seeded()
    logger.info("plantpal: ready (startup took %.3fs)", time.time() - t0)
    yield
    logger.info("plantpal: shutdown")


app = FastAPI(title="Plant Pal", lifespan=lifespan)
register_exception_handlers(app)

# Security middleware (TrustedHost + response headers + optional CSP) is
# installed right after the FastAPI instance exists so every router below
# inherits it. See app/security.py for the env-var contract.
install_security_middleware(app)

# Starlette 1.0 dropped the ``keep_trailing_newline`` kwarg from
# ``Jinja2Templates``; hand-build the Environment so this option (and any
# future Jinja tweaks) still apply. ``keep_trailing_newline=True`` preserves
# byte-identical output with the legacy template strings the refactor
# inherited — do not remove without re-checking the golden HTML.
_jinja_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=select_autoescape(["html", "htm", "xml"]),
    keep_trailing_newline=True,
)
templates = Jinja2Templates(env=_jinja_env)

# ---------------------------------------------------------------------------
# Router registration. Each feature lives in its own module under
# app/routes/. The PWA router is included before the static mount so the
# explicit hero-image handler wins over the static file lookup.
# ---------------------------------------------------------------------------

# Routers are imported after the FastAPI instance exists so `app` and its
# middleware are in place before any handler is registered. The per-file
# E402 ignore in pyproject.toml covers this intentional late import.
from app.routes import (
    add_plant,
    api,
    dev,
    health,
    landing,
    library,
    pwa,
)
from app.routes import (
    plants as plants_route,
)

# PWA routes (including the hero fallback) must register before the static
# mount so the explicit handler wins over the static file lookup.
app.include_router(pwa.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# User-uploaded plant photos live outside the repo so a redeploy won't
# blow them away. The directory is created lazily by the upload helper;
# we guarantee it exists here so StaticFiles is happy even on a cold
# boot before the first upload.
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

app.include_router(health.router)
app.include_router(landing.router)
app.include_router(library.router)
app.include_router(add_plant.router)
app.include_router(plants_route.router)
app.include_router(api.router)
app.include_router(dev.router)

__all__ = ["app", "templates"]
