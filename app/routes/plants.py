"""
Plant routes.

The plant list also appears on ``/`` under *All plants*; ``GET /plants`` is
the dedicated *My plants* screen with the same grid. Everything else here is
per-plant:

- ``GET /plants``              → my plants grid (all plants in the home)
- ``GET /plants/{id}``         → plant detail page (history + explanation)
- ``POST /plants/{id}/water``  → form submit (optional ``watered_on`` backdate)
- ``POST /plants/{id}/event``  → record a life event (repot, move, …)
- ``POST /plants/{id}/remove`` → delete + back to home
"""
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.add_plant import _room_suggestions
from app.watering_date import parse_optional_iso_date, validate_watered_date
from core.db import (
    LIFE_EVENT_KINDS,
    ensure_seeded,
    get_observation_history,
    get_plant,
    get_plants,
    get_recent_events,
    get_templates,
    init_db,
    log_watered,
    record_event,
    remove_plant,
    update_plant,
)
from core.drying_model import predicted_dry_date
from core.identity_cues import archetype_cue, format_place_cue
from core.learning_tier import history_learning_badge
from core.plant_images import html_plant_img, resolve_plant_image_url
from core.service import get_plant_recommendation
from core.ui_copy import recommendation_confidence_for_ui

router = APIRouter()


_VALID_SOIL = {"dry", "ok", "wet"}


def _safe_next(next_value: str | None, default: str = "/") -> str:
    """Reject open-redirect targets. Same-origin absolute paths only."""
    if not next_value:
        return default
    n = next_value.strip()
    if not n.startswith("/") or n.startswith("//") or "://" in n or "\n" in n:
        return default
    return n


def _add_query_param(relative_path: str, key: str, value: str) -> str:
    """Append a query key to a same-site path, replacing an existing value for *key*."""
    rel = (relative_path or "/").strip() or "/"
    if not rel.startswith("/"):
        rel = "/" + rel
    sp = urlsplit(rel)
    path = sp.path or "/"
    pairs = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True) if k != key]
    pairs.append((key, value))
    qs = urlencode(pairs)
    return f"{path}?{qs}" if qs else path


@router.get("/plants", response_class=HTMLResponse)
def my_plants_page(
    request: Request,
    added: str | None = None,
    name: str | None = None,
) -> HTMLResponse:
    """All plants in your home (same grid data as the *All plants* section on ``/``)."""
    init_db()
    ensure_seeded()
    from app.routes.landing import _build_all_plants

    plants = get_plants()
    today = date.today()
    all_plants = _build_all_plants(plants, today)
    added_name = (name or "").strip() if added else None

    from app.main import templates

    return templates.TemplateResponse(
        request,
        "my_plants.html",
        {
            "active": "plants",
            "all_plants": all_plants,
            "plants_total": len(plants),
            "added_name": added_name,
        },
    )


@router.get("/plants/{plant_id}", response_class=HTMLResponse)
def plant_detail(
    request: Request,
    plant_id: str,
    e: str | None = None,
) -> HTMLResponse:
    """Plant detail: history timeline, explanation, and life-event actions."""
    init_db()
    ensure_seeded()
    plant = get_plant(plant_id)
    if plant is None:
        return HTMLResponse(
            "<h1>Plant not found</h1><p><a href='/'>Back home</a></p>",
            status_code=404,
        )

    today = date.today()
    rec = get_plant_recommendation(plant, today=today)
    due = predicted_dry_date(plant, today)
    history = get_observation_history(plant_id, limit=20)
    events = get_recent_events(plant_id, since_days=180)

    if due is None:
        due_label = "No schedule yet"
    elif due < today:
        due_label = f"Overdue — was due {due.isoformat()}"
    elif due == today:
        due_label = "Due today"
    else:
        days = (due - today).days
        due_label = "Tomorrow" if days == 1 else f"In {days} days ({due.isoformat()})"

    timeline: list[dict] = []
    for h in history:
        watered = h.get("observed_at")
        interval = h.get("interval_days")
        if watered is None:
            continue
        desc = "Watered"
        if interval is not None:
            desc += f" · {int(interval)}d since last"
        soil = h.get("soil_feeling")
        if soil and soil != "ok":
            desc += f" · felt {soil}"
        timeline.append({"when": watered.isoformat(), "what": desc})
    for e in events:
        when = e.get("at")
        if when is None:
            continue
        kind = e.get("kind", "note")
        label = {
            "repot": "Repotted",
            "move": "Moved",
            "light_change": "Light changed",
            "break": "Care break",
            "note": "Note",
        }.get(kind, kind.replace("_", " ").title())
        detail = e.get("detail")
        timeline.append({
            "when": when.isoformat(),
            "what": f"{label}{f' — {detail}' if detail else ''}",
        })
    timeline.sort(key=lambda row: row["when"], reverse=True)

    stats = [
        {"label": "Current streak", "value": f"{plant.current_streak}d"},
        {"label": "Longest streak", "value": f"{plant.longest_streak}d"},
        {
            "label": "Observed interval",
            "value": (
                f"{plant.interval_mean_days:.1f}d"
                if plant.interval_mean_days is not None
                else "—"
            ),
        },
        {"label": "Waterings logged", "value": str(plant.observation_count)},
    ]

    thumb_html = html_plant_img(
        resolve_plant_image_url(plant),
        plant.display_name or "Plant",
        "w-full h-full object-cover",
    )

    from app.main import templates

    return templates.TemplateResponse(
        request,
        "plant_detail.html",
        {
            "active": "plants",
            "plant": plant,
            "place_cue": format_place_cue(plant.room_name, plant.position_note),
            "archetype_cue": archetype_cue(plant),
            "thumb_html": thumb_html,
            "due_label": due_label,
            "rec": rec,
            "confidence_chip": recommendation_confidence_for_ui(rec.confidence),
            "history_badge": history_learning_badge(plant.observation_count),
            "timeline": timeline,
            "stats": stats,
            "event_kinds": sorted(LIFE_EVENT_KINDS),
            "today_iso": today.isoformat(),
            "water_date_error": e == "water_date",
        },
    )


