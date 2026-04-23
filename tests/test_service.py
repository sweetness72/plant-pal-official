"""Tests for ``core.service`` — DB + engine glue used by the UI and API.

The service module is thin; these tests still matter because they catch
wiring mistakes (wrong history passed into ``recommend_for_plant``, or
``ensure_seeded`` / ``get_plants`` skew). They complement
``test_recommendation*.py`` which test the engine and persistence
directly.
"""

from __future__ import annotations

from datetime import date

from core import db as db_module
from core.drying_model import recommend_for_plant
from core.schema import ActionType, Plant
from core.service import get_plant_recommendation, get_todays_recommendations


def _add_minimal_plant() -> Plant:
    return db_module.add_plant(
        display_name="ServiceTest",
        room_name="Lab",
        pot_diameter_inches=8,
        pot_material="plastic",
        light_level="medium",
        template_id=None,
    )


class TestTodaysRecommendations:
    """`get_todays_recommendations` drives the home “Today” list with metadata."""

    def test_includes_unwatered_plant_with_water_action(self, tmp_db) -> None:
        plant = _add_minimal_plant()
        rows = get_todays_recommendations()
        match = next((r for p, r in rows if p.id == plant.id), None)
        assert match is not None, "new plant with no water should need a first action"
        assert match.action is not None
        assert match.action.action_type == ActionType.WATER


class TestGetPlantRecommendation:
    """`get_plant_recommendation` should match calling the engine with DB-backed inputs."""

    def test_matches_recommend_for_plant_with_same_history(self, tmp_db) -> None:
        plant = _add_minimal_plant()
        today = date(2025, 9, 1)
        from core.db import get_observation_history, get_recent_events

        direct = recommend_for_plant(
            plant,
            history=get_observation_history(str(plant.id)),
            today=today,
            recent_events=get_recent_events(str(plant.id)),
        )
        from_svc = get_plant_recommendation(plant, today=today)
        assert from_svc.action == direct.action
        assert from_svc.reason_code == direct.reason_code
        assert from_svc.confidence == direct.confidence
        assert from_svc.factors == direct.factors
        assert from_svc.predicted_interval_days == direct.predicted_interval_days


class TestAddRemove:
    """Minimal smoke on plant lifecycle through the public DB API."""

    def test_remove_plant_deletes_row(self, tmp_db) -> None:
        p = _add_minimal_plant()
        pid = str(p.id)
        assert db_module.get_plant(pid) is not None
        assert db_module.remove_plant(pid) is True
        assert db_module.get_plant(pid) is None
