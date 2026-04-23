"""
SQLite connection + shared constants + value clamps.

Every caller goes through ``_get_conn()`` so DB path setup lives in one
place. ``DB_PATH`` and ``DATA_DIR`` are defined here and re-exported by
``core.db.__init__``. ``_get_conn`` resolves them from the package at
call time — that preserves the long-standing test pattern of
``monkeypatch.setattr(db_module, "DB_PATH", tmp)`` without needing to
teach every test about the new package layout.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Project root: three levels up (core/db/connection.py -> repo root).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

DATA_DIR: Path = _DEFAULT_DATA_DIR
DB_PATH: Path = _DEFAULT_DATA_DIR / "plant_panel.db"

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"

# Bounds documented in ASSUMPTIONS.md. Writers call the clamp helpers so
# corrupt values never land on disk.
COEFFICIENT_MIN = 0.5
COEFFICIENT_MAX = 1.5
DRYING_DAYS_MIN = 2
DRYING_DAYS_MAX = 60


def _get_conn() -> sqlite3.Connection:
    """Open a new SQLite connection.

    Reads ``DB_PATH`` and ``DATA_DIR`` from the top-level ``core.db``
    package, not this module. That way a test's
    ``monkeypatch.setattr(core.db, "DB_PATH", tmp)`` takes effect
    immediately without the test having to also patch
    ``core.db.connection.DB_PATH``.
    """
    # Local import avoids a circular import at module load; by the time
    # _get_conn is actually called, core.db has finished initializing.
    from core import db as _pkg

    _pkg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_pkg.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _clamp_coefficient(c: float) -> float:
    """Pin learning coefficient to the documented [0.5, 1.5] band."""
    return max(COEFFICIENT_MIN, min(COEFFICIENT_MAX, float(c)))


def _clamp_drying_days(d: int) -> int:
    """Pin template drying-day base to a sane [2, 60] band before storing."""
    return max(DRYING_DAYS_MIN, min(DRYING_DAYS_MAX, int(d)))


__all__ = [
    "COEFFICIENT_MAX",
    "COEFFICIENT_MIN",
    "DATA_DIR",
    "DB_PATH",
    "DEFAULT_USER_ID",
    "DRYING_DAYS_MAX",
    "DRYING_DAYS_MIN",
    "PROJECT_ROOT",
    "_clamp_coefficient",
    "_clamp_drying_days",
    "_get_conn",
]
