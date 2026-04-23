"""``update_plant`` updates identity + template-derived visuals."""

from __future__ import annotations

from core import db as db_module


def test_update_plant_position_and_room(tmp_db):
    p = db_module.add_plant(
        display_name="A",
        room_name="One",
        position_note="left",
        template_id=None,
    )
    pid = str(p.id)
    t = db_module.get_plant(pid)
    assert t is not None
    assert t.position_note == "left"

    db_module.update_plant(
        pid,
        display_name="A2",
        room_name="Two",
        position_note="back",
        template_id=None,
        light_level="low",
        pot_diameter_inches=6,
        pot_material="ceramic",
    )
    t2 = db_module.get_plant(pid)
    assert t2 is not None
    assert t2.display_name == "A2"
    assert t2.room_name == "Two"
    assert t2.position_note == "back"
    assert t2.light_level.value == "low"
