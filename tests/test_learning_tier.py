"""Observation-count history tier (UI honesty)."""

from core.learning_tier import (
    history_learning_badge,
    history_learning_copy,
    history_learning_tier,
)


def test_history_tier_buckets():
    assert history_learning_tier(0) == "low"
    assert history_learning_tier(2) == "low"
    assert history_learning_tier(3) == "medium"
    assert history_learning_tier(4) == "medium"
    assert history_learning_tier(5) == "high"


def test_history_copy_starts_with_still_learning():
    short, _long = history_learning_copy(1)
    assert "Still learning" in short


def test_history_badge_keys():
    b = history_learning_badge(4)
    assert b["variant"] == "medium"
    assert "title" in b and "label" in b
