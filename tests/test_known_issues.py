"""Known issues: confirmed bugs, missing validation, and model limitations.

This file is intentionally separate from ``test_drying_model.py``. That
file pins the happy-path contract of the engine; this file surfaces
behavior that is either wrong (bugs) or worth making visible before a
future change (limitations / undefended inputs).

Conventions used here:
  * ``@pytest.mark.xfail(strict=True, reason=...)`` — a CONFIRMED BUG.
    The test describes the *expected* behavior. It fails today, but
    will start passing when the bug is fixed, which will flip the mark
    to ``XPASS`` and fail the run (thanks to ``strict=True``). That way
    the xfail never silently rots.
  * Plain test with comment "pins current behavior, may change" —
    a MODEL LIMITATION or MISSING VALIDATION. Asserts what the code
    actually does today so a future change is visible in the diff.

See ``ASSUMPTIONS.md`` for the full list of hard-coded thresholds and
rules these tests rely on.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.routes.api import AddPlantBody, LogWateredBody
from core import db as db_module
from core.drying_model import (
    effective_drying_days,
    generate_action_for_plant,
    predicted_dry_date,
    water_amount_oz,
)
from core.schema import ActionType, CareTemplate, LightLevel, MoisturePreference, Plant, PotMaterial


# ===========================================================================
# Confirmed bugs — now FIXED (pinning contract tests)
# ===========================================================================


class TestStreakBugFixed:
    """B1 (fixed) — First watering of a freshly added plant starts a streak at 1.

    The first-watering signal in ``log_watered`` is now
    ``plant.last_watered_date is None`` rather than ``dry_date is None``.
    ``predicted_dry_date`` always falls back to ``created_at + days`` for a
    fresh plant, so the old guard was unreachable.
    """

    def test_first_watering_same_day_as_add_starts_streak_at_one(self, tmp_db):
        plant = db_module.add_plant(
            display_name="Basil",
            room_name="Kitchen",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
            template_id=None,
        )
        db_module.log_watered(str(plant.id), watered_date=date.today(), soil_feeling="ok")
        after = db_module.get_plant(str(plant.id))
        assert after is not None
        assert after.current_streak == 1
        assert after.longest_streak == 1

    def test_first_watering_is_always_on_time_regardless_of_offset(self, tmp_db):
        """The fix is not day-0-specific: watering some days after creating
        the plant still starts the streak at 1 (it's still the first one)."""
        plant = db_module.add_plant(
            display_name="Basil2",
            room_name="Kitchen",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
            template_id=None,
        )
        db_module.log_watered(
            str(plant.id),
            watered_date=date.today() + timedelta(days=3),
            soil_feeling="ok",
        )
        after = db_module.get_plant(str(plant.id))
        assert after is not None
        assert after.current_streak == 1


class TestFutureWateredDateFixed:
    """B2 (fixed) — A future ``last_watered_date`` no longer silences the plant.

    ``predicted_dry_date`` clamps ``ref`` to ``today`` when the reference is
    in the future, so the plant re-enters the normal drying cycle instead
    of disappearing from the panel until calendar time catches up.
    """

    TODAY = date(2024, 6, 15)

    def test_predicted_dry_date_is_clamped_to_today_plus_interval(self):
        """With last_watered_date 30 days in the future, the prediction
        is now ``today + effective_days`` (7 for a bare plant), not
        ``today + 37``."""
        plant = Plant(
            display_name="ClockSkew",
            last_watered_date=self.TODAY + timedelta(days=30),
        )
        assert predicted_dry_date(plant, self.TODAY) == self.TODAY + timedelta(days=7)

    def test_engine_recovers_once_calendar_time_passes_ref_plus_interval(self):
        """Ref is re-clamped on every call, so while the evaluation date is
        still before ``last_watered_date`` the plant looks 'freshly watered.'
        Once calendar time reaches ``last_watered_date + effective_days``
        the plant produces WATER normally — no permanent silence.
        """
        plant = Plant(
            display_name="ClockSkew",
            last_watered_date=self.TODAY + timedelta(days=30),
        )
        action = generate_action_for_plant(plant, self.TODAY + timedelta(days=37))
        assert action is not None
        assert action.action_type == ActionType.WATER

    def test_today_is_still_silent_because_not_overdue(self):
        """The clamp doesn't force a today-action; the plant simply re-enters
        the normal cycle. Pinned so a future over-eager fix is visible."""
        plant = Plant(
            display_name="ClockSkew",
            last_watered_date=self.TODAY + timedelta(days=30),
        )
        assert generate_action_for_plant(plant, self.TODAY) is None


# ===========================================================================
# Missing validation — pin current undefended behavior
# ===========================================================================


class TestInputValidation:
    """No validation currently exists for corrupt/extreme plant inputs.

    These tests pin CURRENT behavior so future defensive code is a
    deliberate change. Suggested validation layers (NOT implemented):

      * ``AddPlantBody`` (app/routes/api.py): Pydantic ``Field(ge=1, le=36)``
        on ``pot_diameter_inches``, ``Literal`` on ``pot_material`` /
        ``light_level``.
      * ``core.db`` writers: clamp / reject invalid coefficients and
        drying days on the way in.
      * ``core.drying_model``: defensive ``max(0.1, coefficient)`` etc.
        so corrupted data can't make predictions go negative.
    """

    TODAY = date(2024, 6, 15)

    def test_zero_coefficient_makes_plant_perpetually_due(self):
        # V1: effective_drying_days == 0 → dry_date == last_watered,
        # which is always <= today once last_watered is in the past.
        plant = Plant(
            drying_coefficient=0.0,
            last_watered_date=self.TODAY - timedelta(days=1),
        )
        assert effective_drying_days(plant) == 0.0
        action = generate_action_for_plant(plant, self.TODAY)
        assert action is not None and action.action_type == ActionType.WATER

    def test_negative_coefficient_makes_dry_date_in_the_past(self):
        # V1: -1.0 × 7 = -7 → predicted dry date 7 days BEFORE last_watered.
        # Today is always "overdue" → WATER.
        plant = Plant(
            drying_coefficient=-1.0,
            last_watered_date=self.TODAY,
        )
        assert effective_drying_days(plant) == -7.0
        action = generate_action_for_plant(plant, self.TODAY)
        assert action is not None and action.action_type == ActionType.WATER

    def test_template_base_of_zero_clamps_to_two_days(self):
        # V2: effective_drying_days clamp saves us, but base=0 stored in DB
        # is still a data-quality problem worth flagging at the writer.
        plant = Plant(template=CareTemplate(default_drying_days=0))
        assert effective_drying_days(plant) == 2.0

    def test_negative_template_base_clamps_to_two_days(self):
        plant = Plant(template=CareTemplate(default_drying_days=-5))
        assert effective_drying_days(plant) == 2.0

    def test_zero_pot_diameter_does_not_raise(self):
        # V3: Silently interpreted as "small pot" (< 6 → -1 modifier).
        # water_amount_oz clamps to the smallest table row.
        plant = Plant(pot_diameter_inches=0)
        assert water_amount_oz(plant) == 2  # smallest key (4") row

    def test_unknown_soil_feeling_is_ignored(self, tmp_db):
        # V4: API validates literal feelings; at ``log_watered`` anything
        # other than "wet" / "dry" / "ok" leaves the coefficient unchanged.
        plant = db_module.add_plant("X", "Y", 8, "plastic", "medium", None)
        db_module.log_watered(str(plant.id), soil_feeling="soaking_wet")
        after = db_module.get_plant(str(plant.id))
        assert after is not None
        assert after.drying_coefficient == pytest.approx(1.0)


# ===========================================================================
# Model limitations — pin current coarse-grained behavior
# ===========================================================================


class TestModelLimitations:
    """Pin current behavior for known-coarse rules so product changes are
    visible. Each test has a "current behavior, may change later" note.
    """

    def test_pot_size_has_single_breakpoint(self, make_plant):
        """L1: everything >= 6" gets modifier 0, regardless of size."""
        small = make_plant(pot_diameter_inches=4)
        medium = make_plant(pot_diameter_inches=8)
        huge = make_plant(pot_diameter_inches=24)
        # current behavior, may change later
        assert effective_drying_days(small) == 6.0   # base 7 - 1 (small)
        assert effective_drying_days(medium) == 7.0
        assert effective_drying_days(huge) == 7.0    # same as medium, despite pot size

    def test_light_only_bright_modifies(self, make_plant):
        """L2: LOW and MEDIUM are treated identically."""
        low = make_plant(light_level=LightLevel.LOW)
        medium = make_plant(light_level=LightLevel.MEDIUM)
        bright = make_plant(light_level=LightLevel.BRIGHT)
        # current behavior, may change later
        assert effective_drying_days(low) == effective_drying_days(medium) == 7.0
        assert effective_drying_days(bright) == 6.0

    def test_material_only_terracotta_modifies(self, make_plant):
        """L3: CERAMIC and PLASTIC are treated identically."""
        ceramic = make_plant(pot_material=PotMaterial.CERAMIC)
        plastic = make_plant(pot_material=PotMaterial.PLASTIC)
        terracotta = make_plant(pot_material=PotMaterial.TERRACOTTA)
        # current behavior, may change later
        assert effective_drying_days(ceramic) == effective_drying_days(plastic) == 7.0
        assert effective_drying_days(terracotta) == 6.0

    def test_plant_without_template_defaults_to_evenly_moist(self, make_plant):
        """L4: moisture preference can't be set independently of a template."""
        plant = make_plant(template=None)
        # current behavior: no moisture modifier at all
        assert effective_drying_days(plant) == 7.0

    def test_coefficient_cap_limits_extreme_plant_types(self, tmp_db):
        """L6: coefficient is clamped to [0.5, 1.5] regardless of how many
        consistent 'wet' or 'dry' observations we get. A true cactus with a
        7-day template tops out at ~11 days between waterings.
        """
        plant = db_module.add_plant("Cactus", "Sill", 8, "terracotta", "bright", None)
        pid = str(plant.id)
        for i in range(30):
            db_module.log_watered(
                pid,
                watered_date=date(2024, 1, 1) + timedelta(days=i),
                soil_feeling="wet",
            )
        after = db_module.get_plant(pid)
        assert after is not None
        # current behavior, may change later
        assert after.drying_coefficient == pytest.approx(1.5, abs=1e-6)

    def test_no_overdue_escalation(self, make_plant):
        """L7: an action 30 days overdue is indistinguishable from one due
        today — same action_type, same note, same priority.
        """
        due = make_plant(last_watered_date=date(2024, 6, 15) - timedelta(days=7))
        very_late = make_plant(last_watered_date=date(2024, 6, 15) - timedelta(days=37))
        today = date(2024, 6, 15)
        a1 = generate_action_for_plant(due, today)
        a2 = generate_action_for_plant(very_late, today)
        assert a1 is not None and a2 is not None
        # current behavior, may change later
        assert a1.action_type == a2.action_type
        assert a1.note == a2.note
        assert a1.priority == a2.priority


# ===========================================================================
# Design decisions worth documenting via tests
# ===========================================================================


class TestDocumentedBehavior:
    """D1-D5: not bugs, but surprising enough that a passing test acts as
    living documentation.
    """

    def test_water_amount_between_keys_rounds_up_not_nearest(self, make_plant):
        """D1: a 7" pot is handled as if it were 8", not 6"."""
        assert water_amount_oz(make_plant(pot_diameter_inches=7)) == 6  # 8" row
        assert water_amount_oz(make_plant(pot_diameter_inches=6)) == 4  # exact 6"

    def test_first_watering_note_is_exact_copy(self, make_plant):
        """D5: the landing page relies on this exact copy — don't silently
        rename it.
        """
        plant = make_plant(last_watered_date=None)
        action = generate_action_for_plant(plant, date(2024, 6, 15))
        assert action is not None
        assert action.note == "First watering — start your timer"
        assert action.action_type == ActionType.WATER
        assert action.priority == 0


# ===========================================================================
# Validation — Pydantic edge + DB writer clamps (NEW behavior, enforced)
# ===========================================================================


class TestAddPlantBodyValidation:
    """``AddPlantBody`` rejects corrupt inputs at the API boundary.

    Complements the ``TestInputValidation`` pins above (which show that
    the *core model* is still permissive if you bypass the API) by showing
    that the HTTP entry point is no longer permissive.
    """

    def _valid(self, **overrides):
        base = dict(display_name="x", room_name="y")
        base.update(overrides)
        return base

    def test_accepts_known_good_values(self):
        body = AddPlantBody(**self._valid(pot_diameter_inches=8, pot_material="terracotta", light_level="bright"))
        assert body.pot_diameter_inches == 8
        assert body.pot_material == "terracotta"
        assert body.light_level == "bright"

    def test_rejects_zero_pot_diameter(self):
        with pytest.raises(ValidationError):
            AddPlantBody(**self._valid(pot_diameter_inches=0))

    def test_rejects_negative_pot_diameter(self):
        with pytest.raises(ValidationError):
            AddPlantBody(**self._valid(pot_diameter_inches=-3))

    def test_rejects_oversize_pot_diameter(self):
        with pytest.raises(ValidationError):
            AddPlantBody(**self._valid(pot_diameter_inches=37))

    def test_rejects_unknown_pot_material(self):
        with pytest.raises(ValidationError):
            AddPlantBody(**self._valid(pot_material="wood"))

    def test_rejects_unknown_light_level(self):
        with pytest.raises(ValidationError):
            AddPlantBody(**self._valid(light_level="extreme"))


class TestLogWateredBodyValidation:
    """``LogWateredBody.soil_feeling`` is now a tight literal."""

    def test_accepts_known_feelings(self):
        for v in ("wet", "dry", "ok"):
            assert LogWateredBody(soil_feeling=v).soil_feeling == v

    def test_default_is_ok(self):
        assert LogWateredBody().soil_feeling == "ok"

    def test_default_no_watered_date(self):
        assert LogWateredBody().watered_date is None

    def test_rejects_unknown_feeling(self):
        with pytest.raises(ValidationError):
            LogWateredBody(soil_feeling="soaking_wet")


class TestWriterClamps:
    """``core.db`` helpers + writers pin numeric fields to documented bands
    before they hit disk. These complement — not replace — the read-time
    clamps in ``drying_model`` and the Pydantic edge above.
    """

    def test_clamp_coefficient_helper_bounds(self):
        assert db_module._clamp_coefficient(0.0) == 0.5
        assert db_module._clamp_coefficient(0.5) == 0.5
        assert db_module._clamp_coefficient(1.0) == 1.0
        assert db_module._clamp_coefficient(1.5) == 1.5
        assert db_module._clamp_coefficient(9.9) == 1.5

    def test_clamp_drying_days_helper_bounds(self):
        assert db_module._clamp_drying_days(-1) == 2
        assert db_module._clamp_drying_days(0) == 2
        assert db_module._clamp_drying_days(2) == 2
        assert db_module._clamp_drying_days(7) == 7
        assert db_module._clamp_drying_days(60) == 60
        assert db_module._clamp_drying_days(9999) == 60

    def test_log_watered_pins_corrupt_coefficient_to_band(self, tmp_db):
        """If a coefficient outside [0.5, 1.5] somehow lands in the DB
        (raw SQL, old data, future bug), the next ``log_watered`` clamps it.
        Without the unconditional clamp, a no-feedback watering would leave
        the bad value in place forever.
        """
        plant = db_module.add_plant("Corrupt", "Lab", 8, "plastic", "medium", None)
        pid = str(plant.id)

        # Poison the coefficient past the upper bound via raw SQL, mimicking
        # a bad import or a pre-clamp-era row.
        conn = sqlite3.connect(db_module.DB_PATH)
        try:
            conn.execute("UPDATE plant SET drying_coefficient = 2.0 WHERE id = ?", (pid,))
            conn.commit()
        finally:
            conn.close()

        # A plain log_watered with no soil_feeling used to leave 2.0 in place.
        db_module.log_watered(pid, watered_date=date.today())
        after = db_module.get_plant(pid)
        assert after is not None
        assert after.drying_coefficient == pytest.approx(1.5)

    def test_log_watered_pins_corrupt_coefficient_below_band(self, tmp_db):
        plant = db_module.add_plant("CorruptLow", "Lab", 8, "plastic", "medium", None)
        pid = str(plant.id)
        conn = sqlite3.connect(db_module.DB_PATH)
        try:
            conn.execute("UPDATE plant SET drying_coefficient = 0.1 WHERE id = ?", (pid,))
            conn.commit()
        finally:
            conn.close()
        db_module.log_watered(pid, watered_date=date.today())
        after = db_module.get_plant(pid)
        assert after is not None
        assert after.drying_coefficient == pytest.approx(0.5)
