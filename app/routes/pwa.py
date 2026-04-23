"""PWA routes: web manifest, service worker, and hero-image fallback.

The hero fallback exists because older deployments served
``/static/plant-pal-hero.png`` from the working directory instead of the
package directory. Keeping the explicit handler guarantees the image
resolves regardless of where the app is launched from.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_HERO_PATH = _STATIC_DIR / "plant-pal-hero.png"

router = APIRouter()


def _hero_path() -> Path | None:
    if _HERO_PATH.exists():
        return _HERO_PATH
    cwd_hero = Path.cwd() / "app" / "static" / "plant-pal-hero.png"
    if cwd_hero.exists():
        return cwd_hero
    legacy_cwd_hero = Path.cwd() / "static" / "plant-pal-hero.png"
    return legacy_cwd_hero if legacy_cwd_hero.exists() else None


@router.get("/static/plant-pal-hero.png", include_in_schema=False)
def serve_hero():
    """Explicit hero image handler so it resolves from any run directory."""
    p = _hero_path()
    if p:
        return FileResponse(p, media_type="image/png")
    raise HTTPException(
        status_code=404,
        detail="Hero image not found. Add static/plant-pal-hero.png next to app.py or in cwd.",
    )


@router.get("/manifest.json", response_class=JSONResponse)
def pwa_manifest():
    """Web app manifest so the panel can be added to home screen and opened like an app."""
    manifest_path = _STATIC_DIR / "manifest.json"
    return FileResponse(manifest_path, media_type="application/manifest+json")


@router.get("/sw.js", response_class=Response)
def service_worker():
    """Minimal service worker so browsers offer 'Install' / Add to Home Screen."""
    sw_path = _STATIC_DIR / "js" / "sw.js"
    return FileResponse(sw_path, media_type="application/javascript")
