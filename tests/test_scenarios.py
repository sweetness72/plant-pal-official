"""End-to-end scenario tests: archetype plants and multi-step user flows.

The goal here is different from ``test_drying_model.py``:

  * ``test_drying_model.py`` tests pure functions in isolation.
  * ``test_scenarios.py`` walks the engine through a realistic sequence
    of days so that a regression in ONE rule (coefficient, modifier,
    streak, badge) has a visible blast radius on a user-facing story.

Scenarios are chosen to cover the three moisture archetypes the app
explicitly markets against:

  * DRY_BETWEEN    → cactus-like (long interval, terracotta, bright)
  * EVENLY_MOIST   → houseplant default
  * MOIST_OFTEN    → fern-like (short interval, plastic, medium)

See ``ASSUMPTIONS.md`` for the thresholds these tests depend on.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import db as db_module
from core.drying_model import generate_action_for_plant
from core.schema import ActionType, LightLevel, MoisturePreference, PotMaterial


# ===========================================================================
# Archetype lifecycles (pure-function / engine level)
# ===========================================================================


class TestCactusLifecycle:
    """Cactus-like plant: DRY_BETWEEN, 14-day template, terracotta, bright.

    Effective interval:
        base 14 + moisture(+1) + terracotta(-1) + bright(-1) + size(0)
        = 13 days, × coef 1.0 = 13.

    Expected story over 20 days after a fresh watering:
        day 0   — just watered, silence
        day 6   — silence (not near dry)
        day 11  — silence (still not the day-before)
        day 12  — CHECK (day before dry, coef==1.0)
        day 13  — WATER (dry today)
        day 15  — WATER (overdue; same action_type, no escalation — see L7)
    """

    WATERED = date(2024, 6, 1)

    @pytest.fixture
    def cactus(self, make_plant, make_template):
        template = make_template(
            default_drying_days=14,
            moisture_preference=MoisturePreference.DRY_BETWEEN,
        )
        return make_plant(
            pot_diameter_inches=8,
            pot_material=PotMaterial.TERRACOTTA,
            light_level=LightLevel.BRIGHT,
            template=template,
            last_watered_date=self.WATERED,
        )

    def test_silence_early_in_cycle(self, cactus):
        for offset in (0, 1, 6, 11):
            assert generate_action_for_plant(cactus, self.WATERED + timedelta(days=offset)) is None, (
                f"expected silence at day {offset}"
            )

    def test_check_day_before_due(self, cactus):
        action = generate_action_for_plant(cactus, self.WATERED + timedelta(days=12))
        assert action is not None
        assert action.action_type == ActionType.CHECK

    def test_water_on_and_after_due(self, cactus):
        for offset in (13, 14, 15, 30):
            action = generate_action_for_plant(cactus, self.WATERED + timedelta(days=offset))
            assert action is not None, f"expected WATER at day {offset}"
            assert action.action_type == ActionType.WATER


class TestFernLifecycle:
    """Fern-like plant: MOIST_OFTEN, 5-day template, plastic, medium.

    Effective interval:
        base 5 + moisture(-1) + plastic(0) + medium(0) + size(0)
        = 4 days, × coef 1.0 = 4.
    """

    WATERED = date(2024, 6, 1)

    @pytest.fixture
    def fern(self, make_plant, make_template):
        template = make_template(
            default_drying_days=5,
            moisture_preference=MoisturePreference.MOIST_OFTEN,
        )
        return make_plant(
            pot_diameter_inches=6,
            pot_material=PotMaterial.PLASTIC,
            light_level=LightLevel.MEDIUM,
            template=template,
            last_watered_date=self.WATERED,
        )

    def test_silence_early(self, fern):
        for offset in (0, 1, 2):
            assert generate_action_for_plant(fern, self.WATERED + timedelta(days=offset)) is None

    def test_check_on_day_three(self, fern):
        action = generate_action_for_plant(fern, self.WATERED + timedelta(days=3))
        assert action is not None
        assert action.action_type == ActionType.CHECK

    def test_water_from_day_four(self, fern):
        for offset in (4, 5, 6, 10):
            action = generate_action_for_plant(fern, self.WATERED + timedelta(days=offset))
            assert action is not None
            assert action.action_type == ActionType.WATER


# ===========================================================================
# Feedback sequences (integration: log_watered updates coefficient + streak)
# ===========================================================================


class TestFeedbackSequences:
    """Multi-event sequences exercise the learning rule and its interaction
    with ``should_emit_check``'s ``coef == 1.0`` gate.
    """

    def test_wet_then_ok_never_returns_to_exact_one_point_zero(self, tmp_db):
        """After one "wet" (half step while history is short → 1.05), "ok"
        pulls it DOWN by a half ok-step → 1.025, never exactly 1.0.
        This is intentional hysteresis; CHECK's ``coef == 1.0`` gate stays closed.
        See design note D2.
        """
        plant = db_module.add_plant("WP", "Room", 8, "plastic", "medium", None)
        pid = str(plant.id)

        db_module.log_watered(pid, soil_feeling="wet")
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(1.05)

        db_module.log_watered(pid, soil_feeling="ok")
        coef = db_module.get_plant(pid).drying_coefficient
        assert coef == pytest.approx(1.025)
        assert coef != 1.0  # the CHECK gate will stay closed

    def test_wet_then_dry_returns_to_exact_one_point_zero(self, tmp_db):
        """With damped first steps, wet (+0.05) then dry (−0.05) still reach
        exactly 1.0 so CHECK actions can resume. Pinned for ``should_emit_check``.
        """
        plant = db_module.add_plant("WD", "Room", 8, "plastic", "medium", None)
        pid = str(plant.id)

        db_module.log_watered(pid, soil_feeling="wet")
        db_module.log_watered(pid, soil_feeling="dry")
        coef = db_module.get_plant(pid).drying_coefficient
        assert coef == pytest.approx(1.0, abs=1e-9)

    def test_ok_drift_caps_at_one_point_zero_from_below(self, tmp_db):
        """Repeated "ok" feedback from below 1.0 drifts up but stops at 1.0."""
        plant = db_module.add_plant("Drift", "Room", 8, "plastic", "medium", None)
        pid = str(plant.id)
        db_module.log_watered(pid, soil_feeling="dry")  # 0.9
        db_module.log_watered(pid, soil_feeling="dry")  # 0.8
        for _ in range(20):
            db_module.log_watered(pid, soil_feeling="ok")
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(1.0, abs=1e-9)


# ===========================================================================
# Streak / badge regression (integration)
# ===========================================================================


class TestStreakAndBadges:
    """Regression tests for the streak + badge behavior that is visible to
    users on the landing page. Note: these tests pin CURRENT behavior,
    which is affected by bug B1 (see ``test_known_issues.py``). If B1 is
    fixed, one of these tests will need to shift by one watering.
    """

    def _add(self, name: str = "Streaky"):
        plant = db_module.add_plant(name, "Lab", 8, "plastic", "medium", None)
        return str(plant.id)

    def _set_last_watered(self, plant_id: str, d: date):
        # Helper: force a specific last_watered_date so the NEXT log_watered
        # call sits on the due date exactly, avoiding the B1 interaction.
        import sqlite3

        conn = sqlite3.connect(db_module.DB_PATH)
        try:
            conn.execute(
                "UPDATE plant SET last_watered_date = ? WHERE id = ?",
                (d.isoformat(), plant_id),
            )
            conn.commit()
        finally:
            conn.close()

    def test_three_consecutive_on_time_waterings_earn_first_badge(self, tmp_db):
        """Three on-time waterings in a row earn the milestone[3] badge.

        We seed the plant with an explicit last_watered_date so the first
        log_watered sits on the due date (7 days later) — otherwise B1
        silently swallows the first point of streak.
        """
        pid = self._add()
        day0 = date(2024, 1, 1)
        self._set_last_watered(pid, day0)

        db_module.log_watered(pid, watered_date=day0 + timedelta(days=7))
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=14))
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=21))

        after = db_module.get_plant(pid)
        assert after is not None
        assert after.current_streak == 3
        assert 3 in after.badges_earned

    def test_late_watering_resets_streak(self, tmp_db):
        """Watering 3 days late (outside the ±1 window) resets streak to 0."""
        pid = self._add()
        day0 = date(2024, 1, 1)
        self._set_last_watered(pid, day0)

        db_module.log_watered(pid, watered_date=day0 + timedelta(days=7))   # on time
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=14))  # on time
        after = db_module.get_plant(pid)
        assert after.current_streak == 2

        # Skip ahead to day 24: 3 days past the dry date. Outside ±1 window.
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=24))
        after = db_module.get_plant(pid)
        assert after.current_streak == 0
        assert after.longest_streak == 2  # preserved high-water mark

    def test_on_time_window_is_plus_or_minus_one_day(self, tmp_db):
        """The ±1-day tolerance is a hard threshold. Day-before and
        day-after both count; 2 days off does not.

        current behavior, may change later.
        """
        pid = self._add()
        day0 = date(2024, 1, 1)
        self._set_last_watered(pid, day0)

        # due on day 7; water on day 6 (1 day early) → on time
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=6))
        assert db_module.get_plant(pid).current_streak == 1

        # due on day 13 (6 + 7); water on day 14 (1 day late) → on time
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=14))
        assert db_module.get_plant(pid).current_streak == 2

        # due on day 21 (14 + 7); water on day 19 (2 days early) → reset
        db_module.log_watered(pid, watered_date=day0 + timedelta(days=19))
        assert db_module.get_plant(pid).current_streak == 0
