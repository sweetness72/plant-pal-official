"""
Indoor Drying Model v1.
Decides: for a given plant and date, do we emit WATER, CHECK, or nothing?

All hard-coded thresholds (modifiers, clamps, water-amount table,
learning rule, streak window, badge milestones) are documented in
``ASSUMPTIONS.md`` at the repo root — start with **§ Drying model
assumptions (at a glance)** for a scannable list, then the tables below
it for detail. If you change a number in this file, update
``ASSUMPTIONS.md`` in the same commit and expect the pinning tests in
``tests/test_known_issues.py`` / ``tests/test_scenarios.py`` to need
matching edits.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .schema import (
    Action,
    ActionType,
    CareTemplate,
    Confidence,
    LightLevel,
    MoisturePreference,
    Plant,
    PotMaterial,
    ReasonCode,
    Recommendation,
)

logger = logging.getLogger(__name__)


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

    A reference date in the future (clock skew, bad import, accidental edit)
    is clamped to ``today`` so the plant re-enters the normal drying cycle
    instead of being silently hidden forever. See known-issues B2.
    """
    ref = plant.last_watered_date or plant.created_at
    if ref is None:
        return None
    if ref > today:
        ref = today
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
            for _i, k in enumerate(keys):
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
    if today == dry - timedelta(days=1):  # noqa: SIM102 — nested-if preserves
        # Optional: only CHECK if drying_coefficient is still 1.0 (no learning
        # yet). Kept as a separate `if` so the rationale comment stays in
        # context; ruff's SIM102 would collapse it and lose that.
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


# ===========================================================================
# Recommendation v2, phase 1 — explanation + confidence wrapper.
#
# We do NOT change the underlying math in this phase. The action is still
# whatever ``generate_action_for_plant`` returns; we just add the metadata
# the UI needs to show WHY today's recommendation exists and HOW sure the
# engine is about it.
#
# Phase 2 will replace ``effective_drying_days``'s coefficient with an
# exp-weighted mean/variance over the observation history. When that
# lands, the only thing that changes here is ``_explain_factors``
# (adds a learned-offset line) and the confidence rule (starts using cv).
# ===========================================================================

_LOW_CONF_OBS_FLOOR = 3           # < N observations → always LOW
_HIGH_CONF_OBS_FLOOR = 5          # >= N observations required for HIGH
_STALE_MULTIPLIER = 2.0           # last_watered older than mean*this → stale
_LEARNED_COEFFICIENT_BAND = 0.05  # |c - 1.0| above this counts as "learned"

# Phase 2 estimator thresholds. CoV = stddev / mean of observed intervals;
# a tight plant (always watered at 7 days) has CoV near 0; a chaotic one
# (5 days, 20 days, 7 days…) easily crosses 0.5.
_HIGH_COV_THRESHOLD = 0.25
_MEDIUM_COV_THRESHOLD = 0.50
# Minimum ``observation_count`` to trust the EWMA for prediction. Below
# this we keep using template * modifiers * drying_coefficient.
_ESTIMATOR_MIN_OBSERVATIONS = 3
# A life event (repot / move / light_change / break) in the last N days
# caps confidence at MEDIUM regardless of how steady the historical
# stats look — the environment just changed on us.
_RECENT_EVENT_WINDOW_DAYS = 30
_LIFE_EVENT_KINDS = frozenset({"repot", "move", "light_change", "break"})


