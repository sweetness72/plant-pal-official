"""Place + archetype helpers for human-facing labels."""

from core.identity_cues import archetype_cue, format_place_cue
from core.schema import CareTemplate, MoisturePreference, Plant


def test_format_place_cue_joins_room_and_position():
    assert format_place_cue("Kitchen Window", "Right") == "Kitchen Window · Right"


def test_format_place_cue_room_only():
    assert format_place_cue("Living Room", None) == "Living Room"


def test_archetype_cue_prefers_template_name():
    t = CareTemplate(
        name="Snake plant",
        slug="snake",
        default_drying_days=7,
        moisture_preference=MoisturePreference.EVENLY_MOIST,
    )
    p = Plant(template=t, display_name="Bob", room_name="Office")
    assert archetype_cue(p) == "Snake plant"


def test_archetype_cue_falls_back_to_visual_type():
    p = Plant(
        template=None,
        display_name="Bob",
        room_name="Office",
        visual_type="succulent",
    )
    assert archetype_cue(p) == "Succulent"
