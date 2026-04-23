"""
Add Plant form: GET + POST /add-plant

GET renders the form (mostly static markup). Accepts ``?template_id=<id>``
to pre-select a care template — used by Library rows so
"Add to my garden" drops the user into a form that already knows what
the plant is.

POST accepts form fields, inserts the plant via core.db.add_plant, and
redirects back to either the landing page or the My Plants list.
"""
import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from core.db import add_plant, ensure_seeded, get_plants, get_templates, init_db
from core.plant_images import resolve_care_template_image_url
from core.uploads import PhotoRejected, save_plant_photo

logger = logging.getLogger(__name__)

router = APIRouter()


# Rooms we suggest in the datalist even for brand-new users. Existing room
# names used by the user's plants are merged in on top of these.
_SEED_ROOMS = (
    "Living Room",
    "Kitchen",
    "Bedroom",
    "Office",
    "Desk",
    "Bathroom",
    "Hallway",
    "Porch",
    "Balcony",
)


def _room_suggestions() -> list[str]:
    """Return a de-duplicated list of room names for the room datalist.

    Merges seed rooms with every distinct room the user has already typed,
    so the picker 'remembers' past values without requiring any extra DB
    structure. Order: user's existing rooms first, then seeds.
    """
    seen: set[str] = set()
    out: list[str] = []
    for p in get_plants():
        name = (p.room_name or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    for r in _SEED_ROOMS:
        if r.lower() not in seen:
            seen.add(r.lower())
            out.append(r)
    return out


def _resolve_prefill_template(template_id: Optional[str]):
    """Look up a template by id for pre-filling. Returns ``(id, name, image_url)`` or all Nones."""
    if not template_id:
        return None, None, None
    for t in get_templates():
        if str(t.id) == template_id:
            return str(t.id), t.name, resolve_care_template_image_url(t)
    return None, None, None


# Archetype catalogue. Each archetype bundles a human label, a short
# tagline, the default light_level + pot_material we pre-fill on step 2,
# and an icon. The point is to let a new user land somewhere softer than
# a blank form — "what kind of plant is this?" is easier than
# "Monstera Deliciosa or Monstera Adansonii?".
ARCHETYPES: list[dict] = [
    {
        "slug": "succulent",
        "label": "Succulent or cactus",
        "tagline": "Loves sun, hates damp feet.",
        "icon": "wb_sunny",
        "light": "bright",
        "pot": "terracotta",
    },
    {
        "slug": "tropical",
        "label": "Tropical foliage",
        "tagline": "Monstera, pothos, philodendron, calathea.",
        "icon": "forest",
        "light": "medium",
        "pot": "plastic",
    },
    {
        "slug": "flowering",
        "label": "Flowering houseplant",
        "tagline": "Orchids, African violets, peace lilies.",
        "icon": "local_florist",
        "light": "medium",
        "pot": "ceramic",
    },
    {
        "slug": "herb_edible",
        "label": "Herb or edible",
        "tagline": "Basil, rosemary, mint — wants sun and steady water.",
        "icon": "eco",
        "light": "bright",
        "pot": "plastic",
    },
    {
        "slug": "outdoor",
        "label": "Outdoor / porch",
        "tagline": "Anything that lives outside most of the year.",
        "icon": "yard",
        "light": "bright",
        "pot": "terracotta",
    },
    {
        "slug": "other",
        "label": "Not sure / other",
        "tagline": "Start with defaults; adjust as you learn.",
        "icon": "help",
        "light": "medium",
        "pot": "plastic",
    },
]


def _archetype_by_slug(slug: str | None) -> dict | None:
    if not slug:
        return None
    for a in ARCHETYPES:
        if a["slug"] == slug:
            return a
    return None


@router.get("/add-plant", response_class=HTMLResponse)
def add_plant_page(
    request: Request,
    template_id: Optional[str] = None,
    archetype: Optional[str] = None,
) -> HTMLResponse:
    """Render the Add Plant flow.

    Step 1 (no query params) is the archetype picker. Step 2 is the
    detailed form — reached via an archetype slug, a ``template_id`` from
    the Library, or the ``skip`` flag below. Library deep-links stay
    one-click because ``template_id`` implies intent.
    """
    init_db()
    ensure_seeded()
    from app.main import templates

    show_picker = not template_id and not archetype and request.query_params.get("skip") is None
    if show_picker:
        return templates.TemplateResponse(
            request,
            "add_plant_archetype.html",
            {"archetypes": ARCHETYPES},
        )

    prefill_id, prefill_name, prefill_image = _resolve_prefill_template(template_id)
    archetype_obj = _archetype_by_slug(archetype)

    return templates.TemplateResponse(
        request,
        "add_plant.html",
        {
            "room_suggestions": _room_suggestions(),
            "prefill_template_id": prefill_id or "",
            "prefill_template_name": prefill_name or "",
            "prefill_template_image": prefill_image or "",
            "archetype": archetype_obj,
        },
    )


@router.post("/add-plant")
async def add_plant_submit(
    display_name: str = Form(""),
    room_name: str = Form(""),
    position_note: str = Form(""),
    pot_diameter_inches: int = Form(8),
    pot_material: str = Form("plastic"),
    light_level: str = Form("medium"),
    template_id: str = Form(""),
    next: str = Form("/"),
    photo: Optional[UploadFile] = File(None),
):
    """Form POST: add plant and redirect.

    ``next`` can aim post-add redirects at ``/``, ``/plants``, or the legacy
    ``/#all-plants`` fragment on the home page.

    ``photo`` is optional. When provided we resize + re-encode to JPEG
    and store the site path in ``image_override``. Decode failures fall
    through to template artwork — we'd rather add the plant than block
    on a finicky HEIC.
    """
    init_db()
    name = display_name or "Unnamed"

    image_override: str | None = None
    if photo is not None and photo.filename:
        try:
            image_override = save_plant_photo(photo.file, photo.content_type)
        except PhotoRejected as exc:
            logger.warning("Rejecting plant photo for %r: %s", name, exc)
            image_override = None
        finally:
            await photo.close()

    add_plant(
        display_name=name,
        room_name=room_name or "Unknown",
        position_note=(position_note or "").strip() or None,
        pot_diameter_inches=pot_diameter_inches,
        pot_material=pot_material,
        light_level=light_level,
        template_id=template_id or None,
        image_override=image_override,
    )
    n = (next or "").strip()
    name_q = quote(name)
    if n == "/#all-plants":
        url = f"/?added=1&name={name_q}#all-plants"
    elif n == "/plants":
        url = f"/plants?added=1&name={name_q}"
    else:
        url = f"/?added=1&name={name_q}"
    return RedirectResponse(url=url, status_code=303)
