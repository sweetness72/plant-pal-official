"""Phase 1 of recommendation v2.

What these tests protect:
  * Every ``log_watered`` call persists an ``observation`` row with the
    correct elapsed-interval metadata. Without this, phase 2's estimator
    has nothing to learn from.
  * ``get_observation_history`` returns rows newest-first with parsed
    dates, so the engine can treat it as structured input.
  * ``recommend_for_plant`` wraps today's ``Action`` with the promised
    metadata (factors, confidence bucket, reason code) — without
    changing the action itself. Phase-1 is a strict superset of the
    existing engine's behavior.

When phase 2 replaces the coefficient with an exp-weighted estimator,
the confidence rules change but the shape of ``Recommendation`` must not
— this file pins that shape.
"""

from __future__ import annotations

from datetime import date

from core import db as db_module
from core.drying_model import recommend_for_plant
from core.schema import ActionType, Confidence, LightLevel, PotMaterial, ReasonCode

# ---------------------------------------------------------------------------
# Persistence: every watering is recorded
# ---------------------------------------------------------------------------


class TestObservationPersistence:
    def test_first_watering_creates_row_with_no_interval(self, tmp_db):
        """The first watering has no previous watered_date, so interval is NULL."""
        plant = db_module.add_plant(
            display_name="Monty",
            room_name="Desk",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
        )
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 1), soil_feeling="ok")

        hist = db_module.get_observation_history(str(plant.id))
        assert len(hist) == 1
        row = hist[0]
        assert row["observed_at"] == date(2025, 6, 1)
        assert row["soil_feeling"] == "ok"
        assert row["previous_watered_date"] is None
        assert row["interval_days"] is None
        assert row["was_on_time"] is True  # first waterings are always on-time

    def test_subsequent_watering_records_elapsed_interval(self, tmp_db):
        plant = db_module.add_plant(
            display_name="Monty",
            room_name="Desk",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
        )
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 1), soil_feeling="ok")
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 8), soil_feeling="ok")

        hist = db_module.get_observation_history(str(plant.id))
        assert len(hist) == 2
        newest, oldest = hist
        assert newest["observed_at"] == date(2025, 6, 8)
        assert newest["previous_watered_date"] == date(2025, 6, 1)
        assert newest["interval_days"] == 7.0
        assert oldest["observed_at"] == date(2025, 6, 1)

    def test_history_is_newest_first(self, tmp_db):
        plant = db_module.add_plant(
            display_name="Monty",
            room_name="Desk",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
        )
        for d in (date(2025, 6, 1), date(2025, 6, 8), date(2025, 6, 15)):
            db_module.log_watered(str(plant.id), watered_date=d, soil_feeling="ok")

        hist = db_module.get_observation_history(str(plant.id))
        assert [r["observed_at"] for r in hist] == [
            date(2025, 6, 15),
            date(2025, 6, 8),
            date(2025, 6, 1),
        ]


# ---------------------------------------------------------------------------
# Recommendation wrapper: pure-function shape and confidence buckets
# ---------------------------------------------------------------------------


