"""Developer-only introspection routes. Not part of the product UI."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from core.db import ensure_seeded, get_plants, get_templates, init_db
from core.plant_images import (
    debug_resolve_parts,
    html_plant_img,
    resolve_care_template_image_url,
)

router = APIRouter()


@router.get("/dev/plant-images", response_class=HTMLResponse, include_in_schema=False)
def dev_plant_images_page() -> HTMLResponse:
    """Inspect per-plant image resolution (override, types, fallbacks)."""
    init_db()
    ensure_seeded()

    def esc(x: object) -> str:
        s = "" if x is None else str(x)
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    plants = get_plants()
    rows = []
    for p in plants:
        d = debug_resolve_parts(p)
        rows.append(
            "<tr><td>"
            + esc(d["display_name"])
            + "</td><td>"
            + esc(d["category"] or "—")
            + "</td><td>"
            + esc(d["visual_type"] or "—")
            + "</td><td>"
            + esc(d["image_override"] or "—")
            + "</td><td>"
            + esc(d["template_visual_type"] or "—")
            + "</td><td>"
            + esc(d["template_environment"] or "—")
            + "</td><td><code>"
            + esc(d["resolved_url"])
            + "</code></td><td>"
            + html_plant_img(d["resolved_url"], d["display_name"], "h-14 w-14 object-cover rounded-lg")
            + "</td></tr>"
        )

    tpl_rows = []
    for t in get_templates():
        tpl_rows.append(
            "<tr><td>"
            + esc(t.name)
            + "</td><td>"
            + esc(t.slug)
            + "</td><td>"
            + esc(t.environment)
            + "</td><td>"
            + esc(t.visual_type or "—")
            + "</td><td><code>"
            + esc(resolve_care_template_image_url(t))
            + "</code></td><td>"
            + html_plant_img(resolve_care_template_image_url(t), t.name, "h-12 w-12 object-cover rounded")
            + "</td></tr>"
        )

    body = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        "<title>Plant images (dev)</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:1.25rem;line-height:1.45}"
        "table{border-collapse:collapse;margin-top:.75rem} td,th{border:1px solid #ccc;padding:.45rem .65rem;text-align:left;vertical-align:middle}"
        "code{font-size:.8rem} h2{margin-top:2rem}</style></head><body>"
        "<h1>Plant image resolver</h1>"
        "<p>Developer view. <a href=\"/\">Home</a> · <a href=\"/plants\">My Plants</a> · <a href=\"/library\">Library</a></p>"
        "<h2>Your plants</h2>"
        "<table><thead><tr><th>Name</th><th>category</th><th>visual_type</th><th>image_override</th>"
        "<th>template.visual_type</th><th>template.env</th><th>Resolved</th><th>Preview</th></tr></thead><tbody>"
        + ("".join(rows) if rows else "<tr><td colspan=\"8\">No plants yet.</td></tr>")
        + "</tbody></table>"
        "<h2>Library templates (sample)</h2>"
        "<table><thead><tr><th>Name</th><th>slug</th><th>environment</th><th>visual_type</th><th>Resolved</th><th>Preview</th></tr></thead><tbody>"
        + ("".join(tpl_rows) if tpl_rows else "<tr><td colspan=\"6\">No templates.</td></tr>")
        + "</tbody></table>"
        "</body></html>"
    )
    return HTMLResponse(body)