@router.get("/plants/{plant_id}/edit", response_class=HTMLResponse)
def plant_edit_page(request: Request, plant_id: str) -> HTMLResponse:
    init_db()
    ensure_seeded()
    plant = get_plant(plant_id)
    if plant is None:
        return HTMLResponse(
            "<h1>Plant not found</h1><p><a href='/'>Back home</a></p>",
            status_code=404,
        )
    templates_list = get_templates()
    from app.main import templates as jt

    return jt.TemplateResponse(
        request,
        "edit_plant.html",
        {
            "plant": plant,
            "care_templates": templates_list,
            "room_suggestions": _room_suggestions(),
        },
    )


@router.post("/plants/{plant_id}/edit")
def plant_edit_post(
    plant_id: str,
    display_name: str = Form(""),
    room_name: str = Form(""),
    position_note: str = Form(""),
    template_id: str = Form(""),
    light_level: str = Form("medium"),
    pot_diameter_inches: int = Form(8),
    pot_material: str = Form("plastic"),
) -> RedirectResponse:
    init_db()
    p = get_plant(plant_id)
    if p is None:
        return RedirectResponse(url="/", status_code=303)
    name = (display_name or "").strip() or p.display_name
    room = (room_name or "").strip() or "Unknown"
    pos = (position_note or "").strip() or None
    tid = (template_id or "").strip() or None
    mat = pot_material if pot_material in ("plastic", "ceramic", "terracotta") else "plastic"
    light = light_level if light_level in ("low", "medium", "bright") else "medium"
    update_plant(
        plant_id,
        display_name=name,
        room_name=room,
        position_note=pos,
        template_id=tid,
        light_level=light,
        pot_diameter_inches=int(pot_diameter_inches),
        pot_material=mat,
    )
    return RedirectResponse(url=f"/plants/{plant_id}", status_code=303)


@router.post("/plants/{plant_id}/water")
def water_plant_post(
    plant_id: str,
    soil_feeling: str = Form("ok"),
    next: str = Form("/"),
    watered_on: str = Form(""),
) -> RedirectResponse:
    """Mark a plant as watered from an HTML form (optional *backdated* date)."""
    init_db()
    plant = get_plant(plant_id)
    if plant is None:
        return RedirectResponse(url=_safe_next(next, "/"), status_code=303)
    try:
        wd = parse_optional_iso_date(watered_on)
        if wd is not None:
            validate_watered_date(plant, wd)
    except ValueError:
        return RedirectResponse(
            url=_add_query_param(
                _safe_next(next, "/"),
                "e",
                "water_date",
            ),
            status_code=303,
        )
    sf = soil_feeling if soil_feeling in _VALID_SOIL else "ok"
    log_watered(plant_id, watered_date=wd, soil_feeling=sf)
    return RedirectResponse(url=_safe_next(next, "/"), status_code=303)


@router.post("/plants/{plant_id}/event")
def plant_event_post(
    plant_id: str,
    kind: str = Form(...),
    detail: str = Form(""),
    next: str = Form(""),
) -> RedirectResponse:
    """Record a life event (repot, move, light_change, …) for a plant.

    Unknown ``kind`` values are rejected silently (coerced to ``note``)
    because the engine only reacts to ``LIFE_EVENT_KINDS`` members. This
    keeps the form resilient to typo-level drift without 500s.
    """
    safe_kind = kind if kind in LIFE_EVENT_KINDS else "note"
    trimmed = (detail or "").strip()[:500] or None
    record_event(plant_id, kind=safe_kind, detail=trimmed)
    fallback = f"/plants/{plant_id}"
    return RedirectResponse(url=_safe_next(next, fallback), status_code=303)


@router.post("/plants/{plant_id}/remove")
def remove_plant_post(plant_id: str) -> RedirectResponse:
    """Remove a plant and return to home."""
    remove_plant(plant_id)
    return RedirectResponse(url="/", status_code=303)


__all__ = ["router"]
