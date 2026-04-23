"""Human-facing place + archetype labels (not model / taxonomy)."""

from __future__ import annotations

from .schema import Plant


def format_place_cue(room_name: str, position_note: str | None) -> str:
    """Room/location and optional position, e.g. ``Kitchen · Right``."""
    r = (room_name or "").strip()
    p = (position_note or "").strip()
    if r and p:
        return f"{r} · {p}"
    return r or p or ""


def archetype_cue(plant: Plant) -> str:
    """Short label for the care template / style — for quick recognition, not ID."""
    if plant.template and (plant.template.name or "").strip():
        return plant.template.name.strip()
    vt = (plant.visual_type or "").strip()
    if vt:
        return vt.replace("_", " ").title()
    return "Houseplant care"
