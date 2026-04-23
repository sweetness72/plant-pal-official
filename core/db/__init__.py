"""
Database package.

Historically ``core/db.py`` was a single ~700-line module. It's now a
package split by concern:

* ``connection``  — paths, ``_get_conn``, clamp helpers, constants.
* ``schema``      — baseline DDL.
* ``migrations``  — versioned migration runner (``PRAGMA user_version``).
* ``seeds``       — idempotent template/library/visual-type seeding.
* ``queries``     — CRUD + learning logic (``log_watered``).

Every public name that used to be importable from ``core.db`` still is,
so call sites like ``from core.db import get_plants`` did not change.

Tests that monkeypatch ``core.db.DB_PATH`` / ``core.db.DATA_DIR`` keep
working because ``_get_conn`` re-resolves those names from this package
at call time.
"""

from __future__ import annotations

import logging

from .connection import (
    COEFFICIENT_MAX,
    COEFFICIENT_MIN,
    DATA_DIR,
    DB_PATH,
    DEFAULT_USER_ID,
    DRYING_DAYS_MAX,
    DRYING_DAYS_MIN,
    _clamp_coefficient,
    _clamp_drying_days,
    _get_conn,
)
from .migrations import run_migrations
from .queries import (
    BADGE_MILESTONES,
    LIFE_EVENT_KINDS,
    add_plant,
    get_observation_history,
    get_plant,
    get_plants,
    get_recent_events,
    get_templates,
    log_watered,
    record_event,
    remove_plant,
    search_templates,
    update_plant,
)
from .seeds import (
    ensure_seeded,
    seed_example_plants_if_empty,
    seed_library_backfill,
    seed_templates_if_empty,
    sync_template_visual_types,
)

logger = logging.getLogger(__name__)


def init_db() -> None:
    """Apply every pending migration. Idempotent — safe at every startup."""
    conn = _get_conn()
    try:
        v = run_migrations(conn)
        logger.info("db: init complete schema_version=%d", v)
    finally:
        conn.close()


__all__ = [
    "BADGE_MILESTONES",
    "COEFFICIENT_MAX",
    "COEFFICIENT_MIN",
    "DATA_DIR",
    "DB_PATH",
    "DEFAULT_USER_ID",
    "DRYING_DAYS_MAX",
    "DRYING_DAYS_MIN",
    "LIFE_EVENT_KINDS",
    "_clamp_coefficient",
    "_clamp_drying_days",
    "_get_conn",
    "add_plant",
    "update_plant",
    "ensure_seeded",
    "get_observation_history",
    "get_plant",
    "get_plants",
    "get_recent_events",
    "get_templates",
    "init_db",
    "log_watered",
    "record_event",
    "remove_plant",
    "run_migrations",
    "search_templates",
    "seed_example_plants_if_empty",
    "seed_library_backfill",
    "seed_templates_if_empty",
    "sync_template_visual_types",
]
