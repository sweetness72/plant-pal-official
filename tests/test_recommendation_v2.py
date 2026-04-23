"""Phase 2 of recommendation v2.

What these tests protect:
  * ``log_watered`` maintains the per-plant EWMA ``interval_mean_days`` /
    ``interval_var_days`` / ``observation_count`` columns. Without this,
    the estimator has nothing to fall back on at boot.
  * ``recommend_for_plant`` uses the learned mean as the anchor interval
    once ``observation_count >= _ESTIMATOR_MIN_OBSERVATIONS``.
  * Confidence is derived from coefficient-of-variation when stats are
    available, not just from count.
  * ``plant_event`` rows written via ``record_event`` / fetched via
    ``get_recent_events`` cap confidence at MEDIUM when a recent life
    event implies the stats may no longer apply.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import db as db_module
from core.drying_model import recommend_for_plant
from core.schema import Confidence

# ---------------------------------------------------------------------------
# EWMA stats maintenance
# ---------------------------------------------------------------------------


class TestIntervalStatsPersistence:
    def test_first_watering_bumps_count_but_leaves_stats_null(self, tmp_db):
        plant = db_module.add_plant("Monty", "Desk", 8, "plastic", "medium", None)
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 1))

        fresh = db_module.get_plant(str(plant.id))
        assert fresh.observation_count == 1
        # No prior watering → no interval to integrate, mean/var stay NULL.
        assert fresh.interval_mean_days is None
        assert fresh.interval_var_days is None

    def test_second_watering_seeds_mean_with_interval(self, tmp_db):
        plant = db_module.add_plant("Monty", "Desk", 8, "plastic", "medium", None)
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 1))
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 8))

        fresh = db_module.get_plant(str(plant.id))
        assert fresh.observation_count == 2
        assert fresh.interval_mean_days == pytest.approx(7.0)
        # First real sample → variance is zero.
        assert fresh.interval_var_days == pytest.approx(0.0)

    def test_third_sample_moves_mean_via_ewma(self, tmp_db):
        plant = db_module.add_plant("Monty", "Desk", 8, "plastic", "medium", None)
        # Intervals: 7, 7, 13 days. After the seed (mean=7, var=0), the
        # 13-day gap should nudge the mean up but nowhere near 13.
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 1))
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 8))
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 15))
        db_module.log_watered(str(plant.id), watered_date=date(2025, 6, 28))

        fresh = db_module.get_plant(str(plant.id))
        assert fresh.observation_count == 4
        # Alpha=0.3: mean goes 7 → 7 → 7 + 0.3*6 = 8.8
        assert fresh.interval_mean_days == pytest.approx(8.8, abs=1e-6)
        assert fresh.interval_var_days > 0.0


# ---------------------------------------------------------------------------
# Estimator: learned mean drives predicted_interval_days once count ≥ 3
# ---------------------------------------------------------------------------


class TestLearnedInterval:
    def test_below_threshold_uses_template(self, make_plant, make_template):
        """With only 2 waterings recorded the estimator stays out of the
        way and the template's default drives the prediction."""
        tmpl = make_template(default_drying_days=7)
        plant = make_plant(
            template=tmpl,
            last_watered_date=date(2025, 6, 8),
            created_at=date(2025, 6, 1),
            interval_mean_days=5.0,
            interval_var_days=0.1,
            observation_count=2,
        )
        rec = recommend_for_plant(plant, history=[], today=date(2025, 6, 10))
        # base 7, no modifiers → 7-day template interval, not 5.
        assert rec.predicted_interval_days == pytest.approx(7.0)

    def test_at_threshold_uses_learned_mean(self, make_plant, make_template):
        tmpl = make_template(default_drying_days=7)
        plant = make_plant(
            template=tmpl,
            last_watered_date=date(2025, 6, 8),
            created_at=date(2025, 6, 1),
            interval_mean_days=10.0,
            interval_var_days=0.5,
            observation_count=3,
        )
        rec = recommend_for_plant(plant, history=[], today=date(2025, 6, 10))
        assert rec.predicted_interval_days == pytest.approx(10.0)

    def test_learned_mean_surfaces_in_factors(self, make_plant, make_template):
        tmpl = make_template(default_drying_days=7)
        plant = make_plant(
            template=tmpl,
            last_watered_date=date(2025, 6, 8),
            created_at=date(2025, 6, 1),
            interval_mean_days=10.0,
            interval_var_days=0.5,
            observation_count=3,
        )
        rec = recommend_for_plant(plant, history=[], today=date(2025, 6, 10))
        joined = "\n".join(rec.factors).lower()
        assert "averages" in joined
        assert "10" in joined  # mean value surfaced


# ---------------------------------------------------------------------------
# Confidence from coefficient-of-variation
# ---------------------------------------------------------------------------


