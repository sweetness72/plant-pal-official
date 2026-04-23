"""
Resolve plant card / library image URLs from plant metadata (override, visual_type, category).
PNG assets live under static/plants/ (see static/plants/.gitkeep).

To add or refresh artwork, run: python3 scripts/import_plant_profile_images.py --fill-missing
(Place real PNGs in ~/Downloads/plant_profile-images/<visual_type>.png or pass Stitch zips via --zip.)
"""

from __future__ import annotations

from html import escape

from .schema import CareTemplate, Plant

# Canonical fallbacks (must match files you add under static/plants/)
GENERIC_PLANT = "/static/plants/generic_plant.png"
INDOOR_DEFAULT = "/static/plants/indoor_default.png"
OUTDOOR_DEFAULT = "/static/plants/outdoor_default.png"


def _normalize_override(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.startswith(("http://", "https://")):
        return s
    if s.startswith("/"):
        return s
    return "/" + s.lstrip("/")


def resolve_plant_image_url(plant: Plant) -> str:
    """
    Priority:
    1. image_override (absolute URL or site path)
    2. /static/plants/{plant.visual_type}.png
    3. /static/plants/{template.visual_type}.png
    4. indoor_default / outdoor_default from plant.category or template.environment
    5. generic_plant.png
    """
    ov = _normalize_override(getattr(plant, "image_override", None))
    if ov:
        return ov

    vt = (getattr(plant, "visual_type", None) or "").strip()
    if vt:
        return f"/static/plants/{vt}.png"

    tpl = plant.template
    if tpl:
        tvt = (getattr(tpl, "visual_type", None) or "").strip()
        if tvt:
            return f"/static/plants/{tvt}.png"

    env = _effective_env_category(plant)
    if env == "indoor":
        return INDOOR_DEFAULT
    if env == "outdoor":
        return OUTDOOR_DEFAULT
    return GENERIC_PLANT


def _effective_env_category(plant: Plant) -> str | None:
    """indoor | outdoor from plant.category, else template.environment."""
    c = (getattr(plant, "category", None) or "").strip().lower()
    if c in ("indoor", "outdoor"):
        return c
    tpl = plant.template
    if tpl:
        e = (getattr(tpl, "environment", None) or "").strip().lower()
        if e in ("indoor", "outdoor"):
            return e
    return None


def resolve_care_template_image_url(template: CareTemplate) -> str:
    """Library / search rows: visual_type PNG, then environment default, then generic."""
    vt = (getattr(template, "visual_type", None) or "").strip()
    if vt:
        return f"/static/plants/{vt}.png"
    env = (getattr(template, "environment", None) or "").strip().lower()
    if env == "indoor":
        return INDOOR_DEFAULT
    if env == "outdoor":
        return OUTDOOR_DEFAULT
    return GENERIC_PLANT


def html_plant_img(src: str, alt: str, class_: str = "") -> str:
    """Single <img> with lazy loading and onerror fallback to generic asset."""
    src_q = escape(src, quote=True)
    alt_a = escape(alt or "Plant")
    cls_a = escape(class_ or "")
    gen_q = escape(GENERIC_PLANT, quote=True)
    cls_attr = f' class="{cls_a}"' if cls_a else ""
    return (
        f'<img src="{src_q}" alt="{alt_a}"{cls_attr} loading="lazy" decoding="async" '
        f"onerror=\"this.onerror=null;this.src='{gen_q}';\" />"
    )


def debug_resolve_parts(plant: Plant) -> dict:
    """For /dev/plant-images: raw fields + final URL."""
    return {
        "display_name": plant.display_name,
        "category": getattr(plant, "category", None),
        "visual_type": getattr(plant, "visual_type", None),
        "image_override": getattr(plant, "image_override", None),
        "template_visual_type": (plant.template.visual_type if plant.template else None),
        "template_environment": (plant.template.environment if plant.template else None),
        "resolved_url": resolve_plant_image_url(plant),
    }
