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
    visual_type: str = ""  # archetype key → /static/plants/{visual_type}.png


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
    # Image resolution (optional; fall back to template + defaults — see core/plant_images.py)
    category: Optional[str] = None  # "indoor" | "outdoor" for fallback PNGs
    visual_type: Optional[str] = None  # archetype; None → inherit from template
    image_override: Optional[str] = None  # full URL or path under site root
    # Recommendation v2 interval estimator. Nullable on fresh plants and
    # on DBs that pre-date migration 2. ``observation_count`` counts
    # waterings integrated (not intervals), so ``mean``/``var`` become
    # meaningful after the second watering.
    interval_mean_days: Optional[float] = None
    interval_var_days: Optional[float] = None
    observation_count: int = 0
    # Free-text spot hint: "left", "by sink", etc. (human recognition only)
    position_note: str | None = None

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


class Confidence(str, Enum):
    """Bucketed confidence the engine has in today's recommendation.

    Kept to three buckets on purpose — a continuous number would
    overstate precision for a model this small. See docs in
    ``core/drying_model.py::_score_confidence`` for the exact rules.
    """

    LOW = "low"        # new plant, sparse history, stale, or recent context change
    MEDIUM = "medium"  # enough history to be useful, but still noisy or early
    HIGH = "high"      # many observations and the plant behaves consistently


class ReasonCode(str, Enum):
    """Why the engine returned this recommendation. Stable keys so the UI
    can localize/reword without changing the engine."""

    NEW_PLANT = "new_plant"                  # first watering — start the timer
    DUE_TODAY = "due_today"                  # today == predicted dry date
    OVERDUE = "overdue"                      # today > predicted dry date
    SOIL_CHECK_LOW_CONFIDENCE = "soil_check_low_confidence"  # CHECK emitted 1 day before due
    STALE_HISTORY = "stale_history"          # last watered far longer than the interval
    NOT_DUE = "not_due"                      # nothing to do today


@dataclass
class Recommendation:
    """Engine output with room for explanation + confidence.

    ``action`` stays the single source of truth for "what should the user do".
    Everything else is metadata the UI can choose to surface.

    Phase 1: populated from the existing drying model with history-aware
    confidence. Phase 2+: mean/variance come from an online estimator and
    ``factors`` starts listing learned offsets too.
    """

    action: Optional[Action]
    reason_code: ReasonCode
    factors: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    predicted_interval_days: float = 0.0
    observations_used: int = 0
