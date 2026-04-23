"""History / observation-count tier for honest UI copy (separate from model Confidence)."""

from __future__ import annotations

def history_learning_tier(observation_count: int) -> str:
    """``low`` | ``medium`` | ``high`` — for CSS only; tied to honest history depth."""
    n = max(0, int(observation_count))
    if n < 3:
        return "low"
    if n < 5:
        return "medium"
    return "high"


def history_learning_copy(observation_count: int) -> tuple[str, str]:
    """(short label, title tooltip). How much *history* we have — not model quality."""
    n = max(0, int(observation_count))
    if n < 3:
        return (
            "Still learning",
            "We're still learning this plant's rhythm. Building a picture from your first few waterings.",
        )
    if n < 5:
        return (
            "Getting dialed in",
            "A rhythm is starting to show. A bit more history helps the schedule feel steady.",
        )
    return (
        "Steady history",
        f"We've seen enough check-ins ({n} waterings) to trust this pattern.",
    )


def history_learning_badge(observation_count: int) -> dict:
    """Template-friendly: label, tooltip title, and ``pp-chip--hist-*`` variant key."""
    n = max(0, int(observation_count))
    label, title = history_learning_copy(n)
    return {
        "label": label,
        "title": title,
        "variant": history_learning_tier(n),
    }
