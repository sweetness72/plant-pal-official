#!/usr/bin/env python3
"""
Web app: panel + API. Data lives in data/plant_panel.db (SQLite).
Run locally: ./run.sh  →  http://127.0.0.1:8000
Docker: image listens on PLANTPAL_HOST (default 0.0.0.0) and PLANTPAL_PORT (default 8000); persist data by mounting a volume on /app/data.
"""
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from core.db import add_plant, ensure_seeded, get_plants, get_templates, init_db, log_watered, remove_plant, search_templates
from core.drying_model import generate_actions_for_today, predicted_dry_date
from core.icons import get_icon_svg
from core.schema import ActionType
from core.service import get_todays_actions

app = FastAPI(title="Plant Pal")

# Hero image path: next to app.py, or in cwd (so it works from any run directory)
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_HERO_PATH = _STATIC_DIR / "plant-pal-hero.png"

def _hero_path() -> Path | None:
    if _HERO_PATH.exists():
        return _HERO_PATH
    cwd_hero = Path.cwd() / "static" / "plant-pal-hero.png"
    return cwd_hero if cwd_hero.exists() else None

# Serve hero image explicitly so it works from any run directory (before mount)
@app.get("/static/plant-pal-hero.png", include_in_schema=False)
def _serve_hero():
    p = _hero_path()
    if p:
        return FileResponse(p, media_type="image/png")
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Hero image not found. Add static/plant-pal-hero.png next to app.py or in cwd.")

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Landing-page rotating growth insights (changes every 3 days).
GROWTH_INSIGHTS = [
    ("Leaf Care", "Dusting leaves helps plants photosynthesize more efficiently.", "eco"),
    ("Water Rhythm", "Water deeply, then let the top layer dry before watering again.", "water_drop"),
    ("Light Check", "Rotate pots weekly for balanced growth and fewer leaning stems.", "wb_sunny"),
    ("Root Health", "Use pots with drainage to prevent soggy roots and rot.", "compress"),
    ("Humidity Boost", "Cluster plants together to create a small humidity pocket.", "humidity_percentage"),
    ("Morning Habit", "Check soil in the morning when moisture readings are most consistent.", "schedule"),
    ("Growth Spurts", "New leaves often arrive faster after brighter, steady light.", "trending_up"),
    ("Season Shift", "Most plants need less water in cooler, darker months.", "calendar_month"),
    ("Feed Smart", "Use diluted fertilizer during active growth, not every watering.", "science"),
    ("Potting Mix", "Chunky, airy soil keeps roots oxygenated and resilient.", "filter_vintage"),
    ("Drainage Tip", "Empty saucers after watering so roots do not sit in water.", "water_ec"),
    ("Pruning", "Trim yellowing leaves to redirect energy to healthy growth.", "content_cut"),
    ("Airflow", "Gentle airflow reduces fungus risk and strengthens stems.", "air"),
    ("Sun Balance", "Bright indirect light is safer than long harsh direct sun.", "light_mode"),
    ("Repot Cue", "Repot when roots circle tightly or poke from drainage holes.", "home_repair_service"),
    ("Pest Patrol", "Inspect leaf undersides weekly for early pest detection.", "search"),
    ("Consistency", "Stable routines beat perfect routines for plant health.", "repeat"),
    ("Room Match", "Place humidity lovers away from dry vents and heaters.", "device_thermostat"),
    ("Soil Probe", "A finger test 1-2 inches deep beats surface-only checks.", "touch_app"),
    ("Recovery", "If overwatered, improve airflow and pause watering until dry.", "health_and_safety"),
    ("Leaf Signals", "Droop can mean thirst, but soggy soil points to overwatering.", "monitor_heart"),
    ("Bright Corners", "South and west windows usually provide stronger growth light.", "window"),
    ("Even Canopy", "Turn plants toward light every few days for fuller shape.", "rotate_right"),
    ("Humidity Assist", "Pebble trays can raise local humidity around tropicals.", "waves"),
    ("Root Space", "Slightly snug roots are fine; severely bound roots need repotting.", "crop_square"),
    ("Water Quality", "Room-temperature water avoids shocking sensitive roots.", "thermostat"),
    ("Sun Acclimation", "Increase direct sun gradually to prevent leaf scorch.", "solar_power"),
    ("Trim Timing", "Prune in active growth periods for faster recovery.", "event_available"),
    ("Soil Refresh", "Top-dress with fresh mix yearly to restore structure.", "refresh"),
    ("Observation", "A 30-second daily glance catches issues before they spread.", "visibility"),
]

