"""
Single place to get "today's actions" and full Recommendations from DB + engine.
Used by the panel (HTML) and the API.
"""

from datetime import date

from .db import ensure_seeded, get_observation_history, get_plants, get_recent_events
from .drying_model import generate_actions_for_today, recommend_for_plant
from .schema import Action, Plant, Recommendation


def get_todays_actions(user_id: str = None) -> list[tuple[Plant, Action]]:
    """
    Load plants from DB, run the drying engine for today, return (plant, action) pairs.
    Seeds DB with templates and example plants if empty (first run).
    """
    from .db import DEFAULT_USER_ID, init_db

    init_db()
    ensure_seeded()
    uid = user_id or DEFAULT_USER_ID
    plants = get_plants(uid)
    today = date.today()
    actions = generate_actions_for_today(plants, today)
    plant_by_id = {p.id: p for p in plants}
    return [(plant_by_id[a.plant_id], a) for a in actions]


def get_todays_recommendations(
    user_id: str = None,
) -> list[tuple[Plant, Recommendation]]:
    """
    Full Recommendation per plant that has an action today.

    Shape mirrors ``get_todays_actions`` but carries the phase-2 metadata
    (confidence, factors, reason code, predicted_interval_days) so the
    UI can render a confidence chip + explanation without a second
    round-trip to the engine. Plants with no action today are omitted.
    """
    from .db import DEFAULT_USER_ID, init_db

    init_db()
    ensure_seeded()
    uid = user_id or DEFAULT_USER_ID
    plants = get_plants(uid)
    today = date.today()
    out: list[tuple[Plant, Recommendation]] = []
    for p in plants:
        history = get_observation_history(str(p.id))
        events = get_recent_events(str(p.id))
        rec = recommend_for_plant(p, history=history, today=today, recent_events=events)
        if rec.action is not None:
            out.append((p, rec))
    return out


def get_plant_recommendation(
    plant: Plant,
    today: date | None = None,
) -> Recommendation:
    """Full Recommendation for one plant. Used by the detail page."""
    history = get_observation_history(str(plant.id))
    events = get_recent_events(str(plant.id))
    return recommend_for_plant(plant, history=history, today=today, recent_events=events)
