"""Unit tests for core.drying_model.

Coverage goals (in priority order):
  1. The action decision: WATER / CHECK / None in every real-world branch.
  2. Edge cases around new plants, boundary days, and clamping.
  3. Effect of drying_coefficient (learning) on predictions.
  4. Each pure modifier + effective_drying_days composition.
  5. water_amount_oz lookup, clamping, and moisture scaling.

Ambiguities flagged during authoring (see module-level notes in conftest
and the comments beside the specific tests) — these describe current
behavior faithfully rather than asserting what "should" happen, so the
tests stay honest about the engine.
"""

from datetime import date, timedelta

import pytest

from core.drying_model import (
    WATER_OZ_BY_POT_INCHES,
    _light_modifier,
    _moisture_modifier,
    _pot_material_modifier,
    _pot_size_modifier,
    effective_drying_days,
    generate_action_for_plant,
    generate_actions_for_today,
    predicted_dry_date,
    should_emit_check,
    water_amount_oz,
)
from core.schema import ActionType, LightLevel, MoisturePreference, PotMaterial

# ---------------------------------------------------------------------------
# Individual modifiers
# ---------------------------------------------------------------------------


class TestModifiers:
    @pytest.mark.parametrize("inches,expected", [(3, -1), (5, -1), (6, 0), (8, 0), (12, 0)])
    def test_pot_size(self, make_plant, inches, expected):
        assert _pot_size_modifier(make_plant(pot_diameter_inches=inches)) == expected

    @pytest.mark.parametrize(
        "material,expected",
        [
            (PotMaterial.PLASTIC, 0),
            (PotMaterial.CERAMIC, 0),
            (PotMaterial.TERRACOTTA, -1),
        ],
    )
    def test_pot_material(self, make_plant, material, expected):
        assert _pot_material_modifier(make_plant(pot_material=material)) == expected

    @pytest.mark.parametrize(
        "light,expected",
        [
            (LightLevel.LOW, 0),
            (LightLevel.MEDIUM, 0),
            (LightLevel.BRIGHT, -1),
        ],
    )
    def test_light(self, make_plant, light, expected):
        assert _light_modifier(make_plant(light_level=light)) == expected

    @pytest.mark.parametrize(
        "pref,expected",
        [
            (MoisturePreference.MOIST_OFTEN, -1),
            (MoisturePreference.EVENLY_MOIST, 0),
            (MoisturePreference.DRY_BETWEEN, 1),
        ],
    )
    def test_moisture(self, make_plant, make_template, pref, expected):
        plant = make_plant(template=make_template(moisture_preference=pref))
        assert _moisture_modifier(plant) == expected

    def test_moisture_without_template_defaults_to_evenly_moist(self, make_plant):
        # Plant.get_moisture_preference() falls back to EVENLY_MOIST when no template.
        assert _moisture_modifier(make_plant(template=None)) == 0


# ---------------------------------------------------------------------------
# effective_drying_days
# ---------------------------------------------------------------------------


