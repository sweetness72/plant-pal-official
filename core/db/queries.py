"""
CRUD + learning logic for plants, templates, and observations.

This is the "what do we do with the data" layer. Schema + migrations live
in sibling modules; everything here takes a connection from ``_get_conn``
and returns domain dataclasses (``Plant``, ``CareTemplate``) so callers
never see raw rows.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import date, timedelta
from uuid import UUID

from ..schema import (
    CareTemplate,
    LightLevel,
    MoisturePreference,
    Plant,
    PotMaterial,
)
from .connection import DEFAULT_USER_ID, _clamp_coefficient, _get_conn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Row mapping helpers
#
# sqlite3.Row gotchas — read once and remember:
#   * __contains__ iterates VALUES, not keys. Use `k in row.keys()` for
#     existence checks. (SIM118 auto-fix breaks this; the lint rule is
#     ignored project-wide in pyproject.toml for exactly this reason.)
#   * There is no .get() method.
# ---------------------------------------------------------------------------


def _str_to_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def _parse_badges(s: str | None) -> list[int]:
    if not s or not s.strip():
        return []
    return [int(x.strip()) for x in s.split(",") if x.strip().isdigit()]


def _row_opt_str(row: sqlite3.Row, key: str) -> str | None:
    """Return a stripped string value, or None if the column is missing or empty."""
    if key not in row.keys():
        return None
    v = row[key]
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return str(v).strip()


def _plant_from_row(row: sqlite3.Row, template: CareTemplate | None) -> Plant:
    keys = row.keys()
    interval_mean = row["interval_mean_days"] if "interval_mean_days" in keys else None
    interval_var = row["interval_var_days"] if "interval_var_days" in keys else None
    obs_count = (
        int(row["observation_count"] or 0) if "observation_count" in keys else 0
    )
    return Plant(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        template=template,
        display_name=row["display_name"],
        room_name=row["room_name"],
        pot_diameter_inches=row["pot_diameter_inches"],
        pot_material=PotMaterial(row["pot_material"]),
        light_level=LightLevel(row["light_level"]),
        last_watered_date=_str_to_date(row["last_watered_date"]),
        drying_coefficient=row["drying_coefficient"],
        created_at=_str_to_date(row["created_at"]),
        low_effort_mode=bool(row["low_effort_mode"]),
        current_streak=row["current_streak"] if "current_streak" in keys else 0,
        longest_streak=row["longest_streak"] if "longest_streak" in keys else 0,
        badges_earned=(
            _parse_badges(row["badges_earned"])
            if "badges_earned" in keys and row["badges_earned"]
            else []
        ),
        category=_row_opt_str(row, "category"),
        visual_type=_row_opt_str(row, "visual_type"),
        image_override=_row_opt_str(row, "image_override"),
        interval_mean_days=(
            float(interval_mean) if interval_mean is not None else None
        ),
        interval_var_days=(
            float(interval_var) if interval_var is not None else None
        ),
        observation_count=obs_count,
        position_note=_row_opt_str(row, "position_note"),
    )


def _template_from_row(r: sqlite3.Row) -> CareTemplate:
    def _opt(key: str, default: str = "") -> str:
        return r[key] if key in r.keys() else default

    return CareTemplate(
        id=UUID(r["id"]),
        name=r["name"],
        slug=r["slug"],
        default_drying_days=r["default_drying_days"],
        moisture_preference=MoisturePreference(r["moisture_preference"]),
        icon_id=r["icon_id"],
        watering_frequency_display=_opt("watering_frequency_display"),
        light_display=_opt("light_display"),
        description=_opt("description"),
        environment=_opt("environment", "indoor"),
        category=_opt("category"),
        growing_instructions=_opt("growing_instructions"),
        visual_type=(
            r["visual_type"]
            if "visual_type" in r.keys() and r["visual_type"]
            else ""
        ),
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def get_templates(environment: str | None = None) -> list[CareTemplate]:
    """Load care templates, optionally filtered by environment ('indoor' | 'outdoor')."""
    conn = _get_conn()
    try:
        if environment and environment in ("indoor", "outdoor"):
            rows = conn.execute(
                "SELECT * FROM care_template WHERE environment = ? ORDER BY name",
                (environment,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM care_template ORDER BY environment, name"
            ).fetchall()
        return [_template_from_row(r) for r in rows]
    finally:
        conn.close()


def search_templates(
    query: str, limit: int = 25, environment: str | None = None
) -> list[CareTemplate]:
    """
    Search templates by name, slug, category, description, or growing instructions.
    Parameterized only (no SQL injection). Optional environment filter.
    """
    conn = _get_conn()
    try:
        if not query or not query.strip():
            if environment and environment in ("indoor", "outdoor"):
                rows = conn.execute(
                    "SELECT * FROM care_template WHERE environment = ? ORDER BY name LIMIT ?",
                    (environment, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM care_template ORDER BY name LIMIT ?",
                    (limit,),
                ).fetchall()
            return [_template_from_row(r) for r in rows]

        pattern = f"%{query.strip()}%"
        if environment and environment in ("indoor", "outdoor"):
            rows = conn.execute(
                """SELECT * FROM care_template WHERE environment = ? AND (
                    name LIKE ? OR slug LIKE ? OR category LIKE ?
                    OR description LIKE ? OR growing_instructions LIKE ?
                ) ORDER BY name LIMIT ?""",
                (environment, pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM care_template WHERE
                    name LIKE ? OR slug LIKE ? OR category LIKE ?
                    OR description LIKE ? OR growing_instructions LIKE ?
                ORDER BY name LIMIT ?""",
                (pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        return [_template_from_row(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Plants
# ---------------------------------------------------------------------------


def get_plant(plant_id: str, user_id: str = DEFAULT_USER_ID) -> Plant | None:
    """Load one plant by id, or None if not found / not owned by user."""
    conn = _get_conn()
    try:
        templates = {str(t.id): t for t in get_templates()}
        row = conn.execute(
            "SELECT * FROM plant WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        ).fetchone()
        if not row:
            return None
        tid = row["template_id"]
        template = templates.get(tid) if tid else None
        return _plant_from_row(row, template)
    finally:
        conn.close()


def get_plants(user_id: str = DEFAULT_USER_ID) -> list[Plant]:
    """Load all plants for a user, with templates joined."""
    conn = _get_conn()
    try:
        templates = {str(t.id): t for t in get_templates()}
        rows = conn.execute(
            "SELECT * FROM plant WHERE user_id = ? ORDER BY room_name, display_name",
            (user_id,),
        ).fetchall()
        plants: list[Plant] = []
        for r in rows:
            tid = r["template_id"]
            template = templates.get(tid) if tid else None
            plants.append(_plant_from_row(r, template))
        return plants
    finally:
        conn.close()


def add_plant(
    display_name: str,
    room_name: str,
    pot_diameter_inches: int = 8,
    pot_material: str = "plastic",
    light_level: str = "medium",
    template_id: str | None = None,
    user_id: str = DEFAULT_USER_ID,
    image_override: str | None = None,
    position_note: str | None = None,
) -> Plant:
    """Insert a new plant (not yet watered — last_watered_date stays NULL).

    ``image_override`` is a site path (``/uploads/...``) or absolute URL.
    When unset the UI falls back to the template/category artwork.
    """
    conn = _get_conn()
    try:
        plant_id = str(uuid.uuid4())
        today_str = date.today().isoformat()

        # Inherit visual_type + category from the template so the
        # image-resolution layer can fall back without a second lookup.
        plant_category: str | None = None
        plant_visual: str | None = None
        if template_id:
            for t in get_templates():
                if str(t.id) == template_id:
                    if getattr(t, "environment", "") in ("indoor", "outdoor"):
                        plant_category = t.environment
                    vt = (getattr(t, "visual_type", None) or "").strip()
                    plant_visual = vt or None
                    break

        pos = (position_note or "").strip() or None
        conn.execute(
            """INSERT INTO plant (
                id, user_id, template_id, display_name, room_name,
                pot_diameter_inches, pot_material, light_level,
                last_watered_date, drying_coefficient, created_at, low_effort_mode,
                current_streak, longest_streak, badges_earned,
                category, visual_type, image_override, position_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, 0, 0, 0, '', ?, ?, ?, ?)""",
            (
                plant_id,
                user_id,
                template_id,
                display_name,
                room_name,
                pot_diameter_inches,
                pot_material,
                light_level,
                None,
                today_str,
                plant_category,
                plant_visual,
                image_override,
                pos,
            ),
        )
        conn.commit()
        plants = get_plants(user_id)
        p = next(pl for pl in plants if str(pl.id) == plant_id)
        logger.info(
            "plant: added id=%s name=%r room=%r",
            plant_id,
            display_name,
            room_name,
        )
        return p
    finally:
        conn.close()


def update_plant(
    plant_id: str,
    *,
    display_name: str,
    room_name: str,
    position_note: str | None,
    template_id: str | None,
    light_level: str,
    pot_diameter_inches: int,
    pot_material: str,
    user_id: str = DEFAULT_USER_ID,
) -> Plant | None:
    """Update identity + environment fields. Returns the plant or None if missing."""
    pos = (position_note or "").strip() or None
    plant_category: str | None = None
    plant_visual: str | None = None
    if template_id:
        for t in get_templates():
            if str(t.id) == template_id:
                if getattr(t, "environment", "") in ("indoor", "outdoor"):
                    plant_category = t.environment
                vt = (getattr(t, "visual_type", None) or "").strip()
                plant_visual = vt or None
                break

    conn = _get_conn()
    try:
        cur = conn.execute(
            """UPDATE plant SET
                display_name = ?,
                room_name = ?,
                position_note = ?,
                template_id = ?,
                light_level = ?,
                pot_diameter_inches = ?,
                pot_material = ?,
                category = ?,
                visual_type = ?
            WHERE id = ? AND user_id = ?""",
            (
                display_name,
                room_name,
                pos,
                template_id,
                light_level,
                pot_diameter_inches,
                pot_material,
                plant_category,
                plant_visual,
                plant_id,
                user_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return get_plant(plant_id, user_id)
    finally:
        conn.close()


def remove_plant(plant_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Remove a plant and its observations. Returns True if a row was deleted."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM observation WHERE plant_id = ?", (plant_id,))
        cur = conn.execute(
            "DELETE FROM plant WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        )
        conn.commit()
        ok = cur.rowcount > 0
        if ok:
            logger.info("plant: removed id=%s", plant_id)
        return ok
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Watering + learning
# ---------------------------------------------------------------------------


# Streak badges: only at these milestones (increments).
BADGE_MILESTONES = [3, 5, 10, 25, 50, 100, 250, 300, 500]


# Recommendation v2 EWMA smoothing factor. 0.3 is a common textbook
# choice for fast-adapting online estimators; higher values chase recent
# samples more aggressively at the cost of noise.
_INTERVAL_EWMA_ALPHA = 0.3

# Soil-feedback steps are damped until a few waterings exist so early taps
# do not yank the coefficient. Mirrors the <3 ``observation_count`` idea in
# ASSUMPTIONS / product spec.
_EARLY_OBS_LEARNING_FLOOR = 3


def _soil_feedback_step_scale(plant: Plant) -> float:
    """0.5 when ``observation_count`` < 3 (before the current log); else 1.0."""
    return 0.5 if (plant.observation_count or 0) < _EARLY_OBS_LEARNING_FLOOR else 1.0


def _update_interval_stats(
    prior_mean: float | None,
    prior_var: float | None,
    new_interval_days: float,
) -> tuple[float, float]:
    """Fold one new interval sample into the running EWMA mean + variance.

    Returns ``(mean, var)``. The variance here is an EWMA estimate, not
    the unbiased Welford variance — it's cheap to maintain online and
    good enough for the coefficient-of-variation confidence rule.

    First sample (``prior_mean is None``) seeds the estimator with
    ``mean=x`` and ``var=0``. Subsequent samples move the mean by
    ``alpha * (x - mean)`` and the variance by
    ``(1-alpha) * (var + alpha * delta**2)`` — straight out of the
    incremental EWMV derivation.
    """
    if prior_mean is None:
        return float(new_interval_days), 0.0
    alpha = _INTERVAL_EWMA_ALPHA
    delta = new_interval_days - prior_mean
    new_mean = prior_mean + alpha * delta
    new_var = (1.0 - alpha) * ((prior_var or 0.0) + alpha * delta * delta)
    return float(new_mean), float(new_var)


def log_watered(
    plant_id: str,
    watered_date: date | None = None,
    soil_feeling: str | None = None,
) -> None:
    """
    Record a watering event.

    Side effects:
      * Moves the drying coefficient toward a new target based on
        ``soil_feeling`` (±0.1 / ±0.05 when ``observation_count`` ≥ 3,
        half those steps while count is still below 3 — see
        ``_soil_feedback_step_scale``), bounded by ``_clamp_coefficient``.
      * Updates the watering streak + badges (on-time = dry date ±1 day).
      * Writes an ``observation`` row with the elapsed interval and
        on-time flag so the recommendation engine has real history to
        learn from.
    """
    from ..drying_model import predicted_dry_date

    watered_date = watered_date or date.today()
    plant = get_plant(plant_id)
    if not plant:
        return

    conn = _get_conn()
    try:
        # --- 1. Learning-rule coefficient update -------------------------
        coef = plant.drying_coefficient
        scale = _soil_feedback_step_scale(plant)
        if soil_feeling == "wet":
            coef = min(1.5, coef + 0.1 * scale)
        elif soil_feeling == "dry":
            coef = max(0.5, coef - 0.1 * scale)
        elif soil_feeling == "ok":
            step = 0.05 * scale
            if coef < 1.0:
                coef = min(1.0, coef + step)
            elif coef > 1.0:
                coef = max(1.0, coef - step)

        # --- 2. Streak + on-time flag -----------------------------------
        # First watering: ONLY ``last_watered_date is None`` (never use
        # ``predicted_dry_date`` here). A new plant has ``created_at`` but
        # no prior watering — ``predicted_dry_date`` would still return a
        # date (from created_at + interval), so the on-time window would
        # wrongly give streak 0 for a same-day first water. See B1.
        is_first_watering = plant.last_watered_date is None
        if is_first_watering:
            on_time = True
            new_streak = 1
        else:
            dry_date = predicted_dry_date(plant, watered_date)
            on_time = (
                dry_date - timedelta(days=1)
                <= watered_date
                <= dry_date + timedelta(days=1)
            )
            new_streak = (plant.current_streak + 1) if on_time else 0

        coef = _clamp_coefficient(coef)

        new_longest = max(plant.longest_streak, new_streak)
        badges = list(plant.badges_earned)
        for m in BADGE_MILESTONES:
            if new_streak >= m and m not in badges:
                badges.append(m)
        badges.sort()
        badges_str = ",".join(str(b) for b in badges)

        # --- 3. Observation row -----------------------------------------
        prev_str = (
            plant.last_watered_date.isoformat() if plant.last_watered_date else None
        )
        interval_days: float | None = None
        if plant.last_watered_date is not None:
            interval_days = float((watered_date - plant.last_watered_date).days)
        conn.execute(
            """INSERT INTO observation
                 (id, plant_id, observed_at, soil_feeling, action_taken,
                  previous_watered_date, interval_days, was_on_time)
               VALUES (?, ?, ?, ?, 'water', ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                plant_id,
                watered_date.isoformat(),
                soil_feeling,
                prev_str,
                interval_days,
                1 if on_time else 0,
            ),
        )

        # --- 4. Recommendation v2: running interval stats ---------------
        # ``observation_count`` counts waterings (every log_watered bumps
        # it). ``interval_mean_days`` / ``interval_var_days`` only update
        # when we have an actual interval sample, i.e. not the first
        # watering — so the first watering leaves them NULL.
        new_count = (plant.observation_count or 0) + 1
        new_mean = plant.interval_mean_days
        new_var = plant.interval_var_days
        if interval_days is not None:
            new_mean, new_var = _update_interval_stats(
                plant.interval_mean_days,
                plant.interval_var_days,
                interval_days,
            )

        # --- 5. Update plant row ----------------------------------------
        conn.execute(
            """UPDATE plant
                  SET last_watered_date = ?,
                      drying_coefficient = ?,
                      current_streak = ?,
                      longest_streak = ?,
                      badges_earned = ?,
                      interval_mean_days = ?,
                      interval_var_days = ?,
                      observation_count = ?
                WHERE id = ?""",
            (
                watered_date.isoformat(),
                coef,
                new_streak,
                new_longest,
                badges_str,
                new_mean,
                new_var,
                new_count,
                plant_id,
            ),
        )
        conn.commit()
        logger.info(
            "plant: watered id=%s name=%r date=%s soil=%r streak=%d",
            plant_id,
            plant.display_name,
            watered_date.isoformat(),
            soil_feeling,
            new_streak,
        )
    finally:
        conn.close()


def get_observation_history(plant_id: str, limit: int = 50) -> list[dict]:
    """Load recent watering observations for a plant, newest first.

    Returned rows are plain dicts so the drying model (which never
    imports ``core.db``) can consume them. Only ``action_taken='water'``
    rows are returned — CHECK / skip events may exist but are ignored by
    the current estimator.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT observed_at, soil_feeling, action_taken,
                      previous_watered_date, interval_days, was_on_time
                 FROM observation
                WHERE plant_id = ? AND action_taken = 'water'
                ORDER BY observed_at DESC
                LIMIT ?""",
            (plant_id, int(limit)),
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "observed_at": date.fromisoformat(r["observed_at"]),
                    "soil_feeling": r["soil_feeling"],
                    "action_taken": r["action_taken"],
                    "previous_watered_date": (
                        date.fromisoformat(r["previous_watered_date"])
                        if r["previous_watered_date"]
                        else None
                    ),
                    "interval_days": r["interval_days"],
                    "was_on_time": (
                        None if r["was_on_time"] is None else bool(r["was_on_time"])
                    ),
                }
            )
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Plant life events (recommendation v2)
# ---------------------------------------------------------------------------


# Kinds we know about. Stored as plain TEXT so the UI can introduce new
# kinds without a migration, but anything the engine reacts to should be
# one of these so typos don't silently disable confidence demotion.
LIFE_EVENT_KINDS = frozenset({
    "repot",
    "move",
    "light_change",
    "break",
    "note",
})


def record_event(
    plant_id: str,
    kind: str,
    detail: str | None = None,
    at: date | None = None,
) -> None:
    """Append a ``plant_event`` row.

    Events are free-form: "I just repotted this one", "I went on vacation",
    "Moved to the office". The engine uses them to cap confidence for a
    window after the event, so yesterday's stats don't overconfidently
    drive tomorrow's prediction after an environmental change.
    """
    at = at or date.today()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO plant_event (id, plant_id, at, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), plant_id, at.isoformat(), kind, detail),
        )
        conn.commit()
        logger.info(
            "plant: event id=%s kind=%r at=%s",
            plant_id,
            kind,
            at.isoformat(),
        )
    finally:
        conn.close()


def get_recent_events(
    plant_id: str,
    since_days: int = 30,
    today: date | None = None,
) -> list[dict]:
    """Return ``plant_event`` rows within the last ``since_days``, newest first.

    Returned as plain dicts (``at``, ``kind``, ``detail``) so the drying
    model can consume them without importing this package.
    """
    today = today or date.today()
    cutoff = (today - timedelta(days=int(since_days))).isoformat()
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT at, kind, detail
                 FROM plant_event
                WHERE plant_id = ? AND at >= ?
                ORDER BY at DESC""",
            (plant_id, cutoff),
        ).fetchall()
        return [
            {
                "at": date.fromisoformat(r["at"]),
                "kind": r["kind"],
                "detail": r["detail"],
            }
            for r in rows
        ]
    finally:
        conn.close()


__all__ = [
    "BADGE_MILESTONES",
    "LIFE_EVENT_KINDS",
    "add_plant",
    "update_plant",
    "get_observation_history",
    "get_plant",
    "get_plants",
    "get_recent_events",
    "get_templates",
    "log_watered",
    "record_event",
    "remove_plant",
    "search_templates",
]
