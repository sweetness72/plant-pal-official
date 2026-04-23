"""Short, shared UI strings for engine output (keeps HTML routes consistent)."""

from __future__ import annotations

from .schema import Confidence


def recommendation_confidence_for_ui(confidence: Confidence) -> dict:
    """Map engine ``Confidence`` to template props.

    - ``label``: full phrase where a chip or screen reader still needs the word
      *confidence* (e.g. portrait meta if reintroduced).
    - ``short``: one word for visible “For today: …” lines (reduces repetition).
    - ``today_title``: tooltip on that line — honest split from history/learning.
    """
    if confidence == Confidence.HIGH:
        return {
            "label": "High confidence",
            "short": "High",
            "variant": "high",
            "today_title": (
                "How sure we are about today’s water or check suggestion. "
                "Separate from how much watering history this plant has."
            ),
        }
    if confidence == Confidence.MEDIUM:
        return {
            "label": "Medium confidence",
            "short": "Medium",
            "variant": "medium",
            "today_title": (
                "How sure we are about today’s water or check suggestion. "
                "Separate from how much watering history this plant has."
            ),
        }
    return {
        "label": "Low confidence",
        "short": "Low",
        "variant": "low",
        "today_title": (
            "How sure we are about today’s water or check suggestion. "
            "Separate from how much watering history this plant has."
        ),
    }