def recommend_for_plant(
    plant: Plant,
    history: Optional[List[Dict[str, Any]]] = None,
    today: Optional[date] = None,
    recent_events: Optional[List[Dict[str, Any]]] = None,
) -> Recommendation:
    """
    Wrap today's action with explanation metadata and bucketed confidence.

    ``history`` is a newest-first list of observation dicts as returned by
    ``core.db.get_observation_history`` — kept as plain dicts so this module
    stays dependency-free. Pass ``[]`` or ``None`` if you genuinely have no
    history; the function will fall back to "new plant" behavior and label
    confidence LOW.

    ``recent_events`` is an optional list of ``plant_event`` dicts as
    returned by ``core.db.get_recent_events``. If any life event (repot,
    move, light change, break) falls in the last ``_RECENT_EVENT_WINDOW_DAYS``,
    confidence is capped at MEDIUM — the plant's environment just
    changed so the historical stats shouldn't drive an overconfident
    prediction.

    Phase 2: when ``plant.observation_count >= _ESTIMATOR_MIN_OBSERVATIONS``
    and we have ``interval_mean_days``, the learned EWMA mean becomes the
    ``predicted_interval_days`` instead of the template * modifiers *
    coefficient formula. The ``action`` (WATER/CHECK) is still produced
    by ``generate_action_for_plant`` so behavior stays backwards-compatible
    for existing call sites.
    """
    today = today or date.today()
    history = history or []
    recent_events = recent_events or []

    action = generate_action_for_plant(plant, today)
    template_interval = effective_drying_days(plant)
    learned_interval = _learned_interval_days(plant)
    interval = learned_interval if learned_interval is not None else template_interval

    factors = _explain_factors(plant, history, learned_interval)
    confidence = _score_confidence(plant, history, today, interval, recent_events)
    reason = _reason_code(plant, action, today, history, interval)

    logger.debug(
        "recommendation plant_id=%s name=%r reason=%s confidence=%s interval_days=%.2f obs_n=%d",
        plant.id,
        plant.display_name,
        reason.value,
        confidence.value,
        float(interval),
        len(history),
    )
    return Recommendation(
        action=action,
        reason_code=reason,
        factors=factors,
        confidence=confidence,
        predicted_interval_days=float(interval),
        observations_used=len(history),
    )


def _learned_interval_days(plant: Plant) -> Optional[float]:
    """EWMA interval mean if we have enough samples to trust it, else None.

    Gate is ``observation_count >= _ESTIMATOR_MIN_OBSERVATIONS``. The
    threshold is deliberately conservative: three waterings is the
    minimum where an EWMA mean is meaningfully better than the prior, but
    we're still short of the ``_HIGH_CONF_OBS_FLOOR`` used for HIGH
    confidence. Between those two bars we trust the mean for prediction
    but refuse to say HIGH until it's been validated.
    """
    count = int(plant.observation_count or 0)
    if count < _ESTIMATOR_MIN_OBSERVATIONS:
        return None
    if plant.interval_mean_days is None:
        return None
    mean = float(plant.interval_mean_days)
    if mean <= 0:
        return None
    return mean


def _explain_factors(
    plant: Plant,
    history: List[Dict[str, Any]],
    learned_interval: Optional[float],
) -> List[str]:
    """Short human-readable bullets describing what shaped today's interval.

    These are the lines the UI shows under "Why does Plant Pal think
    this?". Copy stays cozy and plain — no raw coefficients, no jargon.
    Each factor is phrased as a signed offset so the reader can mentally
    add them up.

    When ``learned_interval`` is set, we include a line describing the
    EWMA mean and surface it as the anchor, then still list the
    template-modifier factors below so the user can see their plant's
    drift from the template's defaults.
    """
    base = plant.get_default_drying_days()
    factors: List[str] = []

    if learned_interval is not None:
        rounded = round(learned_interval, 1)
        factors.append(
            f"Your plant averages about {rounded:g} days between waterings"
        )

    factors.append(f"Base {base} days from {_template_name(plant)}")

    if plant.pot_diameter_inches < 6:
        factors.append("−1 day: small pot dries faster")
    if plant.pot_material == PotMaterial.TERRACOTTA:
        factors.append("−1 day: terracotta breathes")
    if plant.light_level == LightLevel.BRIGHT:
        factors.append("−1 day: bright light")

    pref = plant.get_moisture_preference()
    if pref == MoisturePreference.MOIST_OFTEN:
        factors.append("−1 day: likes consistent moisture")
    elif pref == MoisturePreference.DRY_BETWEEN:
        factors.append("+1 day: prefers to dry out between")

    # Soil-feeling learned offset — translate the coefficient into plain
    # language so users don't see "0.82" in the UI. Only surface it once
    # we've moved meaningfully off the prior. This channel is independent
    # of the interval estimator: the coefficient captures "you told me
    # the soil felt dry/wet", the estimator captures "you actually
    # watered every N days". Both can be informative at the same time.
    c = plant.drying_coefficient
    if abs(c - 1.0) > _LEARNED_COEFFICIENT_BAND:
        pct = int(round(abs(c - 1.0) * 100))
        if c < 1.0:
            factors.append(f"Learned: dries about {pct}% faster than template")
        else:
            factors.append(f"Learned: dries about {pct}% slower than template")

    n = len(history)
    if n == 0:
        factors.append("No history yet — still learning")
    elif n == 1:
        factors.append("Based on 1 watering logged")
    else:
        factors.append(f"Based on {n} waterings logged")

    return factors


