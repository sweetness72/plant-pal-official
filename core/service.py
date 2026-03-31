"""
Single place to get "today's actions" from DB + engine.
Used by the panel (HTML) and the API.
"""
from datetime import date
from typing import List, Tuple

from .db import ensure_seeded, get_plants
from .drying_model import generate_actions_for_today
from .schema import Action, Plant


def get_todays_actions(user_id: str = None) -> List[Tuple[Plant, Action]]:
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
