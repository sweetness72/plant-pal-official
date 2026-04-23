"""
Stdlib logging setup for Plant Pal.

Intended for ``docker logs`` and journald: one line per event, optional
JSON lines (``PLANTPAL_LOG_FORMAT=json``) for trivial grepping.

Env
---
``PLANTPAL_LOG_LEVEL`` — root + ``plantpal``/``app``/``core`` loggers.
Default **INFO**. Use **DEBUG** in development when you need
per-recommendation lines (``core.drying_model``) without flooding prod.

``PLANTPAL_LOG_FORMAT`` — **text** (default) or **json**. JSON emits a
single object per line: ``ts``, ``level``, ``logger``, ``msg`` (and
``exception`` when present).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any


def _level_from_env() -> int:
    raw = (os.environ.get("PLANTPAL_LOG_LEVEL") or "INFO").strip().upper()
    m = logging.getLevelNamesMapping()
    v = m.get(raw)
    return v if v is not None else logging.INFO


class _JsonLineFormatter(logging.Formatter):
    """One JSON object per line; works with ``docker logs`` and ``jq``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    """UTC timestamp, level, logger, message — easy to read in a TTY."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        self.converter = time.gmtime  # type: ignore[assignment]


def configure_logging() -> None:
    """Idempotent: safe to call more than once (e.g. tests). Replaces handlers."""
    level = _level_from_env()
    fmt = (os.environ.get("PLANTPAL_LOG_FORMAT") or "text").strip().lower()
    use_json = fmt == "json"

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if use_json:
        handler.setFormatter(_JsonLineFormatter())
    else:
        handler.setFormatter(_TextFormatter())
    root.addHandler(handler)

    for name in ("plantpal", "app", "core"):
        logging.getLogger(name).setLevel(level)

    # Uvicorn is chatty on INFO (every request). Keep access logs at
    # WARNING unless the operator explicitly wants more.
    logging.getLogger("uvicorn.access").setLevel(
        logging.DEBUG if level <= logging.DEBUG else logging.WARNING
    )


__all__ = ["configure_logging"]