def _template_name(plant: Plant) -> str:
    """Return a template display string for factor copy without dumping a UUID."""
    if plant.template and plant.template.name:
        return f"template “{plant.template.name}”"
    return "the default template"


def _score_confidence(
    plant: Plant,
    history: List[Dict[str, Any]],
    today: date,
    interval: float,
    recent_events: Optional[List[Dict[str, Any]]] = None,
) -> Confidence:
    """Bucketed confidence.

    Rules, in order:
      1. **Stale**: haven't logged anything in > 2× interval → LOW.
      2. **Sparse**: fewer than ``_LOW_CONF_OBS_FLOOR`` observations → LOW.
      3. **Recent life event** (repot/move/light_change/break in the
         last ``_RECENT_EVENT_WINDOW_DAYS``): cap at MEDIUM.
      4. **CoV-based** (preferred when plant has stored stats):
         - count ≥ 5 and CoV ≤ 0.25 → HIGH
         - count ≥ 3 and CoV ≤ 0.50 → MEDIUM
         - otherwise → LOW
      5. **Phase 1 fallback** (no stored stats — e.g. tests that build
         Plants manually with a history list):
         - count ≥ 5 → HIGH
         - soil-feeling coefficient has moved off the prior → MEDIUM
         - otherwise → LOW
    """
    recent_events = recent_events or []

    if plant.last_watered_date is not None:
        since_last = (today - plant.last_watered_date).days
        if interval > 0 and since_last > _STALE_MULTIPLIER * interval:
            return Confidence.LOW

    stored_count = int(plant.observation_count or 0)
    count = stored_count if stored_count > 0 else len(history)
    if count < _LOW_CONF_OBS_FLOOR:
        return Confidence.LOW

    has_recent_event = any(
        e.get("kind") in _LIFE_EVENT_KINDS
        and (today - e["at"]).days <= _RECENT_EVENT_WINDOW_DAYS
        for e in recent_events
    )

    mean = float(plant.interval_mean_days or 0.0)
    var = float(plant.interval_var_days or 0.0)
    have_stats = mean > 0

    if have_stats:
        cov = (var**0.5) / mean
        if has_recent_event:
            # Still in the post-event observation window — the stats may
            # be accurate but we don't want to over-promise.
            return Confidence.MEDIUM
        if count >= _HIGH_CONF_OBS_FLOOR and cov <= _HIGH_COV_THRESHOLD:
            return Confidence.HIGH
        if count >= _LOW_CONF_OBS_FLOOR and cov <= _MEDIUM_COV_THRESHOLD:
            return Confidence.MEDIUM
        return Confidence.LOW

    # Fallback: no stored stats. Preserve the phase-1 rule so tests that
    # construct Plants manually with a history list still pass.
    coef_moved = abs(plant.drying_coefficient - 1.0) > _LEARNED_COEFFICIENT_BAND
    if has_recent_event:
        return Confidence.MEDIUM
    if count >= _HIGH_CONF_OBS_FLOOR:
        return Confidence.HIGH
    if coef_moved:
        return Confidence.MEDIUM
    return Confidence.LOW


def _reason_code(
    plant: Plant,
    action: Optional[Action],
    today: date,
    history: List[Dict[str, Any]],
    interval: float,
) -> ReasonCode:
    """Pick a stable reason key for the UI to reword/localize."""
    if action is None:
        return ReasonCode.NOT_DUE

    if plant.last_watered_date is None:
        return ReasonCode.NEW_PLANT

    # Stale takes priority over DUE/OVERDUE — if we haven't heard from the
    # plant in way longer than the interval, the "overdue" label is
    # technically true but not useful. "I'm not sure — check the soil" is.
    if interval > 0:
        since_last = (today - plant.last_watered_date).days
        if since_last > _STALE_MULTIPLIER * interval:
            return ReasonCode.STALE_HISTORY

    if action.action_type == ActionType.CHECK:
        return ReasonCode.SOIL_CHECK_LOW_CONFIDENCE

    dry = predicted_dry_date(plant, today)
    if dry is not None and today > dry:
        return ReasonCode.OVERDUE
    return ReasonCode.DUE_TODAY
