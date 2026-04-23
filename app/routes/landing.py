"""
Landing page: GET /

Unified home. Renders today's care list on top and "All plants" below so
``/`` is the home / *Today* screen; ``/plants`` is the dedicated *My plants*
list (see ``app/routes/plants.py``). The route is thin; the view-model is
built from ``core.service.get_todays_recommendations`` plus ``get_plants``.
"""
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.insights import pick_today
from core.db import ensure_seeded, get_plants, init_db
from core.drying_model import predicted_dry_date
from core.identity_cues import archetype_cue, format_place_cue
from core.learning_tier import history_learning_badge
from core.plant_images import html_plant_img, resolve_plant_image_url
from core.schema import ActionType, Plant, Recommendation
from core.service import get_todays_recommendations
from core.ui_copy import recommendation_confidence_for_ui

router = APIRouter()


def _build_today_cards(
    recs_with_plants: list[tuple[Plant, Recommendation]],
    limit: int = 8,
) -> list[dict]:
    """Shape (plant, recommendation) pairs into today-list view-models."""
    rows: list[dict] = []
    for plant, rec in recs_with_plants[:limit]:
        action = rec.action
        if action is None:
            continue
        thumb = html_plant_img(
            resolve_plant_image_url(plant),
            plant.display_name or "Plant",
            "w-full h-full object-cover",
        )
        if action.action_type == ActionType.WATER:
            action_text = f"Water {action.amount_oz} oz"
        else:
            action_text = "Check soil moisture"
        place = format_place_cue(plant.room_name, plant.position_note)
        rows.append({
            "plant_id": plant.id,
            "display_name": plant.display_name,
            "room_name": plant.room_name,
            "place_cue": place,
            "archetype_cue": archetype_cue(plant),
            "note": action.note or "",
            "thumb_html": thumb,
            "action_text": action_text,
            "confidence": recommendation_confidence_for_ui(rec.confidence),
            "history_badge": history_learning_badge(plant.observation_count),
            "factors": rec.factors,
        })
    return rows


def _build_all_plants(plants: list[Plant], today: date) -> list[dict]:
    """Build the 'All plants' grid under today's care."""
    cards: list[dict] = []
    for p in plants:
        due = predicted_dry_date(p, today)
        if due is None:
            due_short, due_tone = "No schedule", "muted"
        elif due < today:
            due_short, due_tone = "Overdue", "urgent"
        elif due == today:
            due_short, due_tone = "Due today", "primary"
        else:
            days = (due - today).days
            due_short = "Tomorrow" if days == 1 else f"In {days} days"
            due_tone = "secondary" if days <= 2 else "muted"
        place = format_place_cue(p.room_name, p.position_note)
        cards.append({
            "id": p.id,
            "display_name": p.display_name,
            "room_name": p.room_name,
            "place_cue": place,
            "archetype_cue": archetype_cue(p),
            "streak": p.current_streak,
            "due_short": due_short,
            "due_tone": due_tone,
            "thumb_html": html_plant_img(
                resolve_plant_image_url(p),
                p.display_name or "Plant",
                "w-full h-full object-cover",
            ),
        })
    cards.sort(key=lambda c: (
        {"urgent": 0, "primary": 1, "secondary": 2, "muted": 3}[c["due_tone"]],
        c["display_name"].lower(),
    ))
    return cards


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    added: str | None = None,
    name: str | None = None,
    e: str | None = None,
) -> HTMLResponse:
    init_db()
    ensure_seeded()
    plants = get_plants()
    today = date.today()
    recs = get_todays_recommendations()
    added_name = (name or "").strip() if added else None

    display_actions = _build_today_cards(recs)
    count = len(display_actions)
    task_label = "task remaining" if count == 1 else "tasks remaining"
    no_plants = len(plants) == 0
    empty_msg = (
        "No plants yet. Start by adding your first plant."
        if no_plants
        else "All plants are happy today."
    )
    insight_title, insight_text, insight_icon = pick_today()
    all_plants = _build_all_plants(plants, today)

    from app.main import templates

    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "active": "today",
            "current_time": date.today().strftime("%b %d"),
            "added_name": added_name,
            "count": count,
            "task_label": task_label,
            "display_actions": display_actions,
            "empty_msg": empty_msg,
            "insight_title": insight_title,
            "insight_text": insight_text,
            "insight_icon": insight_icon,
            "all_plants": all_plants,
            "plants_total": len(plants),
            "today_iso": today.isoformat(),
            "water_date_error": e == "water_date",
        },
    )


__all__ = ["router", "_build_today_cards", "_build_all_plants"]