class TestConfidenceFromCoV:
    def _plant_with_stats(self, make_plant, make_template, *, count, mean, var):
        tmpl = make_template(default_drying_days=7)
        return make_plant(
            template=tmpl,
            last_watered_date=date(2025, 7, 1),
            created_at=date(2025, 6, 1),
            interval_mean_days=mean,
            interval_var_days=var,
            observation_count=count,
        )

    def test_tight_intervals_many_samples_reach_high(self, make_plant, make_template):
        # CoV = sqrt(0.25) / 7 ≈ 0.071 → well under 0.25.
        plant = self._plant_with_stats(make_plant, make_template, count=6, mean=7.0, var=0.25)
        rec = recommend_for_plant(plant, history=[], today=date(2025, 7, 2))
        assert rec.confidence == Confidence.HIGH

    def test_noisy_intervals_stay_medium(self, make_plant, make_template):
        # CoV = sqrt(4) / 7 ≈ 0.286 → above HIGH threshold, below MEDIUM.
        plant = self._plant_with_stats(make_plant, make_template, count=6, mean=7.0, var=4.0)
        rec = recommend_for_plant(plant, history=[], today=date(2025, 7, 2))
        assert rec.confidence == Confidence.MEDIUM

    def test_chaotic_intervals_stay_low(self, make_plant, make_template):
        # CoV = sqrt(25) / 7 ≈ 0.71 → above MEDIUM threshold.
        plant = self._plant_with_stats(make_plant, make_template, count=8, mean=7.0, var=25.0)
        rec = recommend_for_plant(plant, history=[], today=date(2025, 7, 2))
        assert rec.confidence == Confidence.LOW


# ---------------------------------------------------------------------------
# plant_event: record + recent-window + confidence demotion
# ---------------------------------------------------------------------------


class TestPlantEvents:
    def test_record_and_fetch_recent_event(self, tmp_db):
        plant = db_module.add_plant("Monty", "Desk", 8, "plastic", "medium", None)
        db_module.record_event(
            str(plant.id),
            "repot",
            detail="new 8in terracotta",
            at=date(2025, 6, 15),
        )
        events = db_module.get_recent_events(
            str(plant.id),
            since_days=30,
            today=date(2025, 6, 20),
        )
        assert len(events) == 1
        assert events[0]["kind"] == "repot"
        assert events[0]["detail"] == "new 8in terracotta"
        assert events[0]["at"] == date(2025, 6, 15)

    def test_events_outside_window_are_excluded(self, tmp_db):
        plant = db_module.add_plant("Monty", "Desk", 8, "plastic", "medium", None)
        db_module.record_event(str(plant.id), "repot", at=date(2025, 5, 1))
        events = db_module.get_recent_events(
            str(plant.id),
            since_days=7,
            today=date(2025, 7, 1),
        )
        assert events == []

    def test_recent_repot_caps_confidence_at_medium(self, make_plant, make_template):
        """Even with high-quality stats, a repot in the last 30 days
        means the old intervals may no longer predict the new ones."""
        tmpl = make_template(default_drying_days=7)
        plant = make_plant(
            template=tmpl,
            last_watered_date=date(2025, 7, 1),
            created_at=date(2025, 6, 1),
            interval_mean_days=7.0,
            interval_var_days=0.25,  # CoV would normally → HIGH
            observation_count=6,
        )
        recent_events = [{"at": date(2025, 6, 25), "kind": "repot", "detail": None}]
        rec = recommend_for_plant(
            plant,
            history=[],
            today=date(2025, 7, 2),
            recent_events=recent_events,
        )
        assert rec.confidence == Confidence.MEDIUM

    def test_old_event_does_not_demote(self, make_plant, make_template):
        tmpl = make_template(default_drying_days=7)
        plant = make_plant(
            template=tmpl,
            last_watered_date=date(2025, 7, 1),
            created_at=date(2025, 6, 1),
            interval_mean_days=7.0,
            interval_var_days=0.25,
            observation_count=6,
        )
        # 45 days ago, outside the 30-day window.
        recent_events = [
            {"at": date(2025, 7, 1) - timedelta(days=45), "kind": "repot", "detail": None}
        ]
        rec = recommend_for_plant(
            plant,
            history=[],
            today=date(2025, 7, 2),
            recent_events=recent_events,
        )
        assert rec.confidence == Confidence.HIGH

    def test_non_life_event_kinds_do_not_demote(self, make_plant, make_template):
        """A ``note`` event is user-facing colour, not an environment change."""
        tmpl = make_template(default_drying_days=7)
        plant = make_plant(
            template=tmpl,
            last_watered_date=date(2025, 7, 1),
            created_at=date(2025, 6, 1),
            interval_mean_days=7.0,
            interval_var_days=0.25,
            observation_count=6,
        )
        recent_events = [{"at": date(2025, 7, 1), "kind": "note", "detail": "looks happy"}]
        rec = recommend_for_plant(
            plant,
            history=[],
            today=date(2025, 7, 2),
            recent_events=recent_events,
        )
        assert rec.confidence == Confidence.HIGH
