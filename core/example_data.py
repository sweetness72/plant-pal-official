"""Shared example plants for demo / development."""
from datetime import date, timedelta
from typing import List, Optional

from .schema import CareTemplate, LightLevel, MoisturePreference, Plant, PotMaterial


def get_example_plants(today: Optional[date] = None) -> List[Plant]:
    today = today or date.today()

    fig_template = CareTemplate(
        name="Fiddle Leaf Fig",
        slug="fiddle-leaf-fig",
        default_drying_days=7,
        moisture_preference=MoisturePreference.DRY_BETWEEN,
        icon_id="fig",
    )
    fig = Plant(
        template=fig_template,
        display_name="Living Room Fig",
        room_name="Living Room",
        pot_diameter_inches=14,
        pot_material=PotMaterial.CERAMIC,
        light_level=LightLevel.BRIGHT,
        last_watered_date=today - timedelta(days=8),
        drying_coefficient=1.0,
    )

    snake_template = CareTemplate(
        name="Snake Plant",
        slug="snake-plant",
        default_drying_days=14,
        moisture_preference=MoisturePreference.DRY_BETWEEN,
        icon_id="snake",
    )
    snake = Plant(
        template=snake_template,
        display_name="Office Snake Plant",
        room_name="Office",
        pot_diameter_inches=8,
        pot_material=PotMaterial.PLASTIC,
        light_level=LightLevel.LOW,
        last_watered_date=today - timedelta(days=5),
    )

    fern_template = CareTemplate(
        name="Boston Fern",
        slug="boston-fern",
        default_drying_days=5,
        moisture_preference=MoisturePreference.MOIST_OFTEN,
        icon_id="fern",
    )
    fern = Plant(
        template=fern_template,
        display_name="Bathroom Fern",
        room_name="Bathroom",
        pot_diameter_inches=6,
        pot_material=PotMaterial.TERRACOTTA,
        light_level=LightLevel.MEDIUM,
        last_watered_date=today - timedelta(days=4),
    )

    new_plant = Plant(
        display_name="Mystery Plant",
        room_name="Kitchen",
        pot_diameter_inches=10,
        created_at=None,
    )

    return [fig, snake, fern, new_plant]
