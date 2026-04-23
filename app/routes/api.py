"""JSON API endpoints under /api/*."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.watering_date import validate_watered_date
from core.db import (
    add_plant,
    ensure_seeded,
    get_plant,
    get_plants,
    get_templates,
    init_db,
    log_watered,
    search_templates,
)
from core.drying_model import predicted_dry_date
from core.icons import get_icon_svg
from core.plant_images import resolve_care_template_image_url, resolve_plant_image_url
from core.service import get_todays_actions

router = APIRouter(prefix="/api")


# --- Request/parameter enums (API boundary) --------------------------------


class PotMaterialField(StrEnum):
    plastic = "plastic"
    ceramic = "ceramic"
    terracotta = "terracotta"


class LightLevelField(StrEnum):
    low = "low"
    medium = "medium"
    bright = "bright"


class SoilFeelingField(StrEnum):
    dry = "dry"
    ok = "ok"
    wet = "wet"


class TemplateEnvironmentField(StrEnum):
    """Filter for care-template listing endpoints."""

    indoor = "indoor"
    outdoor = "outdoor"


# --- Pydantic bodies -------------------------------------------------------


class AddPlantBody(BaseModel):
    """``POST /api/plants`` JSON body."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    room_name: str = Field(min_length=1)
    pot_diameter_inches: int = Field(default=8, ge=1, le=36)
    pot_material: PotMaterialField = PotMaterialField.plastic
    light_level: LightLevelField = LightLevelField.medium
    template_id: str | None = None
    position_note: str | None = None


class LogWateredBody(BaseModel):
    """``POST /api/plants/{id}/log-watered`` JSON body."""

    model_config = ConfigDict(extra="forbid")

    soil_feeling: SoilFeelingField = SoilFeelingField.ok
    # Omit or null → *today* in ``log_watered`` (server date).
    watered_date: date | None = None


# --- Endpoints -------------------------------------------------------------


@router.get("/actions/today")
def api_todays_actions():
    """JSON list of today's actions with plant info (for panels or other clients)."""
    actions_with_plants = get_todays_actions()
    return [
        {
            "plant_id": str(plant.id),
            "display_name": plant.display_name,
            "room_name": plant.room_name,
            "action_type": action.action_type.value,
            "amount_oz": action.amount_oz,
            "note": action.note,
            "image_url": resolve_plant_image_url(plant),
        }
        for plant, action in actions_with_plants
    ]


@router.get("/templates")
def api_list_templates(environment: TemplateEnvironmentField | None = None):
    """List care templates. Optional ?environment=indoor|outdoor."""
    init_db()
    ensure_seeded()
    env: str | None = environment.value if environment is not None else None
    templates = get_templates(environment=env)
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "default_drying_days": t.default_drying_days,
            "moisture_preference": t.moisture_preference,
            "icon_id": t.icon_id,
            "watering_frequency_display": t.watering_frequency_display,
            "light_display": t.light_display,
            "description": t.description,
            "environment": getattr(t, "environment", "indoor"),
            "visual_type": getattr(t, "visual_type", "") or "",
            "image_url": resolve_care_template_image_url(t),
        }
        for t in templates
    ]


@router.get("/templates/search")
def api_search_templates(
    q: str | None = None,
    environment: TemplateEnvironmentField | None = None,
):
    """
    Search templates by name. Uses parameterized queries only (no SQL injection).
    Optional ?environment=indoor|outdoor to filter.
    """
    init_db()
    ensure_seeded()
    env: str | None = environment.value if environment is not None else None
    templates = search_templates(q or "", limit=25, environment=env)
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "icon_id": getattr(t, "icon_id", None) or t.slug,
            "icon_svg": get_icon_svg(getattr(t, "icon_id", None) or t.slug),
            "image_url": resolve_care_template_image_url(t),
            "watering_frequency_display": t.watering_frequency_display,
            "light_display": t.light_display,
            "description": t.description,
            "environment": getattr(t, "environment", "indoor"),
            "visual_type": getattr(t, "visual_type", "") or "",
        }
        for t in templates
    ]


@router.get("/plants")
def api_list_plants():
    """List all plants (for the current user)."""
    init_db()
    plants = get_plants()
    today = date.today()
    return [
        {
            "id": str(p.id),
            "display_name": p.display_name,
            "room_name": p.room_name,
            "position_note": getattr(p, "position_note", None),
            "pot_diameter_inches": p.pot_diameter_inches,
            "pot_material": p.pot_material,
            "light_level": p.light_level,
            "last_watered_date": p.last_watered_date.isoformat() if p.last_watered_date else None,
            "drying_coefficient": p.drying_coefficient,
            "current_streak": p.current_streak,
            "longest_streak": p.longest_streak,
            "badges_earned": p.badges_earned,
            "due_date": (d.isoformat() if (d := predicted_dry_date(p, today)) else None),
            "category": getattr(p, "category", None),
            "visual_type": getattr(p, "visual_type", None),
            "image_override": getattr(p, "image_override", None),
            "image_url": resolve_plant_image_url(p),
        }
        for p in plants
    ]


@router.post("/plants")
def api_add_plant(body: AddPlantBody):
    """Add a new plant."""
    init_db()
    pos = (body.position_note or "").strip() or None
    plant = add_plant(
        display_name=body.display_name,
        room_name=body.room_name,
        position_note=pos,
        pot_diameter_inches=body.pot_diameter_inches,
        pot_material=body.pot_material.value,
        light_level=body.light_level.value,
        template_id=body.template_id,
    )
    return {"id": str(plant.id), "display_name": plant.display_name}


@router.post("/plants/{plant_id}/log-watered")
def api_log_watered(plant_id: UUID, body: LogWateredBody | None = None):
    """
    JSON: mark plant as watered.

    ``soil_feeling`` tunes the learning coefficient; omitted body or
    ``{}`` defaults to ``"ok"``. ``watered_date`` (optional ISO date) may
    be in the *past* or *today* to backfill; future dates and dates before
    the last recorded watering are rejected. Omit ``watered_date`` for
    *today*.

    HTML form callers: ``POST /plants/{id}/water`` in
    ``app/routes/plants.py`` (``next=`` + ``watered_on=``).
    """
    init_db()
    b = body if body is not None else LogWateredBody()
    wd = b.watered_date
    plant = get_plant(str(plant_id))
    if wd is not None:
        try:
            validate_watered_date(plant, wd)
        except ValueError as exc:
            code = str(exc)
            msg = {
                "future": "watered_date cannot be in the future",
                "before_last": "watered_date cannot be before the last recorded watering",
            }.get(
                code,
                "invalid watered_date",
            )
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "type": "value_error",
                        "loc": ("body", "watered_date"),
                        "msg": msg,
                    }
                ],
            ) from exc
    log_watered(
        str(plant_id), watered_date=wd, soil_feeling=b.soil_feeling.value
    )
    return RedirectResponse(url="/", status_code=303)
