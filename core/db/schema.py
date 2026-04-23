"""
Baseline DDL.

Kept declarative so migrations.py can read it and apply it as one shot on
a fresh DB. New columns / tables belong in a numbered migration in
``migrations.py``, not in this file.
"""

from __future__ import annotations

# Matches the shape that existed before migrations were a thing — the
# migration runner layers additional columns on top via ALTER TABLE.
# Every statement is IF NOT EXISTS so this is safe to re-run.
BASELINE_DDL = """
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
"""


__all__ = ["BASELINE_DDL"]