class TestRecommendationShape:
    def test_new_plant_gets_water_action_and_low_confidence(self, make_plant):
        plant = make_plant(last_watered_date=None, created_at=date(2025, 6, 1))
        rec = recommend_for_plant(plant, history=[], today=date(2025, 6, 1))

        assert rec.action is not None
        assert rec.action.action_type == ActionType.WATER
        assert rec.reason_code == ReasonCode.NEW_PLANT
        assert rec.confidence == Confidence.LOW
        assert rec.observations_used == 0
        assert any("still learning" in f.lower() or "no history" in f.lower() for f in rec.factors)

    def test_factors_include_context_modifiers(self, make_plant):
        """Terracotta + bright + small pot should each appear as a −1 day factor."""
        plant = make_plant(
            pot_diameter_inches=4,
            pot_material=PotMaterial.TERRACOTTA,
            light_level=LightLevel.BRIGHT,
            last_watered_date=date(2025, 6, 1),
            created_at=date(2025, 6, 1),
        )
        rec = recommend_for_plant(plant, history=[], today=date(2025, 6, 2))
        joined = "\n".join(rec.factors).lower()
        assert "small pot" in joined
        assert "terracotta" in joined
        assert "bright" in joined

    def test_learned_coefficient_translated_to_plain_english(self, make_plant):
        plant = make_plant(
            last_watered_date=date(2025, 6, 1),
            created_at=date(2025, 6, 1),
            drying_coefficient=0.8,  # learned: dries faster
        )
        rec = recommend_for_plant(plant, history=[], today=date(2025, 6, 2))
        joined = "\n".join(rec.factors).lower()
        assert "20% faster" in joined

    def test_sparse_history_stays_low_even_with_observations(self, make_plant):
        """<3 observations always reads as LOW, regardless of coefficient."""
        plant = make_plant(
            last_watered_date=date(2025, 6, 8),
            created_at=date(2025, 6, 1),
            drying_coefficient=0.8,
        )
        history = [
            {
                "observed_at": date(2025, 6, 8),
                "soil_feeling": "dry",
                "previous_watered_date": date(2025, 6, 1),
                "interval_days": 7.0,
                "was_on_time": True,
                "action_taken": "water",
            },
        ]
        rec = recommend_for_plant(plant, history=history, today=date(2025, 6, 9))
        assert rec.confidence == Confidence.LOW
        assert rec.observations_used == 1

    def test_enough_history_with_learning_reaches_high_confidence(self, make_plant):
        plant = make_plant(
            last_watered_date=date(2025, 7, 1),
            created_at=date(2025, 6, 1),
            drying_coefficient=0.8,
        )
        history = [
            {
                "observed_at": date(2025, 7, 1),
                "soil_feeling": "ok",
                "previous_watered_date": date(2025, 6, 25),
                "interval_days": 6.0,
                "was_on_time": True,
                "action_taken": "water",
            },
        ] * 6  # 6 observations; content is irrelevant for phase 1 confidence rules
        rec = recommend_for_plant(plant, history=history, today=date(2025, 7, 2))
        assert rec.confidence == Confidence.HIGH

    def test_stale_history_demotes_confidence_and_reason(self, make_plant):
        """If the plant hasn't been watered in 2× its interval, confidence
        drops back to LOW with a STALE_HISTORY reason code — even if the
        engine would otherwise scream OVERDUE."""
        plant = make_plant(
            last_watered_date=date(2025, 5, 1),  # ~60 days ago vs ~7-day interval
            created_at=date(2025, 4, 1),
        )
        rec = recommend_for_plant(plant, history=[], today=date(2025, 7, 1))
        assert rec.confidence == Confidence.LOW
        assert rec.reason_code == ReasonCode.STALE_HISTORY

    def test_recommendation_does_not_change_the_action(self, make_plant):
        """Phase 1 contract: ``Recommendation.action`` is exactly what
        ``generate_action_for_plant`` would have returned. If this ever
        breaks, it means phase 1 silently started changing engine output."""
        from core.drying_model import generate_action_for_plant

        plant = make_plant(
            last_watered_date=date(2025, 6, 1),
            created_at=date(2025, 6, 1),
        )
        today = date(2025, 6, 20)  # well past due
        bare = generate_action_for_plant(plant, today)
        rec = recommend_for_plant(plant, history=[], today=today)

        # Dataclass equality would also compare identity of the plant_id
        # UUIDs — which are equal because they're the same plant — so this
        # is safe.
        assert rec.action == bare


# ---------------------------------------------------------------------------
# End-to-end: recommendation reads from the real history loader
# ---------------------------------------------------------------------------


class TestRecommendationEndToEnd:
    def test_recommendation_after_real_watering_sequence(self, tmp_db):
        plant = db_module.add_plant(
            display_name="Monty",
            room_name="Desk",
            pot_diameter_inches=8,
            pot_material="plastic",
            light_level="medium",
        )
        for d in (date(2025, 6, 1), date(2025, 6, 8), date(2025, 6, 15)):
            db_module.log_watered(str(plant.id), watered_date=d, soil_feeling="ok")

        fresh = db_module.get_plant(str(plant.id))
        history = db_module.get_observation_history(str(plant.id))
        rec = recommend_for_plant(fresh, history=history, today=date(2025, 6, 22))

        assert rec.observations_used == 3
        assert rec.predicted_interval_days > 0
        assert rec.reason_code in (
            ReasonCode.DUE_TODAY,
            ReasonCode.OVERDUE,
            ReasonCode.NOT_DUE,
            ReasonCode.SOIL_CHECK_LOW_CONFIDENCE,
        )