# Cozy lo-fi palette: warm cream, soft browns, plant green (no extra ports: bind 127.0.0.1 only)
_COMMON_CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600&family=Nunito:wght@400;600;700&display=swap');
    :root {
        --surface: #fef9f1;
        --surface-container-low: #f8f3eb;
        --surface-container: #f2ede5;
        --surface-container-high: #ece8e0;
        --surface-container-lowest: #ffffff;
        --on-surface: #1d1c17;
        --primary: #0f5234;
        --primary-container: #2d6b4a;
        --outline-variant: #c0c9c0;
        --secondary-container: #aceec7;
        --on-secondary-container: #2f6e4f;
        --shadow-ambient: 0 20px 40px -12px rgba(29, 28, 23, 0.06);
        --ghost-border: 1px solid rgba(192, 201, 192, 0.15);
    }
    * { box-sizing: border-box; }
    body { font-family: 'Nunito', system-ui, sans-serif; background: var(--surface); color: var(--on-surface); margin: 0; padding: 1.5rem; min-height: 100vh; position: relative; }
    a { color: var(--primary-container); text-decoration: none; }
    a:hover { color: #4a8b5e; }
    .skip-link { position: absolute; top: -3rem; left: 0.5rem; padding: 0.6rem 1rem; background: #2d6b4a; color: #faf8f5; border-radius: 12px; font-size: 0.9rem; font-weight: 600; z-index: 100; transition: top 0.2s; }
    .skip-link:focus { top: 0.5rem; outline: 2px solid #3d7c5c; outline-offset: 2px; }
    .brand { font-family: 'Fredoka', 'Nunito', sans-serif; font-weight: 600; color: var(--primary-container); letter-spacing: -0.02em; text-shadow: 0 1px 2px rgba(45,107,74,0.15); }
    .brand-hero { font-size: clamp(1.75rem, 8vw, 2.5rem); line-height: 1.1; margin: 0 0 0.15rem 0; }
    .brand-small { font-size: 1.1rem; margin: 0 0 0.5rem 0; }
    .pill-btn, button, .cta, .plants-cta, .weather-btn {
        border-radius: 999px;
        border: none;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        background: linear-gradient(135deg, var(--primary) 0%, var(--primary-container) 100%);
        color: #fff;
        box-shadow: 0 8px 18px rgba(15,82,52,0.18);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .pill-btn:hover, button:hover, .cta:hover, .plants-cta:hover, .weather-btn:hover {
        transform: scale(1.02);
        box-shadow: 0 12px 22px rgba(15,82,52,0.22);
    }
    input, select {
        background: var(--surface-container-low);
        border: none;
        border-radius: 1.5rem;
    }
    input:focus, select:focus {
        outline: 2px solid rgba(192, 201, 192, 0.3);
        background: var(--surface-container-lowest);
    }
    /* Touch support: remove tap delay, subtle tap highlight, active feedback */
    button, a, [role="button"], .search-hit, .filter-btn { -webkit-tap-highlight-color: rgba(45,107,74,0.2); touch-action: manipulation; }
    button:active, .done:active, .remove-btn:active, .plants-cta:active, .filter-btn:active { opacity: 0.9; }
    @media (max-width: 767px) { button, .remove-btn, .plants-cta, .filter-btn, .lib-search-form button, .weather-btn, .done, .lib-back-top, .cta, .cta-secondary { min-height: 44px; padding: 0.5rem 0.75rem; display: inline-flex; align-items: center; justify-content: center; } .nav a { padding: 0.5rem 0.4rem; } }
"""
# Cozy room background (opaque, behind content). Page-specific opacity so home is "big sell", others don't disrupt.
_COZY_BG_CSS = """
    .cozy-bg { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
    .cozy-bg[data-page="home"] { opacity: 0.38; }
    .cozy-bg[data-page="library"] { opacity: 0.26; }
    .cozy-bg[data-page="plants"] { opacity: 0.26; }
    .cozy-bg[data-page="add"] { opacity: 0.26; }
    .cozy-bg svg.cozy-room { width: 100%; height: 100%; object-fit: cover; }
    .cozy-digital-clock { position: absolute; top: 1rem; right: 1rem; min-width: 4rem; padding: 0.4rem 0.6rem; background: rgba(255,255,255,0.72); border-radius: 999px; box-shadow: var(--shadow-ambient); border: var(--ghost-border); font-family: 'Nunito', system-ui, sans-serif; font-size: 1.1rem; font-weight: 700; color: #4a4540; text-align: center; letter-spacing: 0.02em; backdrop-filter: blur(8px); }
    .cozy-steam { animation: cozy-steam 3s ease-in-out infinite; opacity: 0.5; }
    @keyframes cozy-steam { 0%, 100% { transform: translateY(0) scale(1); opacity: 0.3; } 50% { transform: translateY(-8px) scale(1.1); opacity: 0.5; } }
    .cozy-content { position: relative; z-index: 1; }
"""

def _cozy_bg_html(page: str) -> str:
    """Page-specific cozy background. Home = full room; others = same scene, CSS opacity varies."""
    # Same cozy room SVG for all; no analog clock — we use a cute digital clock overlay
    room_svg = """
        <svg class="cozy-room" viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="cozy-wall" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#e8e0d5"/><stop offset="100%" style="stop-color:#d4c9bb"/></linearGradient>
                <linearGradient id="cozy-table" x1="0%" y1="100%" x2="0%" y2="0%"><stop offset="0%" style="stop-color:#8a7a6a"/><stop offset="100%" style="stop-color:#a09080"/></linearGradient>
            </defs>
            <rect width="400" height="300" fill="url(#cozy-wall)"/>
            <rect x="40" y="40" width="120" height="90" rx="4" fill="#c4b5a0" opacity="0.6"/>
            <rect x="50" y="55" width="30" height="35" fill="#7d8b6f" opacity="0.7"/>
            <rect x="95" y="50" width="25" height="40" fill="#8b9a7a" opacity="0.7"/>
            <rect x="130" y="58" width="22" height="32" fill="#7d8b6f" opacity="0.7"/>
            <rect x="0" y="200" width="400" height="100" fill="url(#cozy-table)"/>
            <ellipse cx="120" cy="245" rx="35" ry="12" fill="#6a5a4a"/>
            <rect x="105" y="218" width="30" height="28" rx="3" fill="#b8a898"/>
            <ellipse cx="120" cy="218" rx="8" ry="5" fill="#4a4540"/>
            <ellipse class="cozy-steam" cx="120" cy="212" rx="6" ry="4" fill="#d4c9bb" opacity="0.5"/>
            <rect x="268" y="218" width="64" height="32" rx="8" fill="#a09080" opacity="0.9"/>
        </svg>"""
    return f'<div class="cozy-bg" data-page="{page}" aria-hidden="true">' + room_svg + '<div class="cozy-digital-clock" id="cozy-digital-time">—:——</div></div>'

_COZY_CLOCK_JS = """
    (function() {
        function updateCozyClock() {
            var el = document.getElementById('cozy-digital-time');
            if (!el) return;
            var now = new Date();
            var h = now.getHours(), m = now.getMinutes();
            var h12 = h % 12 || 12;
            el.textContent = h12 + ':' + (m < 10 ? '0' : '') + m;
        }
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', updateCozyClock);
        else updateCozyClock();
        setInterval(updateCozyClock, 60000);
    })();
"""
# CSS for the animated scene (use on any page that includes _ANIMATED_SCENE)
_LOFI_SCENE_CSS = """
        .lofi-scene { margin: 0 auto 1rem; max-width: 200px; opacity: 0.85; }
        .lofi-float { animation: lofi-float 4s ease-in-out infinite; }
        .lofi-svg { width: 100%; height: auto; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); }
        @keyframes lofi-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
"""
# Muted olive watering can for header and card (matches reference UI)
_WATERING_CAN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="22" height="22" fill="#6b7b5c" aria-hidden="true"><path d="M19 5v1.5L17 9v10c0 1.1-.9 2-2 2H9c-1.1 0-2-.9-2-2V9L5 6.5V5c0-.55.45-1 1-1h2V2h2v2h6V2h2v2h2c.55 0 1 .45 1 1zM9 19h6V9.5l2-3H7l2 3V19z"/></svg>"""

# Small animated lo-fi scene (floating plant) – inline SVG + CSS keyframes
_ANIMATED_SCENE = """
    <div class="lofi-scene" aria-hidden="true">
        <div class="lofi-float">
            <svg class="lofi-svg" viewBox="0 0 120 80" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <linearGradient id="lofi-sky" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" style="stop-color:#e8e0d5"/><stop offset="100%" style="stop-color:#d4c9bb"/></linearGradient>
                    <linearGradient id="lofi-pot" x1="0%" y1="100%" x2="0%" y2="0%"><stop offset="0%" style="stop-color:#a09080"/><stop offset="100%" style="stop-color:#c4b5a0"/></linearGradient>
                </defs>
                <rect width="120" height="80" fill="url(#lofi-sky)"/>
                <ellipse cx="60" cy="72" rx="50" ry="8" fill="#d4c9bb" opacity="0.6"/>
                <path d="M42 72 L48 52 L54 72 L60 48 L66 72 L72 52 L78 72" fill="none" stroke="#7d8b6f" stroke-width="2.5" stroke-linecap="round"/>
                <ellipse cx="60" cy="42" rx="18" ry="12" fill="#8b9a7a" opacity="0.9"/>
                <rect x="52" y="52" width="16" height="20" rx="2" fill="url(#lofi-pot)"/>
                <rect x="50" y="72" width="20" height="4" rx="1" fill="#8a7a6a"/>
            </svg>
        </div>
    </div>
"""


# ---------- Panel (HTML) ----------

def _render_panel(actions_with_plants: list[tuple], no_plants: bool = False, added_name: Optional[str] = None) -> str:
    """Render landing page using the new editorial glassmorphism layout."""
    from string import Template

    def _esc(value: str) -> str:
        return (
            (value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    now_str = date.today().strftime("%A, %B %d")
    action_rows = []
    for plant, action in actions_with_plants[:6]:
        icon_svg = get_icon_svg(plant.get_icon_id())
        action_text = (
            f"Water {action.amount_oz} oz"
            if action.action_type == ActionType.WATER
            else "Check soil moisture"
        )
        action_note = _esc(action.note or "")
        name_esc = _esc(plant.display_name)
        room_esc = _esc(plant.room_name)
        action_rows.append(
            f"""
<div class="group flex items-center justify-between p-5 bg-surface-container-lowest rounded-2xl transition-all duration-500 hover:shadow-lg hover:-translate-y-1">
  <div class="flex items-center gap-4 min-w-0">
    <div class="w-14 h-14 rounded-xl overflow-hidden bg-surface-container flex items-center justify-center">{icon_svg}</div>
    <div class="min-w-0">
      <h3 class="font-body font-bold text-on-background truncate">{name_esc}</h3>
      <div class="flex items-center gap-2 text-xs text-on-surface-variant">
        <span class="material-symbols-outlined text-sm text-primary">water_drop</span>
        <span>{action_text}</span>
      </div>
      <div class="text-[11px] text-outline mt-1 truncate">{room_esc} — {action_note}</div>
    </div>
  </div>
  <a href="/api/plants/{plant.id}/log-watered?soil=ok" class="bg-primary-container hover:bg-primary hover:text-on-primary transition-colors p-3 rounded-full flex items-center justify-center" aria-label="Mark done">
    <span class="material-symbols-outlined">check</span>
  </a>
</div>"""
        )

    if not action_rows:
        empty_msg = "No plants yet. Start by adding your first plant." if no_plants else "All plants are happy today."
        action_rows = [
            f"""
<div class="p-6 bg-surface-container-lowest rounded-2xl text-center text-on-surface-variant">
  <p class="font-body">{_esc(empty_msg)}</p>
  <div class="mt-4 flex items-center justify-center gap-3">
    <a href="/add-plant" class="px-5 py-2 rounded-full bg-primary text-on-primary text-sm font-semibold">+ Add plant</a>
    <a href="/library" class="px-5 py-2 rounded-full bg-surface-container-high text-on-surface text-sm font-semibold">Browse library</a>
  </div>
</div>"""
        ]

    added_esc = _esc(added_name or "")
    success_msg = (
        f'<div class="bg-primary-container/70 text-on-primary-container rounded-2xl px-4 py-3 text-sm">Added {added_esc}. It is on your list.</div>'
        if added_name
        else ""
    )
    count = len(actions_with_plants)
    task_label = "task remaining" if count == 1 else "tasks remaining"
    action_html = "\n".join(action_rows)
    current_time = date.today().strftime("%b %d")
    insight_idx = (date.today().toordinal() // 3) % len(GROWTH_INSIGHTS)
    insight_title, insight_text, insight_icon = GROWTH_INSIGHTS[insight_idx]

    return Template(
        """<!DOCTYPE html>
<html class="light" lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <meta name="theme-color" content="#566a4d"/>
  <link rel="manifest" href="/manifest.json">
  <title>Plant Pal — The Living Journal</title>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800&amp;family=Plus+Jakarta+Sans:wght@200..800&amp;display=swap" rel="stylesheet"/>
  <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-25..200&amp;display=swap" rel="stylesheet"/>
  <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
  <script>
    tailwind.config = {
      darkMode: "class",
      theme: {
        extend: {
          colors: {
            "on-background": "#3a391a",
            "primary-container": "#d2eac5",
            "primary-dim": "#4a5e41",
            "outline": "#84825c",
            "on-surface-variant": "#686642",
            "surface-container-lowest": "#ffffff",
            "on-secondary-container": "#6f4a22",
            "surface-tint": "#566a4d",
            "outline-variant": "#bebb91",
            "surface-container-low": "#fffbda",
            "primary": "#566a4d",
            "on-surface": "#3a391a",
            "background": "#fffbff",
            "surface-container": "#f9f5d0",
            "surface-container-highest": "#eeeabd",
            "surface-variant": "#eeeabd",
            "on-primary-container": "#43573b",
            "secondary-container": "#ffdcbd",
            "surface-dim": "#e8e4b8",
            "surface": "#fffbff",
            "surface-bright": "#fffbff",
            "secondary": "#845c32",
            "on-primary": "#ffffff"
          },
          fontFamily: {
            "headline": ["Newsreader", "serif"],
            "body": ["Plus Jakarta Sans", "sans-serif"],
            "label": ["Plus Jakarta Sans", "sans-serif"]
          },
        }
      }
    }
  </script>
  <style>
    .material-symbols-outlined { font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; }
    .glass-panel { backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); }
    .sketchbook-shadow { box-shadow: 0 40px 80px -15px rgba(58,57,26,0.08); }
    .custom-scrollbar::-webkit-scrollbar { width: 4px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #bebb91; border-radius: 10px; }
    body { background-color: #fffbff; color: #3a391a; font-family: 'Plus Jakarta Sans', sans-serif; min-height: max(884px, 100dvh); }
  </style>
</head>
<body class="min-h-screen relative overflow-x-hidden bg-surface-bright">
  <header class="fixed top-0 left-0 right-0 z-50 flex justify-between items-center max-w-2xl mx-auto rounded-full mt-4 mx-4 px-6 py-3 bg-white/80 backdrop-blur-xl shadow-[0_10px_30px_-5px_rgba(58,57,26,0.05)] md:px-8">
    <div class="flex items-center gap-2">
      <span class="material-symbols-outlined text-green-800">water_bottle</span>
      <span class="font-[Newsreader] italic text-xl text-green-900">Plant Pal</span>
    </div>
    <div class="font-[Newsreader] text-sm tracking-tight text-green-800">$current_time</div>
  </header>

  <div class="fixed inset-0 z-0 opacity-40 blur-[2px] md:blur-sm scale-105">
    <img alt="Cozy, sun-drenched lofi kitchen background with soft light and indoor plants" class="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAN5C4M7YEiHuULmiJ1G-U9KHGehH0sflZ9PE25qxT4W5jmtGrG5eQrfHu1LnM0OJTTWRIqr_TX_e6fvEHXiLhKSwPCqDWBE_D7IwG7b5VcrCTUTJuZuBeQxTJgVXCynuenbbiLVzc7TPr2bNI3Dbh6-Oz1ur1mWAhgB_1GgVdkV1KjrXngEZIzT4ZLETmBoSr3010aGJyRTn4_2dS97rge9G3IRkTHXGokWxip3fSeLLDe3_EppEgYbuCTU_tNhA6AZYvkwK7s_4M"/>
  </div>

  <main class="relative z-10 pt-24 pb-40 px-4 md:px-8 max-w-6xl mx-auto flex flex-col items-center">
    <div class="relative w-full flex justify-center mb-[-2rem] animate-pulse">
      <div class="bg-surface-container-low/60 p-4 rounded-full border border-outline-variant/10 shadow-inner">
        <img alt="Saguaro Cactus Illustration" class="w-32 h-32 md:w-40 md:h-40 object-contain drop-shadow-sm" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAcIFcXbor90EbhcfoJZ_WEJcVC01XlPKWtiVNrrSSF73HBC_P0um1op4jPx6LA-m1HoCoTjvs25FhsDX2_phIZLGTHsi3oF7Bx55eW-Q8xw7UWrwGV3Q6BajGS8eEaq0_O5VqC6zfeVdoj0ydv-MnOP3ep9drW8Czsp4ec69-c2daCJ9CgRzZxz2Hhblmurv4yx11DSoZR5lSt3CXeR2aGcgmAtM8DQLIiHSya3j6DaUV9oCT4_Q83xVrG2xUVwFTPmAgZyNbC_fA"/>
      </div>
      
    </div>

    <section class="w-full bg-white/80 backdrop-blur-3xl rounded-[3rem] p-8 md:p-12 sketchbook-shadow border border-white/40 flex flex-col gap-10">
      <div class="flex flex-col md:flex-row justify-between items-start gap-8">
        <div class="flex-1">
          <h1 class="font-[Newsreader] text-5xl md:text-6xl lg:text-7xl text-on-background tracking-tight mb-4 leading-tight">Good morning, Gardener.</h1>
          <p class="font-body text-lg text-on-surface-variant max-w-xl">Your green companions are thriving in today's soft afternoon light. It's a perfect time for some mindful tending.</p>
        </div>
        <div class="bg-surface-container-low rounded-3xl p-6 w-full md:w-64 flex items-center md:flex-col md:items-start gap-4 border border-outline-variant/10 shadow-sm">
          <div class="bg-primary-container p-4 rounded-full text-on-primary-container">
            <span id="greenhouse-icon" class="material-symbols-outlined text-4xl">partly_cloudy_day</span>
          </div>
          <div>
            <div class="text-[10px] md:text-xs uppercase tracking-widest text-on-surface-variant mb-1">Your Greenhouse</div>
            <div class="font-[Newsreader] text-3xl text-on-background"><span id="greenhouse-temp">--</span> <span class="text-base font-body text-outline">— <span id="greenhouse-vibe">finding your local vibe</span></span></div>
          </div>
        </div>
      </div>

      <nav class="flex items-center gap-2 bg-surface-container-highest/30 p-2 rounded-full self-start overflow-x-auto max-w-full">
        <a class="px-8 py-3 rounded-full font-label text-sm font-semibold bg-primary text-on-primary shadow-md transition-all duration-300 whitespace-nowrap" href="/">My Plants</a>
        <a class="px-8 py-3 rounded-full font-label text-sm text-on-surface-variant hover:bg-surface-container-high transition-all duration-300 whitespace-nowrap" href="/library">Plant Library</a>
        <a class="px-8 py-3 rounded-full font-label text-sm text-on-surface-variant hover:bg-surface-container-high transition-all duration-300 whitespace-nowrap" href="/add-plant">+ Add plant</a>
      </nav>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-12">
        <div class="space-y-8">
          $success_msg
          <div class="flex items-center justify-between px-2">
            <h2 class="font-[Newsreader] text-3xl text-on-background">Today's Care</h2>
            <span class="text-sm font-label text-on-surface-variant italic">$count $task_label</span>
          </div>
          <div class="space-y-5 max-h-[420px] overflow-y-auto pr-2 custom-scrollbar">
            $action_html
          </div>
          <div class="bg-primary-container/20 p-8 rounded-[2.5rem] border border-primary/10 relative overflow-hidden shadow-sm group">
            <div class="relative z-10">
              <div class="flex items-center gap-2 mb-4">
                <span class="material-symbols-outlined text-primary text-xl">$insight_icon</span>
                <div class="text-[10px] uppercase font-bold tracking-[0.2em] text-primary-dim">$insight_title</div>
              </div>
              <p class="font-body text-on-surface-variant leading-relaxed">$insight_text</p>
            </div>
            <span class="material-symbols-outlined absolute -bottom-4 -right-4 text-[100px] text-primary/5 group-hover:rotate-12 transition-transform duration-700">nature_people</span>
          </div>
        </div>

        <div class="space-y-8">
          <h2 class="font-[Newsreader] text-3xl text-on-background px-2">Journal Entries</h2>
          <details class="group bg-surface-container-high/40 rounded-[2.5rem] overflow-hidden border border-outline-variant/10 shadow-sm" open>
            <summary class="flex items-center justify-between p-8 cursor-pointer list-none">
              <div class="flex items-center gap-4">
                <span class="material-symbols-outlined text-3xl text-primary">add_circle</span>
                <span class="font-body font-bold text-lg">Adopt New Plant</span>
              </div>
              <span class="material-symbols-outlined transition-transform duration-500 group-open:rotate-180 text-2xl">expand_more</span>
            </summary>
            <div class="px-8 pb-8 space-y-6">
              <form method="post" action="/add-plant" class="space-y-4">
                <input type="hidden" name="next" value="/" />
                <input class="w-full bg-white/60 border-none rounded-2xl py-4 px-6 focus:ring-2 focus:ring-primary text-base font-body" name="display_name" type="text" required placeholder="Display name"/>
                <input class="w-full bg-white/60 border-none rounded-2xl py-4 px-6 focus:ring-2 focus:ring-primary text-base font-body" name="room_name" type="text" required placeholder="Room"/>
                <div class="grid grid-cols-2 gap-3">
                  <input class="w-full bg-white/60 border-none rounded-2xl py-4 px-6 focus:ring-2 focus:ring-primary text-base font-body" name="pot_diameter_inches" type="number" min="1" max="24" value="8"/>
                  <select class="w-full bg-white/60 border-none rounded-2xl py-4 px-6 focus:ring-2 focus:ring-primary text-base font-body" name="light_level">
                    <option value="low">Low light</option>
                    <option value="medium" selected>Medium light</option>
                    <option value="bright">Bright light</option>
                  </select>
                </div>
                <button class="w-full py-5 bg-primary text-on-primary rounded-2xl font-body font-bold text-lg shadow-lg hover:bg-primary-dim hover:shadow-xl transition-all">Register Plant</button>
              </form>
            </div>
          </details>

          <div class="bg-secondary-container/30 p-8 rounded-[2.5rem] border border-secondary/10 relative overflow-hidden shadow-sm group">
            <div class="relative z-10">
              <div class="text-[10px] uppercase font-bold tracking-[0.2em] text-on-surface-variant mb-4">Weekly Note</div>
              <p class="font-[Newsreader] italic text-2xl md:text-3xl text-on-secondary-container leading-relaxed">"Keep rotating your plants weekly for even growth and healthier stems."</p>
            </div>
            <span class="material-symbols-outlined absolute -bottom-8 -right-8 text-[160px] text-secondary/5 group-hover:scale-110 transition-transform duration-1000">edit_note</span>
          </div>
        </div>
      </div>
    </section>

    
  </main>

  <footer class="fixed bottom-0 left-0 w-full z-50 flex justify-around items-center px-8 pb-10 pt-5 bg-white/90 backdrop-blur-3xl shadow-[0_-20px_60px_-10px_rgba(58,57,26,0.06)] rounded-t-[3rem]">
    <a class="flex flex-col items-center justify-center text-stone-400 hover:text-green-700 transition-all duration-300 group" href="/library">
      <span class="material-symbols-outlined text-3xl group-hover:scale-110 transition-transform">library_books</span>
      <span class="text-[10px] md:text-xs uppercase tracking-widest mt-2">Library</span>
    </a>
    <a class="flex flex-col items-center justify-center bg-green-100 text-green-900 rounded-full px-8 py-3 scale-110 md:scale-125 shadow-inner" href="/">
      <span class="material-symbols-outlined text-3xl">potted_plant</span>
      <span class="text-[10px] uppercase tracking-widest mt-1 font-bold">My Plants</span>
    </a>
    <a class="flex flex-col items-center justify-center text-stone-400 hover:text-green-700 transition-all duration-300 group" href="/add-plant">
      <span class="material-symbols-outlined text-3xl group-hover:scale-110 transition-transform">add_circle</span>
      <span class="text-[10px] md:text-xs uppercase tracking-widest mt-2">Add Plant</span>
    </a>
  </footer>

  <script>{_COZY_CLOCK_JS}</script>
  <script>
    (function() {
      var tempEl = document.getElementById('greenhouse-temp');
      var vibeEl = document.getElementById('greenhouse-vibe');
      var iconEl = document.getElementById('greenhouse-icon');
      if (!tempEl || !vibeEl || !iconEl) return;

      function iconFor(code) {
        if (code === 0) return 'wb_sunny';
        if (code <= 3) return 'partly_cloudy_day';
        if (code <= 48) return 'foggy';
        if (code <= 67) return 'rainy';
        if (code <= 77) return 'ac_unit';
        if (code <= 82) return 'rainy';
        if (code <= 86) return 'ac_unit';
        return 'thunderstorm';
      }

      function vibeFrom(tempF, humidity, code) {
        if (humidity >= 80) return 'humid and lush';
        if (code === 0 && tempF >= 75) return 'lots of sun lately';
        if (code <= 3) return 'bright but gentle light';
        if (code <= 67) return 'rain-kissed and cozy';
        if (tempF <= 45) return 'cool and restful';
        return 'steady growing weather';
      }

      function updateWeather(lat, lon) {
        var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + encodeURIComponent(lat) +
          '&longitude=' + encodeURIComponent(lon) +
          '&current=temperature_2m,relative_humidity_2m,weather_code&temperature_unit=fahrenheit';
        fetch(url).then(function(r) { return r.json(); }).then(function(d) {
          var c = d && d.current ? d.current : null;
          if (!c) throw new Error('No weather data');
          var temp = Math.round(c.temperature_2m || 0);
          var humidity = Number(c.relative_humidity_2m || 0);
          var code = Number(c.weather_code || 0);
          tempEl.textContent = temp + '°F';
          vibeEl.textContent = vibeFrom(temp, humidity, code);
          iconEl.textContent = iconFor(code);
        }).catch(function() {
          tempEl.textContent = '--';
          vibeEl.textContent = 'weather unavailable';
          iconEl.textContent = 'partly_cloudy_day';
        });
      }

      if (!navigator.geolocation) {
        vibeEl.textContent = 'location unavailable';
        return;
      }
      navigator.geolocation.getCurrentPosition(
        function(pos) { updateWeather(pos.coords.latitude, pos.coords.longitude); },
        function() { vibeEl.textContent = 'enable location for local weather'; },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 }
      );
    })();

    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
  </script>
</body>
</html>
"""
    ).substitute(
        current_time=current_time,
        now_str=now_str,
        success_msg=success_msg,
        count=count,
        task_label=task_label,
        action_html=action_html,
        insight_title=insight_title,
        insight_text=insight_text,
        insight_icon=insight_icon,
    )


@app.get("/", response_class=HTMLResponse)
def today_panel(added: Optional[str] = None, name: Optional[str] = None) -> HTMLResponse:
    init_db()
    ensure_seeded()
    plants = get_plants()
    no_plants = len(plants) == 0
    actions_with_plants = get_todays_actions()
    added_name = (name or "").strip() if added else None
    html = _render_panel(actions_with_plants, no_plants=no_plants, added_name=added_name)
    return HTMLResponse(html)


# ---------- Add Plant page ----------

@app.get("/add-plant", response_class=HTMLResponse)
def add_plant_page() -> HTMLResponse:
    """Add Plant form: preset dropdown + custom fields."""
    init_db()
    ensure_seeded()
    html = f"""<!DOCTYPE html>
<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Plant Pal - Add New Plant</title>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800&amp;family=Plus+Jakarta+Sans:ital,wght@0,200..800;1,200..800&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script id="tailwind-config">
tailwind.config = {{
  darkMode: "class",
  theme: {{
    extend: {{
      colors: {{
        "on-primary-fixed": "#31442a", "inverse-primary": "#e6fed8", "on-secondary-fixed": "#5a3811", "on-secondary": "#ffffff",
        "outline": "#84825c", "secondary-fixed-dim": "#ffca98", "tertiary-dim": "#565b3f", "surface-container-high": "#f3efc8",
        "on-error-container": "#6e1400", "primary-dim": "#4a5e41", "secondary": "#845c32", "on-tertiary-container": "#5b6044",
        "on-primary-fixed-variant": "#4d6144", "error-dim": "#791903", "background": "#fffbff", "secondary-container": "#ffdcbd",
        "inverse-on-surface": "#a09e87", "surface-container": "#f9f5d0", "on-primary": "#ffffff", "secondary-fixed": "#ffdcbd",
        "on-tertiary-fixed": "#494e33", "on-secondary-fixed-variant": "#7a532a", "surface": "#fffbff", "primary-fixed": "#d2eac5",
        "primary-container": "#d2eac5", "primary-fixed-dim": "#c4dbb7", "surface-tint": "#566a4d", "primary": "#566a4d",
        "on-surface": "#3a391a", "error": "#ae4025", "surface-container-low": "#fffbda", "surface-container-lowest": "#ffffff",
        "surface-container-highest": "#eeeabd", "on-tertiary": "#ffffff", "tertiary-fixed-dim": "#e7ebc7", "tertiary": "#62674a",
        "surface-bright": "#fffbff", "surface-variant": "#eeeabd", "tertiary-fixed": "#f6fad5", "on-error": "#ffffff",
        "on-primary-container": "#43573b", "secondary-dim": "#765028", "on-background": "#3a391a", "outline-variant": "#bebb91",
        "error-container": "#fd795a", "tertiary-container": "#f6fad5", "on-tertiary-fixed-variant": "#666a4e",
        "on-surface-variant": "#686642", "inverse-surface": "#0f0f03", "on-secondary-container": "#6f4a22", "surface-dim": "#e8e4b8"
      }},
      fontFamily: {{
        "headline": ["Newsreader", "serif"],
        "body": ["Plus Jakarta Sans", "sans-serif"],
        "label": ["Plus Jakarta Sans", "sans-serif"]
      }},
      borderRadius: {{"DEFAULT": "0.25rem", "lg": "0.5rem", "xl": "0.75rem", "full": "9999px"}}
    }}
  }}
}}
</script>
<style>
.glass-panel {{ background: rgba(255, 251, 255, 0.75); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); }}
.material-symbols-outlined {{ font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; }}
.font-serif-italic {{ font-family: 'Newsreader', serif; font-style: italic; }}
.sketch-border {{ border: 2px dashed #bebb91; }}
#species-results:empty {{ display: none; }}
.species-hit {{ padding: 0.65rem 0.8rem; min-height: 44px; cursor: pointer; font-size: 0.9rem; display: flex; align-items: center; gap: 0.5rem; margin: 0.35rem; border-radius: 0.75rem; background: rgba(255,255,255,0.65); }}
.species-hit:hover {{ background: #f5f3ef; }}
.species-hit-icon svg {{ width: 22px; height: 22px; }}
.species-loading, .species-empty, .selected-species {{ font-size: 0.85rem; color: #686642; margin-top: 0.5rem; }}
.selected-species {{ display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }}
.selected-species-icon svg {{ width: 22px; height: 22px; }}
.env-chip.active {{ background: #d2eac5; color: #43573b; font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }}
</style>
</head>
<body class="bg-background text-on-surface font-body min-h-screen relative overflow-x-hidden">
<div class="fixed inset-0 z-0">
  <img alt="Sun-drenched kitchen" class="w-full h-full object-cover opacity-40 blur-sm" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCH24_9fzYSTEb4F4RT_QtvCMHdHMjfsg9NgM3TQCh9APj-I9iBNJCDKuQrH2JdEvk7LnVo8rvzyfYyt9BCsdT4OlJ_zGDgGfKekpqSWMPXlTRVJ1a5CDz7dAZUHBFah8IA51PALEjMC6x_LA8rIEm1ljNygNSWMFJp0dpa-SHnmOO4zKQP0tyDAdI7HeSs--1UdfwjeuMu4QuJYrFZd9CUwHMCsygCcKp8FdrOvLvnB4Q53lWmzWsjFUYpH85TGuu551paQyoYYio"/>
</div>
<header class="bg-stone-50/80 backdrop-blur-md shadow-sm fixed top-0 left-0 w-full z-50">
  <div class="flex justify-between items-center w-full px-8 py-4 max-w-full">
    <div class="font-serif text-2xl italic tracking-tight text-emerald-900">Plant Pal</div>
    <nav class="hidden md:flex items-center space-x-8">
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/">Home</a>
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/library">Library</a>
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/plants">My Plants</a>
      <a class="text-emerald-900 font-semibold border-b-2 border-emerald-900 transition-all" href="/add-plant">Add Plant</a>
    </nav>
    <div class="flex items-center space-x-4">
      <span class="text-sm font-medium text-on-surface-variant hidden sm:inline" id="add-clock">--:--</span>
      <button class="text-stone-600 hover:bg-stone-200/50 p-2 rounded-full transition-colors" type="button" aria-label="Time">
        <span class="material-symbols-outlined">schedule</span>
      </button>
      <button class="text-stone-600 hover:bg-stone-200/50 p-2 rounded-full transition-colors" type="button" aria-label="Account">
        <span class="material-symbols-outlined">account_circle</span>
      </button>
    </div>
  </div>
</header>
<main class="relative z-10 pt-28 pb-32 px-6 flex justify-center">
  <div class="glass-panel w-full max-w-3xl rounded-[2rem] p-10 md:p-14 shadow-2xl shadow-on-surface/5 border border-white/40">
    <div class="mb-12 text-center relative">
      <div class="w-24 h-24 mb-6 mx-auto rounded-full bg-surface-container-high flex items-center justify-center relative">
        <img class="w-16 h-16 object-contain" alt="Seedling illustration" src="https://lh3.googleusercontent.com/aida-public/AB6AXuC0djAF71h7oBHOJPtCT7lxUWAayQk12X7_uEOCDmKOSp6cuwMgjWoZDBYnjJSjFo1IR27v1NWAQHRxJTJzIxCD4yb_v0-afXe9TD2Uf85SyUzHLAFomGPUYaxm7nyvl1G_G-geS2yviVkW9qDbAJL2xa6M1I0YnALmp2UgbS1Mu-mb36JqQAmQfkYBrkj4iqHsZPMzXcRLhwyLUDpRgFMnM0oRWRl6dSiQkFGRLToVjivEGSKuJcgU_SwvhxSWVsPqDUvmxMB3NkY"/>
        <div class="absolute inset-0 border-2 border-dashed border-outline-variant/30 rounded-full scale-110"></div>
      </div>
      <h1 class="font-headline text-5xl md:text-6xl text-primary italic mb-3">New Companion</h1>
      <p class="text-on-surface-variant font-body text-lg">Documenting a new journey of growth.</p>
    </div>
    <form class="space-y-10" method="post" action="/add-plant">
      <input type="hidden" name="template_id" id="template_id" value="" />
      <input type="hidden" name="pot_material" value="plastic" />
      <input type="hidden" name="next" value="/plants" />
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div class="flex flex-col gap-2">
          <label class="label-md font-medium text-on-surface-variant ml-1" for="display_name">What's their name?</label>
          <input class="w-full h-14 px-6 bg-surface-container-highest rounded-xl border-none focus:ring-2 focus:ring-primary focus:bg-surface-bright transition-all placeholder:text-outline/50" id="display_name" name="display_name" placeholder="e.g. Monty" type="text" required/>
        </div>
        <div class="flex flex-col gap-2 relative">
          <label class="label-md font-medium text-on-surface-variant ml-1" for="species">Search species...</label>
          <div class="relative">
            <input class="w-full h-14 pl-12 pr-6 bg-surface-container-highest rounded-xl border-none focus:ring-2 focus:ring-primary focus:bg-surface-bright transition-all placeholder:text-outline/50" id="species" name="species" placeholder="Monstera Deliciosa..." type="text" autocomplete="off"/>
            <span class="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant">search</span>
          </div>
          <div class="selected-species" id="selected-species" style="display:none;"></div>
          <div id="species-results"></div>
        </div>
      </div>
      <div class="flex flex-col gap-4">
        <span class="label-md font-medium text-on-surface-variant ml-1">Environment</span>
        <div class="flex flex-wrap gap-3">
          <button class="env-chip active px-6 py-2 rounded-full bg-surface-container-high text-on-surface-variant hover:bg-primary-container hover:text-on-primary-container transition-all" type="button" data-env="">All</button>
          <button class="env-chip px-6 py-2 rounded-full bg-surface-container-high text-on-surface-variant hover:bg-primary-container hover:text-on-primary-container transition-all" type="button" data-env="indoor">Indoor</button>
          <button class="env-chip px-6 py-2 rounded-full bg-surface-container-high text-on-surface-variant hover:bg-primary-container hover:text-on-primary-container transition-all" type="button" data-env="outdoor">Outdoor</button>
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
        <div class="flex flex-col gap-2">
          <label class="label-md font-medium text-on-surface-variant ml-1" for="room_name">Home Location</label>
          <select class="w-full h-14 px-6 bg-surface-container-highest rounded-xl border-none focus:ring-2 focus:ring-primary focus:bg-surface-bright transition-all appearance-none cursor-pointer" id="room_name" name="room_name" required>
            <option value="Living Room">Living Room</option>
            <option value="Kitchen Sill">Kitchen Sill</option>
            <option value="Bedroom Corner">Bedroom Corner</option>
            <option value="Back Terrace">Back Terrace</option>
          </select>
        </div>
        <div class="flex flex-col gap-2">
          <label class="label-md font-medium text-on-surface-variant ml-1" for="light_level">Light level</label>
          <select class="w-full h-14 px-6 bg-surface-container-highest rounded-xl border-none focus:ring-2 focus:ring-primary focus:bg-surface-bright transition-all appearance-none cursor-pointer" id="light_level" name="light_level">
            <option value="bright">Direct Sunlight</option>
            <option value="medium" selected>Bright Indirect</option>
            <option value="low">Low Light</option>
            <option value="low">Full Shade</option>
          </select>
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <label class="label-md font-medium text-on-surface-variant ml-1" for="pot_diameter_inches">Pot diameter (inches)</label>
        <input class="w-full h-14 px-6 bg-surface-container-highest rounded-xl border-none focus:ring-2 focus:ring-primary focus:bg-surface-bright transition-all placeholder:text-outline/50" id="pot_diameter_inches" name="pot_diameter_inches" placeholder="e.g. 6" type="number" value="8" min="1" max="24"/>
      </div>
      <div class="pt-10 flex justify-center">
        <button class="w-full md:w-auto px-12 py-4 bg-primary text-on-primary rounded-full text-lg font-medium shadow-xl shadow-primary/20 hover:bg-primary-dim hover:-translate-y-1 transition-all duration-300" type="submit">Welcome Home</button>
      </div>
    </form>
    <div class="mt-16 pt-8 border-t border-outline-variant/15 text-center">
      <p class="font-serif italic text-tertiary text-sm">"Every leaf speaks bliss to me, fluttering from the autumn tree." — Emily Bronte</p>
    </div>
  </div>
</main>
<nav class="md:hidden fixed bottom-0 left-0 w-full flex justify-around items-center px-6 pb-6 pt-3 bg-stone-50/80 backdrop-blur-lg border-t border-stone-200/20 shadow-[0_-4px_20px_rgba(0,0,0,0.05)] z-50">
  <a class="flex flex-col items-center justify-center text-stone-500 px-4 py-2 hover:text-emerald-700" href="/">
    <span class="material-symbols-outlined">home</span>
    <span class="text-xs font-medium mt-1">Home</span>
  </a>
  <a class="flex flex-col items-center justify-center text-stone-500 px-6 py-2 hover:text-emerald-700" href="/library">
    <span class="material-symbols-outlined">local_library</span>
    <span class="text-xs font-medium mt-1">Library</span>
  </a>
  <a class="flex flex-col items-center justify-center text-stone-500 px-6 py-2 hover:text-emerald-700" href="/plants">
    <span class="material-symbols-outlined">potted_plant</span>
    <span class="text-xs font-medium mt-1">My Plants</span>
  </a>
  <a class="flex flex-col items-center justify-center bg-emerald-100/50 text-emerald-900 rounded-xl px-6 py-2 transition-all scale-90 duration-200" href="/add-plant">
    <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">add_circle</span>
    <span class="text-xs font-medium mt-1">Add Plant</span>
  </a>
</nav>
<div class="fixed top-1/4 -left-20 w-64 h-64 bg-primary-container/20 rounded-full blur-[100px] pointer-events-none"></div>
<div class="fixed bottom-1/4 -right-20 w-80 h-80 bg-secondary-container/20 rounded-full blur-[120px] pointer-events-none"></div>
<script>
(function() {{
  var clockEl = document.getElementById('add-clock');
  function tick() {{
    if (!clockEl) return;
    var now = new Date();
    var h = now.getHours();
    var m = now.getMinutes();
    var h12 = h % 12 || 12;
    clockEl.textContent = h12 + ':' + (m < 10 ? '0' : '') + m + (h < 12 ? ' AM' : ' PM');
  }}
  tick();
  setInterval(tick, 60000);

  var speciesEl = document.getElementById('species');
  var templateIdEl = document.getElementById('template_id');
  var resultsEl = document.getElementById('species-results');
  var selectedEl = document.getElementById('selected-species');
  var debounce = null;

  speciesEl.addEventListener('input', function() {{
    var q = speciesEl.value.trim();
    if (debounce) clearTimeout(debounce);
    if (!q) {{ resultsEl.innerHTML = ''; return; }}
    resultsEl.innerHTML = '<p class="species-loading">Searching...</p>';
    debounce = setTimeout(function() {{
      var envBtn = document.querySelector('.env-chip.active');
      var env = envBtn && envBtn.getAttribute('data-env') ? '&environment=' + encodeURIComponent(envBtn.getAttribute('data-env')) : '';
      fetch('/api/templates/search?q=' + encodeURIComponent(q) + env)
        .then(function(r) {{ return r.json(); }})
        .then(function(list) {{
          resultsEl.innerHTML = '';
          if (!list || list.length === 0) {{
            resultsEl.innerHTML = '<p class="species-empty">No plants match. Try another name or filter.</p>';
            return;
          }}
          list.forEach(function(t) {{
            var div = document.createElement('div');
            div.className = 'species-hit';
            div.innerHTML = '<span class="species-hit-icon">' + (t.icon_svg || '') + '</span><span>' + (t.name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>';
            div.addEventListener('click', function() {{
              templateIdEl.value = t.id;
              selectedEl.innerHTML = '<span class="selected-species-icon">' + (t.icon_svg || '') + '</span><span>Selected: ' + (t.name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>';
              selectedEl.style.display = 'flex';
              resultsEl.innerHTML = '';
              speciesEl.value = t.name || '';
            }});
            resultsEl.appendChild(div);
          }});
        }});
    }}, 220);
  }});

  document.querySelectorAll('.env-chip').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      document.querySelectorAll('.env-chip').forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      if (speciesEl.value.trim()) speciesEl.dispatchEvent(new Event('input'));
    }});
  }});
}})();
</script>
</body></html>"""
    return HTMLResponse(html)


@app.get("/library", response_class=HTMLResponse)
def plant_library_page(environment: Optional[str] = None, q: Optional[str] = None) -> HTMLResponse:
    """Plant Library: browse by category. Filter with ?environment=indoor|outdoor. Search with ?q=."""
    init_db()
    ensure_seeded()
    env_filter = environment if environment in ("indoor", "outdoor") else None
    search_query = (q or "").strip()
    if search_query:
        templates = search_templates(search_query, limit=500, environment=env_filter)
    else:
        templates = get_templates(environment=env_filter)
    # Group by category (empty -> "Other")
    from collections import defaultdict
    by_cat = defaultdict(list)
    for t in templates:
        cat = getattr(t, "category", "") or "Other"
        by_cat[cat].append(t)
    # Order categories: Herbs & Spices, Fruits & Vegetables first, then alphabetically
    priority = ("Herbs & Spices", "Fruits & Vegetables", "Foliage", "Flowering Houseplants", "Succulents & Cacti",
                "Ferns", "Palms", "Bonsai", "Trailing & Vines", "Easy Care", "Flowering Perennials", "Shrubs", "Trees",
                "Annuals", "Bulbs", "Drought / Xeriscape", "Groundcovers", "Ornamental Grasses", "Other")
    cat_order = [c for c in priority if c in by_cat]
    for c in sorted(by_cat.keys()):
        if c not in cat_order:
            cat_order.append(c)
    sections = []
    for cat in cat_order:
        plants = by_cat[cat]
        rows = []
        for t in plants:
            desc_esc = (t.description or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            grow_esc = (getattr(t, "growing_instructions", "") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            env_badge = "Indoor" if getattr(t, "environment", "indoor") == "indoor" else "Outdoor"
            badge_cls = "lib-badge lib-badge-indoor" if env_badge == "Indoor" else "lib-badge lib-badge-outdoor"
            grow_block = f'<p class="lib-growing">{grow_esc}</p>' if grow_esc else ""
            icon_svg = get_icon_svg(getattr(t, "icon_id", None) or t.slug)
            search_text = " ".join([t.name or "", t.description or "", getattr(t, "growing_instructions", "") or ""]).replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")[:500]
            name_attr = (t.name or "").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
            rows.append(
                f"""
                <div class="lib-row" data-name="{name_attr}" data-search="{search_text}">
                    <span class="lib-icon">{icon_svg}</span>
                    <div class="lib-info">
                        <span class="lib-name">{t.name} <span class="{badge_cls}">{env_badge}</span></span>
                        <span class="lib-meta">Water: {t.watering_frequency_display or "—"} · Light: {t.light_display or "—"}</span>
                        <p class="lib-desc">{desc_esc}</p>
                        {grow_block}
                    </div>
                </div>"""
            )
        block_html = f'<div class="lib-category-block" data-category="{cat.replace(chr(34), "&quot;")}"><h2 class="lib-category">{cat}</h2>' + "\n".join(rows) + "</div>"
        sections.append(block_html)
    if not sections and search_query:
        content = f'<p class="empty lib-empty-search">No plants match “{search_query.replace(chr(34), "&quot;")}”. Try different words or <a href="/library' + ('?environment=' + env_filter if env_filter else '') + '">browse all</a>.</p>'
    elif not sections:
        content = '<p class="empty">No plants in library yet.</p>'
    else:
        content = "\n".join(sections)
    from urllib.parse import quote
    base = "/library"
    all_href = base if not search_query else base + "?q=" + quote(search_query)
    indoor_href = base + "?environment=indoor" + ("&q=" + quote(search_query) if search_query else "")
    outdoor_href = base + "?environment=outdoor" + ("&q=" + quote(search_query) if search_query else "")
    clear_href = base if not env_filter else base + "?environment=" + env_filter
    filter_links = f'<p class="lib-filter">Show: <a href="{all_href}">All</a> · <a href="{indoor_href}">Indoor</a> · <a href="{outdoor_href}">Outdoor</a></p>'
    search_value_esc = search_query.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    env_hidden = f'<input type="hidden" name="environment" value="{env_filter or ""}"/>' if env_filter else ""
    insight_idx = (date.today().toordinal() // 3) % len(GROWTH_INSIGHTS)
    insight_title, insight_text, insight_icon = GROWTH_INSIGHTS[insight_idx]
    html = f"""<!DOCTYPE html>
<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800&amp;family=Plus+Jakarta+Sans:wght@200..800&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script>
tailwind.config = {{
  darkMode: "class",
  theme: {{
    extend: {{
      colors: {{
        "on-surface": "#3a391a", "primary": "#566a4d", "primary-container": "#d2eac5",
        "surface-container-lowest": "#ffffff", "surface-container": "#f9f5d0", "surface-container-highest": "#eeeabd",
        "surface-container-low": "#fffbda", "on-surface-variant": "#686642", "outline-variant": "#bebb91",
        "secondary-container": "#ffdcbd", "tertiary-container": "#f6fad5", "on-tertiary-container": "#5b6044"
      }},
      fontFamily: {{
        "headline": ["Newsreader", "serif"],
        "body": ["Plus Jakarta Sans", "sans-serif"]
      }}
    }}
  }}
}};
</script>
<style>
.glass-panel {{ background: rgba(255, 251, 255, 0.65); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px) }}
.material-symbols-outlined {{ font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 }}
.bg-lofi-kitchen {{ background-image: url(https://lh3.googleusercontent.com/aida-public/AB6AXuCLxyI9Lz4F2MPW8GDCCPTFgsdrlj0q_2cMPz0z5Fg6ZoTQd92VTMThpCbHLrIo47nb5DHY-hSFuK_ByRHGKWjJA6EamIDLNTjuq5F9CGiQhYSSIUIIBCCxLkLDsWfMUij568DkWiIgOW196n2RjvMS-VJh2urlor39qrOJndiPKFZIINyV_3RepRMp2H_F3SMu8ml9jUYTB88e7N6xQkbmyJ_tgNVdGGAhBRd7vdxNIjkr6RbS5dmaqJvc4fcRBT43HMfjwVEmQP8); background-size: cover; background-position: center }}
.lib-category {{ font-family: "Newsreader", serif; font-size: 2rem; color: #566a4d; margin: 1.2rem 0 1rem; }}
.lib-category-block {{ margin-bottom: 1.2rem; }}
.lib-row {{ background: rgba(255,255,255,0.55); border: 1px solid rgba(255,255,255,0.2); border-radius: 1.6rem; padding: 1rem; display: flex; gap: 1rem; transition: all .5s; }}
.lib-row:hover {{ background: rgba(255,255,255,0.75); transform: translateY(-2px); box-shadow: 0 10px 28px rgba(58,57,26,0.08); }}
.lib-icon {{ width: 4rem; height: 4rem; border-radius: 1rem; overflow: hidden; background: #f9f5d0; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
.lib-icon svg {{ width: 2rem; height: 2rem; }}
.lib-name {{ font-weight: 700; font-size: 1.25rem; color: #3a391a; }}
.lib-badge {{ padding: 0.15rem 0.55rem; border-radius: 999px; font-size: .64rem; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; margin-left: .45rem; }}
.lib-badge-indoor {{ background: #f9f5d0; color: #62674a; }}
.lib-badge-outdoor {{ background: #d2eac5; color: #43573b; }}
.lib-meta {{ display:block; margin-top:.2rem; font-size:.78rem; color:#686642; }}
.lib-desc {{ margin-top:.45rem; font-size:.9rem; color:#3a391a; line-height:1.4; }}
.lib-growing {{ margin-top:.6rem; padding:.7rem .8rem; border-radius:.9rem; background:#f6fad5; color:#5b6044; font-size:.82rem; }}
.lib-row-hidden {{ display:none !important; }}
</style>
</head>
<body class="bg-stone-100 font-body text-on-surface min-h-screen relative overflow-x-hidden">
<div class="fixed inset-0 z-0 bg-lofi-kitchen"><div class="absolute inset-0 bg-white/10 backdrop-contrast-75"></div></div>
<header class="bg-stone-50/80 backdrop-blur-md shadow-sm fixed top-0 left-0 w-full z-50">
  <div class="flex justify-between items-center w-full px-8 py-4 max-w-full">
    <div class="font-serif text-2xl italic tracking-tight text-emerald-900">Plant Pal</div>
    <nav class="hidden md:flex items-center space-x-8">
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/">Home</a>
      <a class="text-emerald-900 font-semibold border-b-2 border-emerald-900 transition-all" href="/library">Library</a>
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/plants">My Plants</a>
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/add-plant">Add Plant</a>
    </nav>
    <div class="flex items-center space-x-4">
      <div class="relative hidden sm:block">
        <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-stone-400">search</span>
        <input id="lib-search-top" class="pl-10 pr-4 py-2 bg-stone-100 border-none rounded-full text-sm focus:ring-2 focus:ring-primary/20 w-64" placeholder="Search species..." type="text"/>
      </div>
      <button class="material-symbols-outlined text-stone-600 hover:bg-stone-200/50 p-2 rounded-full transition-colors">account_circle</button>
    </div>
  </div>
</header>
<main class="relative z-10 pt-28 pb-32 px-6 md:px-12 lg:px-24 min-h-screen flex items-start justify-center">
  <div class="glass-panel w-full max-w-6xl rounded-[2.5rem] shadow-2xl p-8 md:p-12 border border-white/30" id="main">
    <div class="mb-12 space-y-6">
      <h1 class="font-headline italic text-5xl md:text-6xl text-on-surface tracking-tight">Plant Library</h1>
      <p class="font-body text-lg text-on-surface-variant max-w-2xl leading-relaxed">Explore our curated collection of botanical wonders. From hardy succulents to dramatic tropicals, find the perfect companion for your space.</p>
      <div class="relative group max-w-2xl">
        <form action="/library" method="get" role="search">
          {env_hidden}
          <div class="absolute inset-y-0 left-0 pl-6 flex items-center pointer-events-none">
            <span class="material-symbols-outlined text-primary text-2xl">search</span>
          </div>
          <input id="lib-search" class="block w-full pl-16 pr-6 py-5 bg-surface-container-highest/50 border-none rounded-full text-on-surface placeholder-on-surface-variant/60 focus:ring-2 focus:ring-primary/30 transition-all text-lg" placeholder="Search by name, light, or care level..." type="text" name="q" value="{search_value_esc}" />
        </form>
      </div>
    </div>
    <div class="flex flex-wrap gap-3 mb-10">
      <a href="{all_href}" class="px-6 py-2 rounded-full {'bg-primary-container text-on-primary-container' if not env_filter else 'bg-surface-container-high text-on-surface'} font-medium text-sm transition-all shadow-sm">All Species</a>
      <a href="{indoor_href}" class="px-6 py-2 rounded-full {'bg-primary-container text-on-primary-container' if env_filter == 'indoor' else 'bg-surface-container-high text-on-surface'} text-sm">Indoor</a>
      <a href="{outdoor_href}" class="px-6 py-2 rounded-full {'bg-primary-container text-on-primary-container' if env_filter == 'outdoor' else 'bg-surface-container-high text-on-surface'} text-sm">Outdoor</a>
      <a href="{base + ('?q=' + __import__('urllib.parse').parse.quote(search_query) if search_query else '')}" class="px-6 py-2 rounded-full bg-surface-container-high text-on-surface text-sm">Reset</a>
    </div>
    <div id="lib-content" class="grid grid-cols-1 gap-8">{content}</div>
  </div>
</main>
<nav class="md:hidden fixed bottom-0 left-0 w-full flex justify-around items-center px-6 pb-6 pt-3 bg-stone-50/80 backdrop-blur-lg border-t border-stone-200/20 shadow-[0_-4px_20px_rgba(0,0,0,0.05)] z-50">
  <a class="flex flex-col items-center justify-center text-stone-500 px-4 py-2 hover:text-emerald-700" href="/">
    <span class="material-symbols-outlined">home</span>
    <span class="text-xs font-medium mt-1">Home</span>
  </a>
  <a class="flex flex-col items-center justify-center bg-emerald-100/50 text-emerald-900 rounded-xl px-6 py-2 transition-all scale-90 duration-200" href="/library">
    <span class="material-symbols-outlined">local_library</span>
    <span class="text-xs font-medium mt-1">Library</span>
  </a>
  <a class="flex flex-col items-center justify-center text-stone-500 px-6 py-2 hover:text-emerald-700" href="/plants">
    <span class="material-symbols-outlined">potted_plant</span>
    <span class="text-xs font-medium mt-1">My Plants</span>
  </a>
  <a class="flex flex-col items-center justify-center text-stone-500 px-6 py-2 hover:text-emerald-700" href="/add-plant">
    <span class="material-symbols-outlined">add_circle</span>
    <span class="text-xs font-medium mt-1">Add Plant</span>
  </a>
</nav>
<a href="/add-plant" class="fixed bottom-24 right-8 md:bottom-12 md:right-12 w-16 h-16 rounded-full bg-primary text-white flex items-center justify-center shadow-2xl hover:bg-primary-dim active:scale-95 transition-all z-40">
  <span class="material-symbols-outlined text-3xl">add</span>
</a>
<script>
(function() {{
  var searchEl = document.getElementById('lib-search');
  var topEl = document.getElementById('lib-search-top');
  if (topEl && searchEl) {{
    topEl.value = searchEl.value || '';
    topEl.addEventListener('input', function() {{ searchEl.value = topEl.value; liveFilter(); }});
    searchEl.addEventListener('input', function() {{ topEl.value = searchEl.value; }});
  }}
  function liveFilter() {{
    if (!searchEl) return;
    var q = (searchEl.value || '').trim().toLowerCase();
    var blocks = document.querySelectorAll('.lib-category-block');
    blocks.forEach(function(block) {{
      var rows = block.querySelectorAll('.lib-row');
      var visible = 0;
      rows.forEach(function(row) {{
        var text = (row.getAttribute('data-search') || '').toLowerCase();
        var show = !q || text.indexOf(q) !== -1;
        if (show) {{ row.classList.remove('lib-row-hidden'); visible++; }}
        else {{ row.classList.add('lib-row-hidden'); }}
      }});
      block.style.display = visible > 0 ? '' : 'none';
    }});
  }}
  if (searchEl) {{
    searchEl.addEventListener('input', liveFilter);
    searchEl.addEventListener('keyup', liveFilter);
  }}
}})();
</script>
</body></html>"""
    return HTMLResponse(html)


@app.get("/plants", response_class=HTMLResponse)
def my_plants_page(sort: Optional[str] = None, added: Optional[str] = None, name: Optional[str] = None) -> HTMLResponse:
    """My Plants: list all plants with due date, streak, badges, remove. Sort: due (default), room, name."""
    init_db()
    ensure_seeded()
    plants = get_plants()
    today = date.today()

    def _esc(value: str) -> str:
        return (
            (value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    if sort == "room":
        plants = sorted(plants, key=lambda p: (p.room_name.lower(), p.display_name.lower()))
    elif sort == "name":
        plants = sorted(plants, key=lambda p: p.display_name.lower())
    else:
        def due_sort_key(p):
            due = predicted_dry_date(p, today)
            return (due or date.max, p.display_name.lower())
        plants = sorted(plants, key=due_sort_key)

    added_name = (name or "").strip() if added else None
    cards = []
    for p in plants:
        due = predicted_dry_date(p, today)
        if due is None:
            due_text = "No schedule"
            due_class = "text-outline"
        elif due < today:
            due_text = "Overdue"
            due_class = "text-error"
        elif due == today:
            due_text = "Due today"
            due_class = "text-primary"
        else:
            days = (due - today).days
            due_text = f"Due in {days} day" + ("s" if days != 1 else "")
            due_class = "text-primary"

        env = getattr(p.template, "environment", "indoor") if p.template else "indoor"
        env_badge = "Indoor" if env == "indoor" else "Outdoor"
        icon_svg = get_icon_svg(p.get_icon_id())
        display_name = _esc(p.display_name)
        room_name = _esc(p.room_name)
        best = p.longest_streak
        streak = p.current_streak
        badges = sorted(p.badges_earned)[:3]
        badge_icons = []
        for b in badges:
            title = _esc(b.replace("_", " ").title())
            badge_icons.append(
                f'<div class="w-8 h-8 rounded-full bg-tertiary-container flex items-center justify-center border-2 border-surface-container-lowest" title="{title}"><span class="material-symbols-outlined text-xs text-tertiary fill-icon" style="font-variation-settings: \'FILL\' 1;">eco</span></div>'
            )
        badge_html = "".join(badge_icons) or '<div class="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center border-2 border-surface-container-lowest" title="Getting Started"><span class="material-symbols-outlined text-xs text-secondary fill-icon" style="font-variation-settings: \'FILL\' 1;">eco</span></div>'

        watering_box_class = "bg-surface-container-low"
        watering_label_class = "text-on-surface-variant"
        if due_class == "text-error":
            watering_box_class = "bg-error-container/10"
            watering_label_class = "text-error"
        env_badge_bg = "bg-primary-container text-on-primary-container" if env_badge == "Indoor" else "bg-secondary-container text-on-secondary-container"

        cards.append(
            f"""
<div class="group relative bg-surface-container-lowest/70 backdrop-blur-md rounded-xl p-6 transition-all duration-300 hover:bg-surface-container-lowest hover:-translate-y-1">
  <div class="flex justify-between items-start mb-4">
    <div class="relative w-24 h-24 rounded-full overflow-hidden border-4 border-surface-container-high bg-primary-container flex items-center justify-center">
      {icon_svg}
    </div>
    <form method="post" action="/plants/{p.id}/remove" onsubmit="return confirm('Remove this plant?');">
      <button class="material-symbols-outlined text-outline-variant hover:text-error transition-colors p-2" aria-label="Remove plant" type="submit">delete_outline</button>
    </form>
  </div>
  <div class="space-y-1 mb-4">
    <div class="flex items-center gap-2">
      <h3 class="text-xl font-headline font-bold text-on-surface">{display_name}</h3>
      <span class="px-2 py-0.5 rounded-full {env_badge_bg} text-[10px] font-bold uppercase tracking-wider">{env_badge}</span>
    </div>
    <div class="flex items-center gap-1 text-on-surface-variant text-sm">
      <span class="material-symbols-outlined text-sm">location_on</span>
      <span>{room_name}</span>
    </div>
  </div>
  <div class="flex items-center gap-3 {watering_box_class} p-3 rounded-lg mb-4">
    <span class="material-symbols-outlined {'text-error' if due_class == 'text-error' else 'text-primary'}">water_drop</span>
    <div class="flex flex-col">
      <span class="text-xs {watering_label_class} font-medium">Watering status</span>
      <span class="text-sm font-bold {due_class}">{due_text}</span>
    </div>
  </div>
  <div class="flex justify-between items-center pt-4 border-t border-outline-variant/10">
    <div class="flex flex-col">
      <span class="text-[10px] uppercase tracking-tighter text-tertiary font-bold">Care Streak</span>
      <div class="flex items-baseline gap-1">
        <span class="text-lg font-bold text-secondary">{streak} days</span>
        <span class="text-[10px] text-on-surface-variant">Best: {best}</span>
      </div>
    </div>
    <div class="flex -space-x-2">{badge_html}</div>
  </div>
</div>"""
        )

    content = "\n".join(cards) if cards else """
<div class="mt-16 p-8 rounded-2xl bg-surface-container-low/50 border border-outline-variant/10 text-center">
  <p class="font-headline text-xl text-tertiary mb-4">Adding a new companion?</p>
  <a href="/add-plant" class="inline-block px-8 py-3 bg-primary text-on-primary rounded-full font-bold text-sm shadow-xl hover:bg-primary-dim transition-all active:scale-95 duration-300">+ Add Plant</a>
</div>"""

    added_msg = f'<div class="mb-8 p-4 rounded-2xl bg-primary-container/70 text-on-primary-container text-sm font-semibold">Added {_esc(name or "")}. It is on your list.</div>' if added_name else ""
    sort_value = sort or "due"
    plants_count = len(plants)

    html = f"""<!DOCTYPE html>
<html class="light" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>My Plants | Plant Pal</title>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800&amp;family=Plus+Jakarta+Sans:wght@200..800&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script>
tailwind.config = {{
  darkMode: "class",
  theme: {{
    extend: {{
      colors: {{
        "error-container": "#fd795a", "primary-fixed-dim": "#c4dbb7", "tertiary-fixed-dim": "#e7ebc7",
        "inverse-on-surface": "#a09e87", "secondary": "#845c32", "on-tertiary-container": "#5b6044",
        "primary": "#566a4d", "on-secondary-fixed": "#5a3811", "tertiary": "#62674a", "error-dim": "#791903",
        "on-error": "#ffffff", "outline": "#84825c", "on-tertiary-fixed-variant": "#666a4e",
        "surface-container-lowest": "#ffffff", "surface-container": "#f9f5d0", "on-tertiary": "#ffffff",
        "on-surface-variant": "#686642", "tertiary-fixed": "#f6fad5", "surface-container-low": "#fffbda",
        "surface-variant": "#eeeabd", "secondary-container": "#ffdcbd", "inverse-surface": "#0f0f03",
        "on-secondary-container": "#6f4a22", "secondary-fixed-dim": "#ffca98", "background": "#fffbff",
        "on-primary-fixed-variant": "#4d6144", "surface-dim": "#e8e4b8", "on-surface": "#3a391a",
        "secondary-dim": "#765028", "on-secondary": "#ffffff", "tertiary-dim": "#565b3f",
        "on-primary-container": "#43573b", "surface": "#fffbff", "error": "#ae4025", "primary-container": "#d2eac5",
        "on-secondary-fixed-variant": "#7a532a", "on-primary-fixed": "#31442a", "surface-container-high": "#f3efc8",
        "primary-fixed": "#d2eac5", "on-tertiary-fixed": "#494e33", "on-primary": "#ffffff", "outline-variant": "#bebb91",
        "surface-container-highest": "#eeeabd", "surface-bright": "#fffbff", "on-background": "#3a391a",
        "tertiary-container": "#f6fad5", "secondary-fixed": "#ffdcbd", "on-error-container": "#6e1400",
        "inverse-primary": "#e6fed8", "primary-dim": "#4a5e41", "surface-tint": "#566a4d"
      }},
      fontFamily: {{
        "headline": ["Newsreader"],
        "body": ["Plus Jakarta Sans"],
        "label": ["Plus Jakarta Sans"]
      }},
    }},
  }},
}};
</script>
<style>
.material-symbols-outlined {{ font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24; }}
.fill-icon {{ font-variation-settings: "FILL" 1; }}
body {{ background-image: linear-gradient(rgba(255, 251, 255, 0.4), rgba(255, 251, 255, 0.4)), url(https://lh3.googleusercontent.com/aida-public/AB6AXuD_kzHB5kZ9wI_0VybKr1jDEEkzz0XySBJ4K5CYoYFJaWPRwlBaVoSgxxyWOtJqPW-Dd1BjoL9SnxWcKTrUS8JQWmruzeLMY1wKupAWoBCqYADJJdCijNZHNRWOHqkbcMj9sQMHueRpk7WRpJzHAb4mFax1tJZIFmCDs6EBw7pe2Qgpa8plnkX3gFCzzLprISZJUoGvO8u65mtmRyk6ddXOhv7LzMdvHjydH3VzxTkilRpzy-m_7oFJSdPX29vDRqlSiLNcpZiHeGo); background-size: cover; background-position: center; background-attachment: fixed; min-height: 100vh; }}
</style>
</head>
<body class="font-body text-on-surface min-h-screen">
<header class="bg-stone-50/80 backdrop-blur-md shadow-sm sticky top-0 z-50">
  <div class="flex justify-between items-center w-full px-8 py-4 max-w-full">
    <div class="font-serif text-2xl italic tracking-tight text-emerald-900">Plant Pal</div>
    <nav class="hidden md:flex items-center space-x-8">
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/">Home</a>
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/library">Library</a>
      <a class="text-emerald-900 font-semibold border-b-2 border-emerald-900 transition-all" href="/plants">My Plants</a>
      <a class="text-stone-500 hover:bg-stone-200/50 transition-colors duration-300 px-3 py-1 rounded-lg" href="/add-plant">Add Plant</a>
    </nav>
    <div class="flex items-center gap-4">
      <span class="text-sm font-medium text-on-surface-variant hidden sm:inline" id="plants-clock">--:--</span>
      <button class="material-symbols-outlined text-green-800 hover:opacity-80 transition-opacity duration-300">schedule</button>
      <div class="w-10 h-10 rounded-full bg-surface-container-high overflow-hidden border border-outline-variant/20 flex items-center justify-center">
        <span class="material-symbols-outlined text-outline">account_circle</span>
      </div>
    </div>
  </div>
</header>
<main class="max-w-7xl mx-auto px-6 pt-12 pb-32">
  <div id="main">
    <div class="flex items-center justify-between mb-5">
      <p class="text-sm"><a href="/" class="underline">Home</a> · <a href="/library" class="underline">Library</a> · <a href="/add-plant" class="underline">+ Add plant</a></p>
    </div>
    {added_msg}
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
      <div>
        <h2 class="text-5xl font-headline italic font-bold text-on-surface tracking-tight mb-2">My Plants</h2>
        <p class="text-on-surface-variant font-medium">Caring for {plants_count} botanical friends</p>
      </div>
      <form class="flex items-center gap-4 bg-surface-container-low/60 backdrop-blur-sm p-2 rounded-full border border-outline-variant/10" method="get" action="/plants">
        {f'<input type="hidden" name="added" value="1"/><input type="hidden" name="name" value="{_esc(name or "")}"/>' if added_name else ''}
        <span class="pl-4 text-sm font-medium text-on-surface-variant">Sort By</span>
        <select name="sort" onchange="this.form.submit()" class="bg-transparent border-none focus:ring-0 text-primary font-bold text-sm cursor-pointer pr-10">
            <option value="due" {"selected" if sort_value == "due" else ""}>Due soon</option>
            <option value="room" {"selected" if sort_value == "room" else ""}>Room</option>
            <option value="name" {"selected" if sort_value == "name" else ""}>Name</option>
          </select>
      </form>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">{content}</div>
  </div>
</main>
<nav class="md:hidden fixed bottom-0 left-0 w-full flex justify-around items-center px-6 pb-6 pt-3 bg-stone-50/80 backdrop-blur-lg border-t border-stone-200/20 shadow-[0_-4px_20px_rgba(0,0,0,0.05)] z-50">
  <a class="flex flex-col items-center justify-center text-stone-500 px-4 py-2 hover:text-emerald-700" href="/">
    <span class="material-symbols-outlined">home</span>
    <span class="text-xs font-medium mt-1">Home</span>
  </a>
  <a class="flex flex-col items-center justify-center text-stone-500 px-6 py-2 hover:text-emerald-700" href="/library">
    <span class="material-symbols-outlined">local_library</span>
    <span class="text-xs font-medium mt-1">Library</span>
  </a>
  <a class="flex flex-col items-center justify-center bg-emerald-100/50 text-emerald-900 rounded-xl px-6 py-2 transition-all scale-90 duration-200" href="/plants">
    <span class="material-symbols-outlined">potted_plant</span>
    <span class="text-xs font-medium mt-1">My Plants</span>
  </a>
  <a class="flex flex-col items-center justify-center text-stone-500 px-6 py-2 hover:text-emerald-700" href="/add-plant">
    <span class="material-symbols-outlined">add_circle</span>
    <span class="text-xs font-medium mt-1">Add Plant</span>
  </a>
</nav>
<script>
  (function() {{
    var el = document.getElementById('plants-clock');
    if (!el) return;
    function tick() {{
      var now = new Date();
      var h = now.getHours(), m = now.getMinutes();
      var h12 = h % 12 || 12;
      el.textContent = h12 + ':' + (m < 10 ? '0' : '') + m + (h < 12 ? ' AM' : ' PM');
    }}
    tick();
    setInterval(tick, 60000);
  }})();
</script>
</body>
</html>"""
    return HTMLResponse(html)


@app.post("/plants/{plant_id}/remove")
def remove_plant_post(plant_id: str):
    """Remove a plant and redirect to My Plants."""
    remove_plant(plant_id)
    return RedirectResponse(url="/plants", status_code=303)


@app.post("/add-plant")
def add_plant_submit(
    display_name: str = Form(""),
    room_name: str = Form(""),
    pot_diameter_inches: int = Form(8),
    pot_material: str = Form("plastic"),
    light_level: str = Form("medium"),
    template_id: str = Form(""),
    next: str = Form("/plants"),
):
    """Form POST: add plant and redirect. Use next=/ to return to home, or /plants for My Plants."""
    from urllib.parse import quote
    init_db()
    name = display_name or "Unnamed"
    add_plant(
        display_name=name,
        room_name=room_name or "Unknown",
        pot_diameter_inches=pot_diameter_inches,
        pot_material=pot_material,
        light_level=light_level,
        template_id=template_id or None,
    )
    next_val = (next or "").strip().lower()
    if next_val in ("", "/", "home"):
        url = "/?added=1&name=" + quote(name)
    else:
        url = "/plants?added=1&name=" + quote(name)
    return RedirectResponse(url=url, status_code=303)


class AddPlantBody(BaseModel):
    display_name: str
    room_name: str
    pot_diameter_inches: int = 8
    pot_material: str = "plastic"
    light_level: str = "medium"
    template_id: Optional[str] = None


class LogWateredBody(BaseModel):
    soil_feeling: Optional[str] = None  # "dry" | "ok" | "wet"


@app.get("/api/actions/today")
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
        }
        for plant, action in actions_with_plants
    ]


@app.get("/api/templates")
def api_list_templates(environment: Optional[str] = None):
    """List care templates. Optional ?environment=indoor|outdoor."""
    init_db()
    ensure_seeded()
    env = environment if environment in ("indoor", "outdoor") else None
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
        }
        for t in templates
    ]


@app.get("/api/templates/search")
def api_search_templates(q: Optional[str] = None, environment: Optional[str] = None):
    """
    Search templates by name. Uses parameterized queries only (no SQL injection).
    Optional ?environment=indoor|outdoor to filter.
    """
    init_db()
    ensure_seeded()
    env = environment if environment in ("indoor", "outdoor") else None
    templates = search_templates(q or "", limit=25, environment=env)
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "icon_id": getattr(t, "icon_id", None) or t.slug,
            "icon_svg": get_icon_svg(getattr(t, "icon_id", None) or t.slug),
            "watering_frequency_display": t.watering_frequency_display,
            "light_display": t.light_display,
            "description": t.description,
            "environment": getattr(t, "environment", "indoor"),
        }
        for t in templates
    ]


@app.get("/api/plants")
def api_list_plants():
    """List all plants (for current user)."""
    init_db()
    plants = get_plants()
    today = date.today()
    return [
        {
            "id": str(p.id),
            "display_name": p.display_name,
            "room_name": p.room_name,
            "pot_diameter_inches": p.pot_diameter_inches,
            "pot_material": p.pot_material,
            "light_level": p.light_level,
            "last_watered_date": p.last_watered_date.isoformat() if p.last_watered_date else None,
            "drying_coefficient": p.drying_coefficient,
            "current_streak": p.current_streak,
            "longest_streak": p.longest_streak,
            "badges_earned": p.badges_earned,
            "due_date": (d.isoformat() if (d := predicted_dry_date(p, today)) else None),
        }
        for p in plants
    ]


@app.post("/api/plants")
def api_add_plant(body: AddPlantBody):
    """Add a new plant."""
    init_db()
    plant = add_plant(
        display_name=body.display_name,
        room_name=body.room_name,
        pot_diameter_inches=body.pot_diameter_inches,
        pot_material=body.pot_material,
        light_level=body.light_level,
        template_id=body.template_id,
    )
    return {"id": str(plant.id), "display_name": plant.display_name}


@app.post("/api/plants/{plant_id}/log-watered")
def api_log_watered(plant_id: str, body: Optional[LogWateredBody] = None):
    """
    Mark plant as watered today. Optionally pass soil_feeling: "dry" | "ok" | "wet"
    to tune the learning (drying_coefficient). Redirects back to panel if from browser.
    """
    log_watered(plant_id, soil_feeling=body.soil_feeling if body else None)
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/plants/{plant_id}/log-watered")
def api_log_watered_get(plant_id: str, soil: Optional[str] = None):
    """GET version for 'Done' links from panel (soil=ok by default)."""
    log_watered(plant_id, soil_feeling=soil or "ok")
    return RedirectResponse(url="/", status_code=303)


# ---------- PWA: installable app (e.g. Kindle Fire "Add to Home Screen") ----------

@app.get("/manifest.json", response_class=JSONResponse)
def pwa_manifest():
    """Web app manifest so the panel can be added to home screen and opened like an app."""
    return JSONResponse({
        "name": "Plant Pal",
        "short_name": "Plant Pal",
        "description": "Track watering and care for your plants",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f0ebe3",
        "theme_color": "#7d8b6f",
    })


@app.get("/sw.js", response_class=Response)
def service_worker():
    """Minimal service worker so browsers offer 'Install' / Add to Home Screen."""
    js = """
self.addEventListener('install', function(e) { self.skipWaiting(); });
self.addEventListener('activate', function(e) { e.waitUntil(self.clients.claim()); });
"""
    return Response(content=js.strip(), media_type="application/javascript")
