"""Shared rules for when a logged watering is considered to have happened."""
from __future__ import annotations

from datetime import date

from core.schema import Plant


def parse_optional_iso_date(s: str | None) -> date | None:
    """``None``/blank → no override (caller uses *today*). Bad ISO → ``ValueError``."""
    if s is None or not str(s).strip():
        return None
    return date.fromisoformat(str(s).strip())


def validate_watered_date(plant: Plant | None, d: date) -> None:
    """
    Reject invalid calendar choices before ``log_watered`` runs.

    * Not in the future (use ``date.today()`` at call time).
    * Not before the last recorded watering (keeps intervals non-negative).

    Raises ``ValueError`` with a short code: ``future`` or ``before_last``.
    """
    if d > date.today():
        raise ValueError("future")
    if (
        plant is not None
        and plant.last_watered_date is not None
        and d < plant.last_watered_date
    ):
        raise ValueError("before_last")
