"""
Seed / backfill routines.

These are idempotent — safe to call at every startup via the FastAPI
lifespan hook. Fresh DB? We insert the whole library. Existing DB that
ran an older library? We backfill missing entries and sync the
visual-type column. Already up to date? We no-op.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from datetime import date, timedelta
from uuid import uuid4

from .connection import _clamp_drying_days, _get_conn
from .queries import add_plant, get_plants, get_templates

logger = logging.getLogger(__name__)


def seed_templates_if_empty() -> None:
    """Insert the plant library when ``care_template`` is empty.

    Parameterized only. Runs once on a fresh DB; becomes a no-op on
    subsequent boots once at least one row exists.
    """
    from ..plant_library_data import (
        PLANT_LIBRARY,
        get_category_and_growing,
        get_icon_id,
        slug_from_name,
    )
    from ..plant_visual_seed import visual_type_for_slug_env

    conn = _get_conn()
    try:
        if conn.execute("SELECT 1 FROM care_template LIMIT 1").fetchone():
            return

        for item in PLANT_LIBRARY:
            name, watering_display, light_display, description, days, pref, env = item
            slug = slug_from_name(name)
            category, growing = get_category_and_growing(slug, env)
            icon_id = get_icon_id(slug, env)
            vtype = visual_type_for_slug_env(slug, env)
            template_id = str(uuid4())
            conn.execute(
                """INSERT INTO care_template (
                    id, name, slug, default_drying_days, moisture_preference, icon_id,
                    watering_frequency_display, light_display, description,
                    environment, category, growing_instructions, visual_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template_id,
                    name,
                    slug,
                    _clamp_drying_days(days),
                    pref,
                    icon_id,
                    watering_display,
                    light_display,
                    description,
                    env,
                    category,
                    growing,
                    vtype,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def seed_library_backfill() -> None:
    """Add library rows missing from ``care_template`` on older DBs.

    This is the "library grew since you installed" path. We insert new
    rows and update the lightweight metadata (category, growing,
    icon_id, visual_type) on existing rows so the library view stays
    consistent.
    """
    from ..plant_library_data import (
        PLANT_LIBRARY,
        get_category_and_growing,
        get_icon_id,
        slug_from_name,
    )
    from ..plant_visual_seed import visual_type_for_slug_env

    conn = _get_conn()
    try:
        for item in PLANT_LIBRARY:
            name, watering_display, light_display, description, days, pref, env = item
            slug = slug_from_name(name)
            category, growing = get_category_and_growing(slug, env)
            icon_id = get_icon_id(slug, env)
            vtype = visual_type_for_slug_env(slug, env)
            existing = conn.execute(
                "SELECT 1 FROM care_template WHERE slug = ? AND environment = ?",
                (slug, env),
            ).fetchone()
            if existing:
                # Rare: the update races a mid-migration schema change.
                # Backfill is best-effort; next boot re-runs it.
                with contextlib.suppress(sqlite3.OperationalError):
                    conn.execute(
                        """UPDATE care_template
                              SET category = ?, growing_instructions = ?,
                                  icon_id = ?, visual_type = ?
                            WHERE slug = ? AND environment = ?""",
                        (category, growing, icon_id, vtype, slug, env),
                    )
                continue
            template_id = str(uuid4())
            conn.execute(
                """INSERT INTO care_template (
                    id, name, slug, default_drying_days, moisture_preference, icon_id,
                    watering_frequency_display, light_display, description,
                    environment, category, growing_instructions, visual_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template_id,
                    name,
                    slug,
                    _clamp_drying_days(days),
                    pref,
                    icon_id,
                    watering_display,
                    light_display,
                    description,
                    env,
                    category,
                    growing,
                    vtype,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def sync_template_visual_types() -> None:
    """Keep ``care_template.visual_type`` aligned with ``plant_visual_seed``.

    Safe to run often — the visual-seed map grows over time and we want
    every boot to converge on the latest mapping without needing a
    migration per addition.
    """
    from ..plant_visual_seed import visual_type_for_slug_env

    conn = _get_conn()
    try:
        try:
            rows = conn.execute(
                "SELECT slug, environment FROM care_template"
            ).fetchall()
        except sqlite3.OperationalError:
            return
        for r in rows:
            vt = visual_type_for_slug_env(r["slug"], r["environment"])
            try:
                conn.execute(
                    "UPDATE care_template SET visual_type = ? WHERE slug = ? AND environment = ?",
                    (vt, r["slug"], r["environment"]),
                )
            except sqlite3.OperationalError:
                return
        conn.commit()
    finally:
        conn.close()


def seed_example_plants_if_empty() -> None:
    """Populate a demo set of plants on a brand-new install.

    Used by the /dev routes and the first-run experience — not called by
    ``ensure_seeded``, because adding fake plants to a real user's DB is
    a rude default.
    """
    if get_plants():
        return
    templates = get_templates()
    by_slug = {t.slug: t for t in templates}
    today = date.today()

    def add(
        name: str,
        room: str,
        slug: str | None,
        pot: int,
        material: str,
        light: str,
        last_watered: date | None,
    ) -> None:
        tid = str(by_slug[slug].id) if slug and slug in by_slug else None
        p = add_plant(
            display_name=name,
            room_name=room,
            pot_diameter_inches=pot,
            pot_material=material,
            light_level=light,
            template_id=tid,
        )
        if last_watered is not None:
            conn = _get_conn()
            try:
                conn.execute(
                    "UPDATE plant SET last_watered_date = ? WHERE id = ?",
                    (last_watered.isoformat(), str(p.id)),
                )
                conn.commit()
            finally:
                conn.close()

    add(
        "Living Room Fig", "Living Room", "fiddle-leaf-fig", 14, "ceramic", "bright",
        today - timedelta(days=8),
    )
    add(
        "Office Snake Plant", "Office", "snake-plant", 8, "plastic", "low",
        today - timedelta(days=5),
    )
    add(
        "Bathroom Fern", "Bathroom", "boston-fern", 6, "terracotta", "medium",
        today - timedelta(days=4),
    )
    add("Mystery Plant", "Kitchen", None, 10, "plastic", "medium", None)


def ensure_seeded() -> None:
    """Seed templates if empty, backfill any missing library rows, sync visuals."""
    seed_templates_if_empty()
    seed_library_backfill()
    sync_template_visual_types()
    logger.info("seed: library and templates checked")


__all__ = [
    "ensure_seeded",
    "seed_example_plants_if_empty",
    "seed_library_backfill",
    "seed_templates_if_empty",
    "sync_template_visual_types",
]