class TestEffectiveDryingDays:
    def test_default_plant_is_base(self, make_plant):
        # No template -> base 7, all modifiers 0, coef 1.0.
        assert effective_drying_days(make_plant()) == 7.0

    def test_modifiers_stack(self, make_plant, make_template):
        # Small pot (-1), terracotta (-1), bright (-1), moist_often (-1) = -4
        # base 7 - 4 = 3, coef 1.0 -> 3.0
        plant = make_plant(
            pot_diameter_inches=4,
            pot_material=PotMaterial.TERRACOTTA,
            light_level=LightLevel.BRIGHT,
            template=make_template(moisture_preference=MoisturePreference.MOIST_OFTEN),
        )
        assert effective_drying_days(plant) == 3.0

    def test_clamp_floor_is_two_days(self, make_plant, make_template):
        # Short-interval template (3 days) + all fast modifiers = -1, clamped to 2.
        plant = make_plant(
            pot_diameter_inches=4,
            pot_material=PotMaterial.TERRACOTTA,
            light_level=LightLevel.BRIGHT,
            template=make_template(
                default_drying_days=3,
                moisture_preference=MoisturePreference.MOIST_OFTEN,
            ),
        )
        assert effective_drying_days(plant) == 2.0

    def test_dry_between_extends_interval(self, make_plant, make_template):
        plant = make_plant(
            template=make_template(moisture_preference=MoisturePreference.DRY_BETWEEN),
        )
        # 7 base + 1 (dry_between) = 8
        assert effective_drying_days(plant) == 8.0

    @pytest.mark.parametrize(
        "coef,expected",
        [
            (1.0, 7.0),
            (1.5, 10.5),
            (0.5, 3.5),
            (2.0, 14.0),
        ],
    )
    def test_coefficient_multiplies_result(self, make_plant, coef, expected):
        # Learning behavior at the model level: whatever coefficient the
        # learner stores, predictions scale linearly.
        assert effective_drying_days(make_plant(drying_coefficient=coef)) == expected

    def test_clamp_applies_before_coefficient(self, make_plant, make_template):
        # Intent: clamp is on the *base+modifiers* value, not on the product.
        # 3-day template with -4 modifiers clamps to 2, then 2 * 0.5 = 1.0.
        # If the clamp were applied after, the result would be max(2, 3-4)*0.5 = 1.0
        # either way — but the spec says "base + modifiers, clamped, then *coef".
        plant = make_plant(
            pot_diameter_inches=4,
            pot_material=PotMaterial.TERRACOTTA,
            light_level=LightLevel.BRIGHT,
            template=make_template(
                default_drying_days=3,
                moisture_preference=MoisturePreference.MOIST_OFTEN,
            ),
            drying_coefficient=0.5,
        )
        assert effective_drying_days(plant) == 1.0


# ---------------------------------------------------------------------------
# predicted_dry_date
# ---------------------------------------------------------------------------


class TestPredictedDryDate:
    TODAY = date(2024, 6, 15)

    def test_uses_last_watered_when_present(self, make_plant):
        plant = make_plant(last_watered_date=date(2024, 6, 10))
        # 7 days from 2024-06-10
        assert predicted_dry_date(plant, self.TODAY) == date(2024, 6, 17)

    def test_falls_back_to_created_at(self, make_plant):
        plant = make_plant(last_watered_date=None, created_at=date(2024, 6, 10))
        assert predicted_dry_date(plant, self.TODAY) == date(2024, 6, 17)

    def test_last_watered_wins_over_created_at(self, make_plant):
        plant = make_plant(
            last_watered_date=date(2024, 6, 12),
            created_at=date(2024, 6, 1),
        )
        assert predicted_dry_date(plant, self.TODAY) == date(2024, 6, 19)

    def test_new_plant_with_neither_returns_none(self, make_plant):
        # Edge: no reference date at all.
        plant = make_plant(last_watered_date=None, created_at=None)
        assert predicted_dry_date(plant, self.TODAY) is None

    @pytest.mark.parametrize(
        "coef,expected_days_added",
        [
            (1.0, 7),  # exact
            (0.6, 4),  # 4.2 -> round -> 4
            (1.1, 8),  # 7.7 -> round -> 8
            (0.5, 4),  # 3.5 -> banker's rounding -> 4 (since 4 is even)
        ],
    )
    def test_rounds_fractional_days(self, make_plant, coef, expected_days_added):
        plant = make_plant(
            last_watered_date=self.TODAY,
            drying_coefficient=coef,
        )
        assert predicted_dry_date(plant, self.TODAY) == self.TODAY + timedelta(
            days=expected_days_added
        )


# ---------------------------------------------------------------------------
# water_amount_oz
# ---------------------------------------------------------------------------


