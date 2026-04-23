"""Integration tests for the coefficient-learning rules in ``core.db.log_watered``.

The drying engine itself only *consumes* ``plant.drying_coefficient``; the
learning rule that adjusts it based on the user's "how did the soil feel?"
reply lives in ``core.db.log_watered``. Rather than refactor that into a
pure function (out of scope for this test pass), we exercise it through a
real sqlite database pointed at a tmp file.

Rules under test (from ``core.db.log_watered``), after ``observation_count`` ≥ 3
(full steps; first three waterings use half-sized steps — see
``_soil_feedback_step_scale``):
  - "wet"   -> coef = min(1.5, coef + 0.1)     (takes longer to dry)
  - "dry"   -> coef = max(0.5, coef - 0.1)     (dries faster)
  - "ok"    -> coef drifts back toward 1.0 by 0.05 per observation
  - other   -> coef unchanged
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import db as db_module


def _add_plant(display_name: str = "Fern") -> str:
    plant = db_module.add_plant(
        display_name=display_name,
        room_name="Lab",
        pot_diameter_inches=8,
        pot_material="plastic",
        light_level="medium",
        template_id=None,
    )
    return str(plant.id)


def _get_coef(plant_id: str) -> float:
    plant = db_module.get_plant(plant_id)
    assert plant is not None
    return plant.drying_coefficient


class TestLogWateredLearning:
    def test_wet_feedback_increases_coefficient(self, tmp_db):
        pid = _add_plant()
        assert _get_coef(pid) == 1.0
        db_module.log_watered(pid, soil_feeling="wet")
        assert _get_coef(pid) == pytest.approx(1.05, abs=1e-6)

    def test_dry_feedback_decreases_coefficient(self, tmp_db):
        pid = _add_plant()
        db_module.log_watered(pid, soil_feeling="dry")
        assert _get_coef(pid) == pytest.approx(0.95, abs=1e-6)

    def test_full_soil_steps_after_three_prior_waterings(self, tmp_db):
        pid = _add_plant()
        for i in range(3):
            db_module.log_watered(
                pid,
                watered_date=date(2024, 1, 1) + timedelta(days=i),
                soil_feeling="ok",
            )
        assert db_module.get_plant(pid).observation_count == 3
        db_module.log_watered(
            pid,
            watered_date=date(2024, 1, 10),
            soil_feeling="wet",
        )
        assert _get_coef(pid) == pytest.approx(1.1, abs=1e-6)

    def test_wet_is_capped_at_1_5(self, tmp_db):
        pid = _add_plant()
        # Nudge wet many times; should plateau at 1.5.
        for i in range(10):
            db_module.log_watered(
                pid,
                watered_date=date(2024, 1, 1) + timedelta(days=i),
                soil_feeling="wet",
            )
        assert _get_coef(pid) == pytest.approx(1.5, abs=1e-6)

    def test_dry_is_floored_at_0_5(self, tmp_db):
        pid = _add_plant()
        for i in range(10):
            db_module.log_watered(
                pid,
                watered_date=date(2024, 1, 1) + timedelta(days=i),
                soil_feeling="dry",
            )
        assert _get_coef(pid) == pytest.approx(0.5, abs=1e-6)

    def test_ok_drifts_back_toward_one_from_below(self, tmp_db):
        pid = _add_plant()
        # Two "dry" observations (half steps) -> 0.9, then "ok" nudges up by 0.025.
        db_module.log_watered(pid, watered_date=date(2024, 1, 1), soil_feeling="dry")
        db_module.log_watered(pid, watered_date=date(2024, 1, 2), soil_feeling="dry")
        assert _get_coef(pid) == pytest.approx(0.9, abs=1e-6)
        db_module.log_watered(pid, watered_date=date(2024, 1, 3), soil_feeling="ok")
        assert _get_coef(pid) == pytest.approx(0.925, abs=1e-6)

    def test_ok_drifts_back_toward_one_from_above(self, tmp_db):
        pid = _add_plant()
        db_module.log_watered(pid, watered_date=date(2024, 1, 1), soil_feeling="wet")
        db_module.log_watered(pid, watered_date=date(2024, 1, 2), soil_feeling="wet")
        assert _get_coef(pid) == pytest.approx(1.1, abs=1e-6)
        db_module.log_watered(pid, watered_date=date(2024, 1, 3), soil_feeling="ok")
        assert _get_coef(pid) == pytest.approx(1.075, abs=1e-6)

    def test_ok_when_already_one_is_noop(self, tmp_db):
        pid = _add_plant()
        db_module.log_watered(pid, soil_feeling="ok")
        # Both branches of the "ok" rule guard with strict < / > so 1.0 is stable.
        assert _get_coef(pid) == pytest.approx(1.0, abs=1e-6)

    def test_unknown_feedback_does_not_change_coef(self, tmp_db):
        pid = _add_plant()
        db_module.log_watered(pid, soil_feeling="soaking")  # not one of the 3 keys
        assert _get_coef(pid) == pytest.approx(1.0, abs=1e-6)

    def test_no_feedback_does_not_change_coef(self, tmp_db):
        pid = _add_plant()
        db_module.log_watered(pid)  # soil_feeling=None
        assert _get_coef(pid) == pytest.approx(1.0, abs=1e-6)

    def test_log_watered_updates_last_watered_date(self, tmp_db):
        pid = _add_plant()
        when = date(2024, 1, 15)
        db_module.log_watered(pid, watered_date=when, soil_feeling="ok")
        plant = db_module.get_plant(pid)
        assert plant is not None
        assert plant.last_watered_date == when


class TestStreakFirstAndSecondWatering:
    """First watering must use ``last_watered_date is None``, not ``predicted_dry_date``, for streak (B1)."""

    def test_add_then_first_water_same_calendar_day_streak_is_one(self, tmp_db):
        day0 = date(2025, 3, 10)
        plant = db_module.add_plant(
            display_name="StreakA",
            room_name="Lab",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
            template_id=None,
        )
        db_module.log_watered(str(plant.id), watered_date=day0, soil_feeling="ok")
        after = db_module.get_plant(str(plant.id))
        assert after is not None
        assert after.current_streak == 1
        assert after.longest_streak == 1

    def test_second_watering_on_time_increments_streak(self, tmp_db):
        day0 = date(2025, 3, 10)
        plant = db_module.add_plant(
            display_name="StreakB",
            room_name="Lab",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
            template_id=None,
        )
        db_module.log_watered(str(plant.id), watered_date=day0, soil_feeling="ok")
        # No template: 7-day base, coef 1.0 → next dry ~day0+7; watering then is on-time.
        db_module.log_watered(
            str(plant.id), watered_date=day0 + timedelta(days=7), soil_feeling="ok"
        )
        after = db_module.get_plant(str(plant.id))
        assert after is not None
        assert after.current_streak == 2
