"""
Rotating growth-care insights shown on the landing page.

The tip cycles every 3 days so the page feels alive without needing a CMS.
Moved here from the monolithic legacy_app.py during the refactor; behavior
(index formula, tuple shape, tip content) is preserved byte-for-byte.
"""

from __future__ import annotations

from datetime import date

GrowthInsight = tuple[str, str, str]  # (title, body, material-symbols icon id)

GROWTH_INSIGHTS: list[GrowthInsight] = [
    ("Leaf Care", "Dusting leaves helps plants photosynthesize more efficiently.", "eco"),
    (
        "Water Rhythm",
        "Water deeply, then let the top layer dry before watering again.",
        "water_drop",
    ),
    ("Light Check", "Rotate pots weekly for balanced growth and fewer leaning stems.", "wb_sunny"),
    ("Root Health", "Use pots with drainage to prevent soggy roots and rot.", "compress"),
    (
        "Humidity Boost",
        "Cluster plants together to create a small humidity pocket.",
        "humidity_percentage",
    ),
    (
        "Morning Habit",
        "Check soil in the morning when moisture readings are most consistent.",
        "schedule",
    ),
    (
        "Growth Spurts",
        "New leaves often arrive faster after brighter, steady light.",
        "trending_up",
    ),
    ("Season Shift", "Most plants need less water in cooler, darker months.", "calendar_month"),
    ("Feed Smart", "Use diluted fertilizer during active growth, not every watering.", "science"),
    ("Potting Mix", "Chunky, airy soil keeps roots oxygenated and resilient.", "filter_vintage"),
    ("Drainage Tip", "Empty saucers after watering so roots do not sit in water.", "water_ec"),
    ("Pruning", "Trim yellowing leaves to redirect energy to healthy growth.", "content_cut"),
    ("Airflow", "Gentle airflow reduces fungus risk and strengthens stems.", "air"),
    ("Sun Balance", "Bright indirect light is safer than long harsh direct sun.", "light_mode"),
    (
        "Repot Cue",
        "Repot when roots circle tightly or poke from drainage holes.",
        "home_repair_service",
    ),
    ("Pest Patrol", "Inspect leaf undersides weekly for early pest detection.", "search"),
    ("Consistency", "Stable routines beat perfect routines for plant health.", "repeat"),
    ("Room Match", "Place humidity lovers away from dry vents and heaters.", "device_thermostat"),
    ("Soil Probe", "A finger test 1-2 inches deep beats surface-only checks.", "touch_app"),
    (
        "Recovery",
        "If overwatered, improve airflow and pause watering until dry.",
        "health_and_safety",
    ),
    (
        "Leaf Signals",
        "Droop can mean thirst, but soggy soil points to overwatering.",
        "monitor_heart",
    ),
    ("Bright Corners", "South and west windows usually provide stronger growth light.", "window"),
    ("Even Canopy", "Turn plants toward light every few days for fuller shape.", "rotate_right"),
    ("Humidity Assist", "Pebble trays can raise local humidity around tropicals.", "waves"),
    (
        "Root Space",
        "Slightly snug roots are fine; severely bound roots need repotting.",
        "crop_square",
    ),
    ("Water Quality", "Room-temperature water avoids shocking sensitive roots.", "thermostat"),
    ("Sun Acclimation", "Increase direct sun gradually to prevent leaf scorch.", "solar_power"),
    ("Trim Timing", "Prune in active growth periods for faster recovery.", "event_available"),
    ("Soil Refresh", "Top-dress with fresh mix yearly to restore structure.", "refresh"),
    ("Observation", "A 30-second daily glance catches issues before they spread.", "visibility"),
]


def pick_today(today: date | None = None) -> GrowthInsight:
    """Return the insight for today (rotates every 3 days). Stable within a 3-day block."""
    day = today or date.today()
    index = (day.toordinal() // 3) % len(GROWTH_INSIGHTS)
    return GROWTH_INSIGHTS[index]