class TestWaterAmountOz:
    def test_exact_key(self, make_plant):
        assert water_amount_oz(make_plant(pot_diameter_inches=8)) == 6

    def test_clamps_below_table(self, make_plant):
        # 2" isn't in the table; smallest key is 4" (2 oz).
        assert water_amount_oz(make_plant(pot_diameter_inches=2)) == 2

    def test_clamps_above_table(self, make_plant):
        # 30" clamps to the 24" row (22 oz).
        assert water_amount_oz(make_plant(pot_diameter_inches=30)) == 22

    def test_between_keys_picks_next_higher(self, make_plant):
        # Ambiguity note: function chooses the next *higher* key, not the
        # nearest. A 7" pot resolves to the 8" row (6 oz), not 6" (4 oz).
        # Conservative (waters a bit more) but worth knowing.
        assert water_amount_oz(make_plant(pot_diameter_inches=7)) == 6
        assert water_amount_oz(make_plant(pot_diameter_inches=11)) == 10  # maps to 12
        assert water_amount_oz(make_plant(pot_diameter_inches=13)) == 12  # maps to 14

    def test_dry_between_scales_down(self, make_plant, make_template):
        plant = make_plant(
            pot_diameter_inches=8,
            template=make_template(moisture_preference=MoisturePreference.DRY_BETWEEN),
        )
        assert water_amount_oz(plant) == int(6 * 0.8)  # 4

    def test_moist_often_scales_up(self, make_plant, make_template):
        plant = make_plant(
            pot_diameter_inches=8,
            template=make_template(moisture_preference=MoisturePreference.MOIST_OFTEN),
        )
        assert water_amount_oz(plant) == int(6 * 1.2)  # 7

    def test_evenly_moist_is_unchanged(self, make_plant, make_template):
        plant = make_plant(
            pot_diameter_inches=8,
            template=make_template(moisture_preference=MoisturePreference.EVENLY_MOIST),
        )
        assert water_amount_oz(plant) == 6

    def test_dry_between_floor_is_one_oz(self, make_plant, make_template):
        # 4" pot -> 2 oz; DRY_BETWEEN -> int(2 * 0.8) = 1 -> max(1, 1) = 1.
        plant = make_plant(
            pot_diameter_inches=4,
            template=make_template(moisture_preference=MoisturePreference.DRY_BETWEEN),
        )
        assert water_amount_oz(plant) == 1

    def test_lookup_table_is_sorted(self):
        # Sanity: the internal lookup relies on sorted keys for clamping.
        keys = list(WATER_OZ_BY_POT_INCHES.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# should_emit_check
# ---------------------------------------------------------------------------


class TestShouldEmitCheck:
    TODAY = date(2024, 6, 15)

    def test_new_plant_returns_true(self, make_plant):
        # Documented oddity: this is true, but generate_action_for_plant
        # always returns WATER for a new plant first, so this branch is
        # effectively dead code from the normal caller path. Still worth
        # pinning so future callers don't change it silently.
        plant = make_plant(last_watered_date=None, created_at=None)
        assert should_emit_check(plant, self.TODAY) is True

    def test_day_before_dry_with_fresh_coefficient(self, make_plant):
        # last_watered 6 days ago -> dry tomorrow, coef still 1.0 -> CHECK.
        plant = make_plant(
            last_watered_date=self.TODAY - timedelta(days=6),
            drying_coefficient=1.0,
        )
        assert should_emit_check(plant, self.TODAY) is True

    def test_day_before_dry_when_coefficient_has_learned(self, make_plant):
        # Once any learning has happened, suppress the CHECK nudge.
        plant = make_plant(
            last_watered_date=self.TODAY - timedelta(days=6),
            drying_coefficient=0.9,  # a single "dry" observation drops coef by 0.1
        )
        # 6 + round(7 * 0.9) = 6 + 6 = day-before only if round(7*0.9)=6... actually
        # 7 * 0.9 = 6.3 -> round(6.3) = 6 -> dry on TODAY - 6 + 6 = TODAY, not tomorrow.
        # Shift last_watered by one so dry is genuinely tomorrow:
        plant = make_plant(
            last_watered_date=self.TODAY - timedelta(days=5),
            drying_coefficient=0.9,
        )
        # 5 days ago + 6 (rounded) = tomorrow.
        assert predicted_dry_date(plant, self.TODAY) == self.TODAY + timedelta(days=1)
        assert should_emit_check(plant, self.TODAY) is False

    def test_on_or_after_dry_date(self, make_plant):
        # The CHECK only fires the day before; not on dry day, not after.
        plant = make_plant(last_watered_date=self.TODAY - timedelta(days=7))
        assert predicted_dry_date(plant, self.TODAY) == self.TODAY
        assert should_emit_check(plant, self.TODAY) is False

    def test_mid_interval(self, make_plant):
        plant = make_plant(last_watered_date=self.TODAY - timedelta(days=3))
        assert should_emit_check(plant, self.TODAY) is False


# ---------------------------------------------------------------------------
# generate_action_for_plant
# ---------------------------------------------------------------------------


class TestGenerateAction:
    TODAY = date(2024, 6, 15)

    def test_new_plant_emits_water_first_watering(self, make_plant):
        plant = make_plant(last_watered_date=None)
        action = generate_action_for_plant(plant, self.TODAY)
        assert action is not None
        assert action.action_type == ActionType.WATER
        assert "First watering" in action.note
        assert action.amount_oz == water_amount_oz(plant)
        assert action.date == self.TODAY

    def test_due_today_emits_water(self, make_plant):
        plant = make_plant(last_watered_date=self.TODAY - timedelta(days=7))
        action = generate_action_for_plant(plant, self.TODAY)
        assert action is not None
        assert action.action_type == ActionType.WATER
        assert "soil line" in action.note

    def test_overdue_emits_water(self, make_plant):
        plant = make_plant(last_watered_date=self.TODAY - timedelta(days=14))
        action = generate_action_for_plant(plant, self.TODAY)
        assert action is not None
        assert action.action_type == ActionType.WATER

    def test_day_before_dry_emits_check_when_unlearned(self, make_plant):
        plant = make_plant(
            last_watered_date=self.TODAY - timedelta(days=6),
            drying_coefficient=1.0,
        )
        action = generate_action_for_plant(plant, self.TODAY)
        assert action is not None
        assert action.action_type == ActionType.CHECK
        assert action.amount_oz is None  # CHECK has no recommended amount
        assert action.priority == 2

    def test_day_before_dry_after_learning_is_silent(self, make_plant):
        # Once we have any learning, skip the pre-emptive CHECK.
        plant = make_plant(
            last_watered_date=self.TODAY - timedelta(days=5),
            drying_coefficient=0.9,
        )
        # sanity: 5 + round(7 * 0.9=6.3 -> 6) = dry tomorrow
        assert predicted_dry_date(plant, self.TODAY) == self.TODAY + timedelta(days=1)
        assert generate_action_for_plant(plant, self.TODAY) is None

    def test_mid_interval_is_silent(self, make_plant):
        plant = make_plant(last_watered_date=self.TODAY - timedelta(days=3))
        assert generate_action_for_plant(plant, self.TODAY) is None


# ---------------------------------------------------------------------------
# generate_actions_for_today
# ---------------------------------------------------------------------------


class TestGenerateActionsForToday:
    TODAY = date(2024, 6, 15)

    def test_empty_input(self):
        assert generate_actions_for_today([], self.TODAY) == []

    def test_filters_silent_plants(self, make_plant):
        due = make_plant(last_watered_date=self.TODAY - timedelta(days=7))
        mid = make_plant(last_watered_date=self.TODAY - timedelta(days=3))
        fresh = make_plant(last_watered_date=self.TODAY - timedelta(days=1))

        actions = generate_actions_for_today([due, mid, fresh], self.TODAY)

        assert len(actions) == 1
        assert actions[0].plant_id == due.id
        assert actions[0].action_type == ActionType.WATER

    def test_preserves_input_order(self, make_plant):
        a = make_plant(last_watered_date=self.TODAY - timedelta(days=7))  # WATER
        b = make_plant(last_watered_date=None)  # WATER (new)
        c = make_plant(last_watered_date=self.TODAY - timedelta(days=6))  # CHECK

        actions = generate_actions_for_today([a, b, c], self.TODAY)

        assert [act.plant_id for act in actions] == [a.id, b.id, c.id]
        assert [act.action_type for act in actions] == [
            ActionType.WATER,
            ActionType.WATER,
            ActionType.CHECK,
        ]

    def test_defaults_today_to_date_today(self, make_plant, monkeypatch):
        # When called without `today`, the engine uses date.today(). Freeze it.
        frozen = date(2024, 6, 15)

        class _FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        monkeypatch.setattr("core.drying_model.date", _FrozenDate)
        plant = make_plant(last_watered_date=frozen - timedelta(days=7))
        actions = generate_actions_for_today([plant])
        assert len(actions) == 1 and actions[0].action_type == ActionType.WATER
