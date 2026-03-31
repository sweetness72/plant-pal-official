"""
Minimal schema for MVP: CareTemplate, Plant, Action.
No DB yet — just dataclasses for the drying engine.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class MoisturePreference(str, Enum):
    DRY_BETWEEN = "dry_between"   # e.g. cactus, snake plant
    EVENLY_MOIST = "evenly_moist"  # most houseplants
    MOIST_OFTEN = "moist_often"    # ferns, some tropicals


class PotMaterial(str, Enum):
    PLASTIC = "plastic"
    CERAMIC = "ceramic"
    TERRACOTTA = "terracotta"


class LightLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    BRIGHT = "bright"


class ActionType(str, Enum):
    WATER = "WATER"
    CHECK = "CHECK"
    FERTILIZE = "FERTILIZE"
    MOVE = "MOVE"


@dataclass
class CareTemplate:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    slug: str = ""
    default_drying_days: int = 7
    moisture_preference: MoisturePreference = MoisturePreference.EVENLY_MOIST
    icon_id: str = "houseplant"
    watering_frequency_display: str = ""
    light_display: str = ""
    description: str = ""
    environment: str = "indoor"  # "indoor" | "outdoor"
    category: str = ""  # e.g. "Foliage", "Herbs & Spices", "Flowering Perennials"
    growing_instructions: str = ""  # care and growing steps for library


@dataclass
class Plant:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    template: Optional[CareTemplate] = None
    display_name: str = ""
    room_name: str = ""
    pot_diameter_inches: int = 8
    pot_material: PotMaterial = PotMaterial.PLASTIC
    light_level: LightLevel = LightLevel.MEDIUM
    last_watered_date: Optional[date] = None
    drying_coefficient: float = 1.0
    low_effort_mode: bool = False
    created_at: Optional[date] = None  # for new-plant edge case
    current_streak: int = 0
    longest_streak: int = 0
    badges_earned: list[int] = field(default_factory=list)  # milestone counts e.g. [3, 5, 10]

    def get_default_drying_days(self) -> int:
        if self.template:
            return self.template.default_drying_days
        return 7

    def get_moisture_preference(self) -> MoisturePreference:
        if self.template:
            return self.template.moisture_preference
        return MoisturePreference.EVENLY_MOIST

    def get_icon_id(self) -> str:
        if self.template:
            return self.template.icon_id
        return "houseplant"


@dataclass
class Action:
    plant_id: UUID = field(default_factory=uuid4)
    date: date = field(default_factory=date.today)
    action_type: ActionType = ActionType.WATER
    amount_oz: Optional[int] = None
    note: str = ""
    priority: int = 0
