"""
Liveness + readiness probe and lightweight ops metadata.

* ``/healthz`` — used by Docker HEALTHCHECK. Fast and boolean-ish.
* ``/status`` — version, Python, platform, uptime, DB file stats. For
  humans and backup scripts, not for high-frequency synthetic monitoring.

Both stay out of the OpenAPI schema. Neither logs per request.
"""
from __future__ import annotations

import os
import platform
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.version_info import get_package_version
from core.db import DB_PATH

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
def healthz() -> JSONResponse:
    # Readiness = "can we open the DB?". We don't care about schema
    # correctness here; init_db runs at startup and a deeper check would
    # just slow the probe down.
    db_status = "ok"
    db_error: str | None = None
    try:
        with sqlite3.connect(DB_PATH, timeout=1.0) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:  # pragma: no cover - exercised only on real failure
        db_status = "error"
        db_error = type(exc).__name__

    status_code = 200 if db_status == "ok" else 503
    payload: dict[str, str] = {"status": "ok" if db_status == "ok" else "degraded", "db": db_status}
    if db_error:
        payload["error"] = db_error
    return JSONResponse(payload, status_code=status_code)


@router.get("/status", include_in_schema=False)
def status(request: Request) -> JSONResponse:
    """Single-user ops: runtime + DB file summary. Safe to curl from the LAN."""
    started = getattr(request.app.state, "started_at", None)
    now = time.time()
    uptime_sec: float | None
    if started is not None:
        uptime_sec = round(now - float(started), 3)
    else:
        uptime_sec = None

    db_path = Path(DB_PATH)
    db_exists = db_path.exists()
    size_bytes: int | None = None
    schema_version: int | None = None
    if db_exists:
        try:
            size_bytes = db_path.stat().st_size
        except OSError:
            size_bytes = None
        try:
            with sqlite3.connect(DB_PATH, timeout=1.0) as conn:
                schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        except Exception:  # pragma: no cover — only on real disk/sqlite failure
            schema_version = None

    payload: dict[str, Any] = {
        "app": "plant-pal",
        "version": get_package_version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uptime_sec": uptime_sec,
        "db": {
            "file": db_path.name,
            "exists": db_exists,
            "size_bytes": size_bytes,
            "schema_version": schema_version,
        },
        "log_level": (os.environ.get("PLANTPAL_LOG_LEVEL") or "INFO").strip(),
    }
    sha = (os.environ.get("PLANTPAL_GIT_SHA") or "").strip()
    if sha:
        payload["git_sha"] = sha[:40]
    return JSONResponse(payload)
