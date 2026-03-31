"""
Indoor Drying Model v1.
Decides: for a given plant and date, do we emit WATER, CHECK, or nothing?
"""
from datetime import date, timedelta
from typing import Optional

from .schema import (
    Action,
    ActionType,
    CareTemplate,
    LightLevel,
    MoisturePreference,
    Plant,
    PotMaterial,
)


# Water amount by pot diameter (inches -> oz) for "soak until moist" heuristic
WATER_OZ_BY_POT_INCHES = {
    4: 2,
    5: 3,
    6: 4,
    8: 6,
    10: 8,
    12: 10,
    14: 12,
    16: 14,
    18: 16,
    20: 18,
    24: 22,
}


def _pot_size_modifier(plant: Plant) -> int:
    """Small pot dries faster -> water more often -> subtract a day from interval."""
    if plant.pot_diameter_inches < 6:
        return -1
    return 0


def _pot_material_modifier(plant: Plant) -> int:
    """Terracotta breathes -> dries faster."""
    if plant.pot_material == PotMaterial.TERRACOTTA:
        return -1
    return 0


def _light_modifier(plant: Plant) -> int:
    """Bright light -> more transpiration -> shorter interval."""
    if plant.light_level == LightLevel.BRIGHT:
        return -1
    return 0


def _moisture_modifier(plant: Plant) -> int:
    """Template preference: moist_often = shorter interval, dry_between = longer."""
    pref = plant.get_moisture_preference()
    if pref == MoisturePreference.MOIST_OFTEN:
        return -1
    if pref == MoisturePreference.DRY_BETWEEN:
        return 1
    return 0


def effective_drying_days(plant: Plant) -> float:
    """
    Compute effective days between waterings for this plant.
    Formula: base + modifiers, then multiply by learning coefficient.
    """
    base = plant.get_default_drying_days()
    modifiers = (
        _pot_size_modifier(plant)
        + _pot_material_modifier(plant)
        + _light_modifier(plant)
        + _moisture_modifier(plant)
    )
    adjusted = base + modifiers
    # Clamp so we never go below 2 days
    adjusted = max(2, adjusted)
    return adjusted * plant.drying_coefficient


def predicted_dry_date(plant: Plant, today: date) -> Optional[date]:
    """
    Date when this plant is predicted to need water.
    Uses last_watered_date or created_at; if neither, returns None (new plant).
    """
    ref = plant.last_watered_date or plant.created_at
    if ref is None:
        return None
    days = effective_drying_days(plant)
    return ref + timedelta(days=int(round(days)))


def water_amount_oz(plant: Plant) -> int:
    """Suggested water amount in oz from pot size; template can scale later."""
    d = plant.pot_diameter_inches
    # Nearest key or clamp
    if d in WATER_OZ_BY_POT_INCHES:
        oz = WATER_OZ_BY_POT_INCHES[d]
    else:
        keys = sorted(WATER_OZ_BY_POT_INCHES.keys())
        if d <= keys[0]:
            oz = WATER_OZ_BY_POT_INCHES[keys[0]]
        elif d >= keys[-1]:
            oz = WATER_OZ_BY_POT_INCHES[keys[-1]]
        else:
            for i, k in enumerate(keys):
                if k >= d:
                    oz = WATER_OZ_BY_POT_INCHES[k]
                    break
            else:
                oz = WATER_OZ_BY_POT_INCHES[keys[-1]]
    pref = plant.get_moisture_preference()
    if pref == MoisturePreference.DRY_BETWEEN:
        oz = max(1, int(oz * 0.8))
    elif pref == MoisturePreference.MOIST_OFTEN:
        oz = int(oz * 1.2)
    return oz


def should_emit_check(plant: Plant, today: date) -> bool:
    """
    Emit CHECK (e.g. "check soil") when we're one day before predicted dry
    and we want to reduce uncertainty. MVP: do it when we have no recent
    feedback (e.g. last_watered is old or never set).
    """
    dry = predicted_dry_date(plant, today)
    if dry is None:
        return True  # New plant -> one CHECK to start
    if today == dry - timedelta(days=1):
        # Optional: only CHECK if drying_coefficient is still 1.0 (no learning yet)
        if plant.drying_coefficient == 1.0:
            return True
    return False


def generate_action_for_plant(plant: Plant, today: date) -> Optional[Action]:
    """
    Core decision: does this plant get an action today?
    Returns one Action (WATER or CHECK) or None.
    """
    # New plant (never watered): show WATER today so the user can mark it done and start the timer.
    if plant.last_watered_date is None:
        return Action(
            plant_id=plant.id,
            date=today,
            action_type=ActionType.WATER,
            amount_oz=water_amount_oz(plant),
            note="First watering — start your timer",
            priority=0,
        )

    dry_date = predicted_dry_date(plant, today)
    if dry_date is None:
        return None

    if today >= dry_date:
        return Action(
            plant_id=plant.id,
            date=today,
            action_type=ActionType.WATER,
            amount_oz=water_amount_oz(plant),
            note=f"Water at soil line",
            priority=0,
        )

    if should_emit_check(plant, today):
        return Action(
            plant_id=plant.id,
            date=today,
            action_type=ActionType.CHECK,
            amount_oz=None,
            note="Check soil 2\" down",
            priority=2,
        )

    return None


def generate_actions_for_today(plants: list[Plant], today: Optional[date] = None) -> list[Action]:
    """
    Run the engine for a list of plants; return only actions that need to be taken.
    """
    today = today or date.today()
    actions: list[Action] = []
    for plant in plants:
        action = generate_action_for_plant(plant, today)
        if action is not None:
            actions.append(action)
    return actions
