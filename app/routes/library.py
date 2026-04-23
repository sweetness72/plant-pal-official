"""
Plant Library: GET /library

Browse and search care templates; filter by indoor/outdoor environment.
Category ordering and row HTML are built in this module so the template
stays a clean skeleton with {{ ... |safe }} slots (byte-identical with the
legacy output during refactor).
"""

from collections import defaultdict
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.db import ensure_seeded, get_templates, init_db, search_templates
from core.plant_images import html_plant_img, resolve_care_template_image_url

router = APIRouter()


CATEGORY_PRIORITY = (
    "Herbs & Spices",
    "Fruits & Vegetables",
    "Foliage",
    "Flowering Houseplants",
    "Succulents & Cacti",
    "Ferns",
    "Palms",
    "Bonsai",
    "Trailing & Vines",
    "Easy Care",
    "Flowering Perennials",
    "Shrubs",
    "Trees",
    "Annuals",
    "Bulbs",
    "Drought / Xeriscape",
    "Groundcovers",
    "Ornamental Grasses",
    "Other",
)


def _html_attr_escape(value: str) -> str:
    """Match legacy escaping: &, <, >, "."""
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _active_btn_class(is_active: bool) -> str:
    return (
        "bg-primary-container text-on-primary-container"
        if is_active
        else "bg-surface-container-high text-on-surface"
    )


@router.get("/library", response_class=HTMLResponse)
def plant_library_page(
    request: Request,
    environment: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    """Plant Library: browse by category. Filter with ?environment=indoor|outdoor. Search with ?q=."""
    init_db()
    ensure_seeded()
    env_filter = environment if environment in ("indoor", "outdoor") else None
    search_query = (q or "").strip()
    if search_query:
        care_templates = search_templates(search_query, limit=500, environment=env_filter)
    else:
        care_templates = get_templates(environment=env_filter)

    by_cat: dict[str, list] = defaultdict(list)
    for t in care_templates:
        cat = getattr(t, "category", "") or "Other"
        by_cat[cat].append(t)

    cat_order = [c for c in CATEGORY_PRIORITY if c in by_cat]
    for c in sorted(by_cat.keys()):
        if c not in cat_order:
            cat_order.append(c)

    sections: list[str] = []
    for cat in cat_order:
        plants = by_cat[cat]
        rows: list[str] = []
        for t in plants:
            desc_esc = _html_attr_escape(t.description or "")
            grow_esc = _html_attr_escape(getattr(t, "growing_instructions", "") or "")
            env_badge = "Indoor" if getattr(t, "environment", "indoor") == "indoor" else "Outdoor"
            badge_cls = (
                "lib-badge lib-badge-indoor"
                if env_badge == "Indoor"
                else "lib-badge lib-badge-outdoor"
            )
            grow_block = f'<p class="lib-growing">{grow_esc}</p>' if grow_esc else ""
            lib_thumb = html_plant_img(
                resolve_care_template_image_url(t),
                t.name or "Plant",
                "lib-thumb-img",
            )
            search_text = (
                " ".join(
                    [
                        t.name or "",
                        t.description or "",
                        getattr(t, "growing_instructions", "") or "",
                    ]
                )
                .replace('"', "&quot;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")[:500]
            )
            name_attr = (
                (t.name or "").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            )
            # Library rows exist to drive the Add flow — "read-only catalog"
            # was the IA weakness in the audit. Every row now has a primary
            # CTA to /add-plant with the template pre-selected.
            add_href = f"/add-plant?template_id={quote(str(t.id))}"
            rows.append(
                f"""
                <div class="lib-row" data-name="{name_attr}" data-search="{search_text}">
                    <span class="lib-icon">{lib_thumb}</span>
                    <div class="lib-info">
                        <span class="lib-name">{t.name} <span class="{badge_cls}">{env_badge}</span></span>
                        <span class="lib-meta">Water: {t.watering_frequency_display or "—"} · Light: {t.light_display or "—"}</span>
                        <p class="lib-desc">{desc_esc}</p>
                        {grow_block}
                    </div>
                    <a class="pp-btn pp-btn--sm lib-add-btn" href="{add_href}" aria-label="Add {name_attr} to my garden">Add to my garden</a>
                </div>"""
            )
        block_html = (
            f'<div class="lib-category-block" data-category="{cat.replace(chr(34), "&quot;")}">'
            f'<h2 class="lib-category">{cat}</h2>' + "\n".join(rows) + "</div>"
        )
        sections.append(block_html)

    if not sections and search_query:
        content = (
            f'<p class="empty lib-empty-search">No plants match \u201c{search_query.replace(chr(34), "&quot;")}\u201d. '
            f'Try different words or <a href="/library'
            + ("?environment=" + env_filter if env_filter else "")
            + '">browse all</a>.</p>'
        )
    elif not sections:
        content = '<p class="empty">No plants in library yet.</p>'
    else:
        content = "\n".join(sections)

    base = "/library"
    all_href = base if not search_query else base + "?q=" + quote(search_query)
    indoor_href = (
        base + "?environment=indoor" + ("&q=" + quote(search_query) if search_query else "")
    )
    outdoor_href = (
        base + "?environment=outdoor" + ("&q=" + quote(search_query) if search_query else "")
    )
    reset_href = base + ("?q=" + quote(search_query) if search_query else "")

    search_value_esc = (
        search_query.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    env_hidden = (
        f'<input type="hidden" name="environment" value="{env_filter or ""}"/>'
        if env_filter
        else ""
    )

    from app.main import templates

    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "active": "library",
            "content": content,
            "env_hidden": env_hidden,
            "search_value_esc": search_value_esc,
            "all_href": all_href,
            "indoor_href": indoor_href,
            "outdoor_href": outdoor_href,
            "reset_href": reset_href,
            "all_btn_class": _active_btn_class(not env_filter),
            "indoor_btn_class": _active_btn_class(env_filter == "indoor"),
            "outdoor_btn_class": _active_btn_class(env_filter == "outdoor"),
        },
    )
