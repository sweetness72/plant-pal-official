"""Shared pytest helpers.

`make_plant` and `make_template` keep pure engine tests focused. The
``tmp_db`` fixture is the single place we point ``core.db`` at an isolated
SQLite file so integration tests never touch ``data/plant_panel.db``.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Optional

import pytest

from core.schema import (
    CareTemplate,
    LightLevel,
    MoisturePreference,
    Plant,
    PotMaterial,
)


def _make_template(
    *,
    default_drying_days: int = 7,
    moisture_preference: MoisturePreference = MoisturePreference.EVENLY_MOIST,
) -> CareTemplate:
    return CareTemplate(
        name="Test Template",
        slug="test-template",
        default_drying_days=default_drying_days,
        moisture_preference=moisture_preference,
    )


def _make_plant(
    *,
    pot_diameter_inches: int = 8,
    pot_material: PotMaterial = PotMaterial.PLASTIC,
    light_level: LightLevel = LightLevel.MEDIUM,
    last_watered_date: Optional[date] = None,
    created_at: Optional[date] = None,
    drying_coefficient: float = 1.0,
    template: Optional[CareTemplate] = None,
    current_streak: int = 0,
    longest_streak: int = 0,
    badges_earned: Optional[list[int]] = None,
    interval_mean_days: Optional[float] = None,
    interval_var_days: Optional[float] = None,
    observation_count: int = 0,
    position_note: Optional[str] = None,
) -> Plant:
    return Plant(
        display_name="Testy",
        room_name="Lab",
        position_note=position_note,
        pot_diameter_inches=pot_diameter_inches,
        pot_material=pot_material,
        light_level=light_level,
        last_watered_date=last_watered_date,
        created_at=created_at,
        drying_coefficient=drying_coefficient,
        template=template,
        current_streak=current_streak,
        longest_streak=longest_streak,
        badges_earned=list(badges_earned or []),
        interval_mean_days=interval_mean_days,
        interval_var_days=interval_var_days,
        observation_count=observation_count,
    )


@pytest.fixture
def make_template():
    """Factory for CareTemplate with sensible defaults."""
    return _make_template


@pytest.fixture
def make_plant():
    """Factory for Plant with sensible defaults. Override only what the test cares about."""
    return _make_plant


@pytest.fixture
def clone():
    """Return a shallow dataclass copy helper so tests don't mutate fixtures by accident."""
    return replace


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point ``core.db`` at an isolated SQLite file and run migrations.

    Patches ``DB_PATH`` and ``DATA_DIR`` together so ``_get_conn`` and any
    path logic match production. Use this for ``log_watered``,
    ``get_plants``, ``core.service``, etc.

    The filename is fixed so stack traces are easy to grep; each test
    run still uses a fresh ``tmp_path``.
    """
    from core import db as db_module

    path = tmp_path / "plantpal_test.db"
    monkeypatch.setattr(db_module, "DB_PATH", path)
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)
    db_module.init_db()
    return path
