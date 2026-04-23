"""
Versioned SQLite migrations driven by ``PRAGMA user_version``.

Design
------
Every migration is a function taking an open connection. They run in
order, and after each one runs we bump ``PRAGMA user_version`` so a
crash mid-routine resumes at the next boot without replaying the same
work.

Rules
-----
1. **Never edit a past migration.** It is part of the on-disk contract
   for every existing deployment. Write a new entry at the bottom
   instead, even for a small tweak.
2. **Prefer additive changes.** SQLite's ALTER TABLE only adds columns
   cleanly. Renames and type changes require table rebuilds — keep
   those for the rare case where correctness demands it.
3. **Each migration is idempotent.** Wrap ALTERs in try/except so a
   deployment that raced two processes during startup doesn't break.
4. **Baseline is migration 0 -> 1.** It handles both a fresh DB
   (creates every table) AND an existing pre-migration-aware DB (the
   tables already exist; the idempotent ALTERs are no-ops but the
   version bump is still meaningful).

Adding a migration
------------------
1. Write a function ``_apply_NNNN(conn)``.
2. Append ``(from_version, _apply_NNNN)`` to ``MIGRATIONS``.
3. Update ``TESTING.md`` / ``ASSUMPTIONS.md`` if the migration changes a
   user-visible rule.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from collections.abc import Callable

from .connection import DEFAULT_USER_ID
from .schema import BASELINE_DDL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Migration 0 -> 1: baseline
# ---------------------------------------------------------------------------


def _apply_baseline(conn: sqlite3.Connection) -> None:
    """Create every table + column that existed before migrations.

    Split into two passes because mid-2025 we were still evolving the
    schema by hand with ALTER TABLE. A fresh DB sees the baseline DDL
    (pass 1) create every table; the ALTERs in pass 2 are no-ops on a
    fresh DB but essential on an existing one that only has the oldest
    shape. Both paths land in the same final schema.
    """
    conn.executescript(BASELINE_DDL)
    conn.execute(
        "INSERT OR IGNORE INTO user (id, name) VALUES (?, 'Me')",
        (DEFAULT_USER_ID,),
    )

    for ddl in (
        "ALTER TABLE plant ADD COLUMN current_streak INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE plant ADD COLUMN longest_streak INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE plant ADD COLUMN badges_earned TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE care_template ADD COLUMN watering_frequency_display TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE care_template ADD COLUMN light_display TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE care_template ADD COLUMN description TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE care_template ADD COLUMN environment TEXT NOT NULL DEFAULT 'indoor'",
        "ALTER TABLE care_template ADD COLUMN category TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE care_template ADD COLUMN growing_instructions TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE care_template ADD COLUMN visual_type TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE plant ADD COLUMN category TEXT",
        "ALTER TABLE plant ADD COLUMN visual_type TEXT",
        "ALTER TABLE plant ADD COLUMN image_override TEXT",
        # Recommendation v2 phase 1 observation context columns. Nullable
        # on purpose — the first watering has no prior, and older rows
        # pre-dating this addition stay valid with NULLs.
        "ALTER TABLE observation ADD COLUMN previous_watered_date TEXT",
        "ALTER TABLE observation ADD COLUMN interval_days REAL",
        "ALTER TABLE observation ADD COLUMN was_on_time INTEGER",
    ):
        # Each ALTER may fail because the column is already present on
        # this DB — that's expected on any non-fresh install and means
        # the migration is already partially applied.
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(ddl)


# ---------------------------------------------------------------------------
# Migration 1 -> 2: recommendation v2 interval estimator
# ---------------------------------------------------------------------------


def _apply_v2_interval_estimator(conn: sqlite3.Connection) -> None:
    """Running interval statistics + per-plant life event log.

    * ``plant.interval_mean_days`` / ``interval_var_days`` /
      ``observation_count`` — EWMA mean + variance of observed watering
      intervals and a count of waterings integrated so far. Updated by
      ``log_watered`` on every call.
    * ``plant_event`` — per-plant life events (repot, move, light change,
      user break). Used to cap confidence when the environment recently
      changed, so a repot doesn't leak into the old interval's prediction.

    The stats start at NULL; a plant without history keeps the old
    ``drying_coefficient`` path. Once ``observation_count`` crosses the
    estimator threshold, the recommendation engine can start using these.
    """
    for ddl in (
        "ALTER TABLE plant ADD COLUMN interval_mean_days REAL",
        "ALTER TABLE plant ADD COLUMN interval_var_days REAL",
        "ALTER TABLE plant ADD COLUMN observation_count INTEGER NOT NULL DEFAULT 0",
    ):
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(ddl)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plant_event (
            id TEXT PRIMARY KEY,
            plant_id TEXT NOT NULL REFERENCES plant(id),
            at TEXT NOT NULL,
            kind TEXT NOT NULL,
            detail TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plant_event_plant_at "
        "ON plant_event (plant_id, at)"
    )


# ---------------------------------------------------------------------------
# Migration 2 -> 3: optional human place hint (left / by sink / …)
# ---------------------------------------------------------------------------


def _apply_v3_position_note(conn: sqlite3.Connection) -> None:
    """``plant.position_note`` — free text, optional, for kiosk recognition."""
    for ddl in (
        "ALTER TABLE plant ADD COLUMN position_note TEXT",
    ):
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(ddl)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


# Each entry: (from_version, migration_fn). Migration runs when the DB is
# at `from_version`, and afterwards ``user_version`` is bumped to
# ``from_version + 1``. NEVER reorder or edit past entries.
MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (0, _apply_baseline),
    (1, _apply_v2_interval_estimator),
    (2, _apply_v3_position_note),
]


def _current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _set_version(conn: sqlite3.Connection, v: int) -> None:
    # PRAGMA user_version doesn't accept parameter binding. `v` is an
    # int literal produced by our own code, not user input, so splicing
    # it into the string is safe here.
    conn.execute(f"PRAGMA user_version = {int(v)}")


def run_migrations(conn: sqlite3.Connection) -> int:
    """Apply every pending migration in order. Returns the final version.

    Idempotent — safe to call at every startup. Does nothing when the DB
    is already at the latest version.
    """
    current = _current_version(conn)
    for from_version, fn in MIGRATIONS:
        if current > from_version:
            continue
        logger.info("db: applying migration %d -> %d", from_version, from_version + 1)
        fn(conn)
        _set_version(conn, from_version + 1)
        current = from_version + 1
    conn.commit()
    return current


__all__ = ["MIGRATIONS", "run_migrations"]
