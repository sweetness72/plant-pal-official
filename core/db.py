"""
SQLite database: where your plant data lives.
DB file: data/plant_panel.db (inside the project directory).
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from .schema import (
    CareTemplate,
    LightLevel,
    MoisturePreference,
    Plant,
    PotMaterial,
)

# Project root: one level up from core/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "plant_panel.db"

# Default user for MVP (single-user)
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS user (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'Me'
            );
            CREATE TABLE IF NOT EXISTS care_template (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                default_drying_days INTEGER NOT NULL DEFAULT 7,
                moisture_preference TEXT NOT NULL DEFAULT 'evenly_moist',
                icon_id TEXT NOT NULL DEFAULT 'houseplant'
            );
            CREATE TABLE IF NOT EXISTS plant (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                template_id TEXT REFERENCES care_template(id),
                display_name TEXT NOT NULL,
                room_name TEXT NOT NULL,
                pot_diameter_inches INTEGER NOT NULL DEFAULT 8,
                pot_material TEXT NOT NULL DEFAULT 'plastic',
                light_level TEXT NOT NULL DEFAULT 'medium',
                last_watered_date TEXT,
                drying_coefficient REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                low_effort_mode INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS observation (
                id TEXT PRIMARY KEY,
                plant_id TEXT NOT NULL REFERENCES plant(id),
                observed_at TEXT NOT NULL,
                soil_feeling TEXT,
                action_taken TEXT NOT NULL
            );
            INSERT OR IGNORE INTO user (id, name) VALUES (?, 'Me');
        """)
        conn.execute("INSERT OR IGNORE INTO user (id, name) VALUES (?, 'Me')", (DEFAULT_USER_ID,))
        conn.commit()
        # Migration: add streak and badges columns if missing (existing DBs)
        for col_sql in (
            "ALTER TABLE plant ADD COLUMN current_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE plant ADD COLUMN longest_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE plant ADD COLUMN badges_earned TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE care_template ADD COLUMN watering_frequency_display TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE care_template ADD COLUMN light_display TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE care_template ADD COLUMN description TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE care_template ADD COLUMN environment TEXT NOT NULL DEFAULT 'indoor'",
            "ALTER TABLE care_template ADD COLUMN category TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE care_template ADD COLUMN growing_instructions TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(col_sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
    finally:
        conn.close()


def _date_to_str(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _str_to_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return date.fromisoformat(s)


def _parse_badges(s: Optional[str]) -> List[int]:
    if not s or not s.strip():
        return []
    return [int(x.strip()) for x in s.split(",") if x.strip().isdigit()]


def _plant_from_row(row: sqlite3.Row, template: Optional[CareTemplate]) -> Plant:
    return Plant(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        template=template,
        display_name=row["display_name"],
        room_name=row["room_name"],
        pot_diameter_inches=row["pot_diameter_inches"],
        pot_material=PotMaterial(row["pot_material"]),
        light_level=LightLevel(row["light_level"]),
        last_watered_date=_str_to_date(row["last_watered_date"]),
        drying_coefficient=row["drying_coefficient"],
        created_at=_str_to_date(row["created_at"]),
        low_effort_mode=bool(row["low_effort_mode"]),
        current_streak=row["current_streak"] if "current_streak" in row.keys() else 0,
        longest_streak=row["longest_streak"] if "longest_streak" in row.keys() else 0,
        badges_earned=_parse_badges(row["badges_earned"]) if "badges_earned" in row.keys() and row["badges_earned"] else [],
    )


def _template_from_row(r: sqlite3.Row) -> CareTemplate:
    return CareTemplate(
        id=UUID(r["id"]),
        name=r["name"],
        slug=r["slug"],
        default_drying_days=r["default_drying_days"],
        moisture_preference=MoisturePreference(r["moisture_preference"]),
        icon_id=r["icon_id"],
        watering_frequency_display=r["watering_frequency_display"] if "watering_frequency_display" in r.keys() else "",
        light_display=r["light_display"] if "light_display" in r.keys() else "",
        description=r["description"] if "description" in r.keys() else "",
        environment=r["environment"] if "environment" in r.keys() else "indoor",
        category=r["category"] if "category" in r.keys() else "",
        growing_instructions=r["growing_instructions"] if "growing_instructions" in r.keys() else "",
    )


def get_templates(environment: Optional[str] = None) -> List[CareTemplate]:
    """Load care templates, optionally filtered by environment ('indoor' | 'outdoor')."""
    conn = _get_conn()
    try:
        if environment and environment in ("indoor", "outdoor"):
            rows = conn.execute(
                "SELECT * FROM care_template WHERE environment = ? ORDER BY name",
                (environment,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM care_template ORDER BY environment, name").fetchall()
        return [_template_from_row(r) for r in rows]
    finally:
        conn.close()


def search_templates(
    query: str, limit: int = 25, environment: Optional[str] = None
) -> List[CareTemplate]:
    """
    Search templates by name or slug. Uses parameterized queries only (no SQL injection).
    Optional environment filter: 'indoor' | 'outdoor'.
    """
    conn = _get_conn()
    try:
        if not query or not query.strip():
            if environment and environment in ("indoor", "outdoor"):
                rows = conn.execute(
                    "SELECT * FROM care_template WHERE environment = ? ORDER BY name LIMIT ?",
                    (environment, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM care_template ORDER BY name LIMIT ?", (limit,)
                ).fetchall()
            return [_template_from_row(r) for r in rows]
        pattern = f"%{query.strip()}%"
        # Search name, slug, category, description, growing_instructions (parameterized only)
        if environment and environment in ("indoor", "outdoor"):
            rows = conn.execute(
                """SELECT * FROM care_template WHERE environment = ? AND (
                    name LIKE ? OR slug LIKE ? OR category LIKE ? OR description LIKE ? OR growing_instructions LIKE ?
                ) ORDER BY name LIMIT ?""",
                (environment, pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM care_template WHERE
                    name LIKE ? OR slug LIKE ? OR category LIKE ? OR description LIKE ? OR growing_instructions LIKE ?
                ORDER BY name LIMIT ?""",
                (pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        return [_template_from_row(r) for r in rows]
    finally:
        conn.close()


def get_plant(plant_id: str, user_id: str = DEFAULT_USER_ID) -> Optional[Plant]:
    """Load one plant by id, or None if not found."""
    conn = _get_conn()
    try:
        templates = {str(t.id): t for t in get_templates()}
        row = conn.execute(
            "SELECT * FROM plant WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        ).fetchone()
        if not row:
            return None
        tid = row["template_id"]
        template = templates.get(tid) if tid else None
        return _plant_from_row(row, template)
    finally:
        conn.close()


def get_plants(user_id: str = DEFAULT_USER_ID) -> List[Plant]:
    """Load all plants for a user, with templates joined."""
    conn = _get_conn()
    try:
        templates = {str(t.id): t for t in get_templates()}
        rows = conn.execute(
            "SELECT * FROM plant WHERE user_id = ? ORDER BY room_name, display_name",
            (user_id,),
        ).fetchall()
        plants = []
        for r in rows:
            tid = r["template_id"]
            template = templates.get(tid) if tid else None
            plant = _plant_from_row(r, template)
            plants.append(plant)
        return plants
    finally:
        conn.close()


def add_plant(
    display_name: str,
    room_name: str,
    pot_diameter_inches: int = 8,
    pot_material: str = "plastic",
    light_level: str = "medium",
    template_id: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
) -> Plant:
    """Insert a new plant. Assumes not yet watered (last_watered_date=None) for future iterations."""
    from uuid import uuid4

    conn = _get_conn()
    try:
        plant_id = str(uuid4())
        today = date.today().isoformat()
        conn.execute(
            """INSERT INTO plant (
                id, user_id, template_id, display_name, room_name,
                pot_diameter_inches, pot_material, light_level,
                last_watered_date, drying_coefficient, created_at, low_effort_mode,
                current_streak, longest_streak, badges_earned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, 0, 0, 0, '')""",
            (
                plant_id,
                user_id,
                template_id,
                display_name,
                room_name,
                pot_diameter_inches,
                pot_material,
                light_level,
                None,
                today,
            ),
        )
        conn.commit()
        plants = get_plants(user_id)
        return next(p for p in plants if str(p.id) == plant_id)
    finally:
        conn.close()


# Streak badges: only at these milestones (increments)
BADGE_MILESTONES = [3, 5, 10, 25, 50, 100, 250, 300, 500]


def log_watered(
    plant_id: str,
    watered_date: Optional[date] = None,
    soil_feeling: Optional[str] = None,
) -> None:
    """
    Update plant after user watered. Sets last_watered_date, applies learning
    (drying_coefficient from soil_feeling), and updates watering streak + badges.
    "On time" = watered on due date or within 1 day before/after.
    """
    from .drying_model import predicted_dry_date

    watered_date = watered_date or date.today()
    plant = get_plant(plant_id)
    if not plant:
        return
    conn = _get_conn()
    try:
        coef = plant.drying_coefficient
        if soil_feeling == "wet":
            coef = min(1.5, coef + 0.1)
        elif soil_feeling == "dry":
            coef = max(0.5, coef - 0.1)
        elif soil_feeling == "ok":
            if coef < 1.0:
                coef = min(1.0, coef + 0.05)
            elif coef > 1.0:
                coef = max(1.0, coef - 0.05)

        # Streak: was this watering "on time"? (due date or within ±1 day)
        dry_date = predicted_dry_date(plant, watered_date)
        if dry_date is None:
            # First time watered (was never watered) → start streak at 1
            on_time = True
            new_streak = 1
        else:
            on_time = dry_date - timedelta(days=1) <= watered_date <= dry_date + timedelta(days=1)
            new_streak = (plant.current_streak + 1) if on_time else 0

        new_longest = max(plant.longest_streak, new_streak)
        badges = list(plant.badges_earned)
        for m in BADGE_MILESTONES:
            if new_streak >= m and m not in badges:
                badges.append(m)
        badges.sort()
        badges_str = ",".join(str(b) for b in badges)

        conn.execute(
            """UPDATE plant SET last_watered_date = ?, drying_coefficient = ?,
               current_streak = ?, longest_streak = ?, badges_earned = ? WHERE id = ?""",
            (watered_date.isoformat(), coef, new_streak, new_longest, badges_str, plant_id),
        )
        conn.commit()
    finally:
        conn.close()


def remove_plant(plant_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Remove a plant and its observations. Returns True if a row was deleted."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM observation WHERE plant_id = ?", (plant_id,))
        cur = conn.execute("DELETE FROM plant WHERE id = ? AND user_id = ?", (plant_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def seed_templates_if_empty() -> None:
    """Insert plant library when table is empty. All inserts use parameterized queries (no SQL injection)."""
    conn = _get_conn()
    try:
        if conn.execute("SELECT 1 FROM care_template LIMIT 1").fetchone():
            return
        from uuid import uuid4

        from .plant_library_data import PLANT_LIBRARY, get_category_and_growing, get_icon_id, slug_from_name

        for item in PLANT_LIBRARY:
            name, watering_display, light_display, description, days, pref, env = item
            slug = slug_from_name(name)
            category, growing = get_category_and_growing(slug, env)
            icon_id = get_icon_id(slug, env)
            template_id = str(uuid4())
            conn.execute(
                """INSERT INTO care_template (
                    id, name, slug, default_drying_days, moisture_preference, icon_id,
                    watering_frequency_display, light_display, description, environment, category, growing_instructions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    template_id,
                    name,
                    slug,
                    days,
                    pref,
                    icon_id,
                    watering_display,
                    light_display,
                    description,
                    env,
                    category,
                    growing,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def seed_example_plants_if_empty() -> None:
    """If no plants exist, add example plants with fixed last_watered dates so tomorrow shows different actions."""
    if get_plants():
        return
    templates = get_templates()
    by_slug = {t.slug: t for t in templates}
    today = date.today()

    def add(name: str, room: str, slug: Optional[str], pot: int, material: str, light: str, last_watered: Optional[date]):
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

    add("Living Room Fig", "Living Room", "fiddle-leaf-fig", 14, "ceramic", "bright", today - timedelta(days=8))
    add("Office Snake Plant", "Office", "snake-plant", 8, "plastic", "low", today - timedelta(days=5))
    add("Bathroom Fern", "Bathroom", "boston-fern", 6, "terracotta", "medium", today - timedelta(days=4))
    add("Mystery Plant", "Kitchen", None, 10, "plastic", "medium", None)


def seed_library_backfill() -> None:
    """Add any plant library entries that are not yet in care_template (for existing DBs). Parameterized only."""
    from uuid import uuid4

    from .plant_library_data import PLANT_LIBRARY, get_category_and_growing, get_icon_id, slug_from_name

    conn = _get_conn()
    try:
        for item in PLANT_LIBRARY:
            name, watering_display, light_display, description, days, pref, env = item
            slug = slug_from_name(name)
            category, growing = get_category_and_growing(slug, env)
            icon_id = get_icon_id(slug, env)
            existing = conn.execute(
                "SELECT 1 FROM care_template WHERE slug = ? AND environment = ?",
                (slug, env),
            ).fetchone()
            if existing:
                try:
                    conn.execute(
                        "UPDATE care_template SET category = ?, growing_instructions = ?, icon_id = ? WHERE slug = ? AND environment = ?",
                        (category, growing, icon_id, slug, env),
                    )
                except Exception:
                    pass
                continue
            template_id = str(uuid4())
            conn.execute(
                """INSERT INTO care_template (
                    id, name, slug, default_drying_days, moisture_preference, icon_id,
                    watering_frequency_display, light_display, description, environment, category, growing_instructions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (template_id, name, slug, days, pref, icon_id, watering_display, light_display, description, env, category, growing),
            )
        conn.commit()
    finally:
        conn.close()


def ensure_seeded() -> None:
    """Call after init_db: seed templates if empty, then backfill any missing library plants."""
    seed_templates_if_empty()
    seed_library_backfill()
