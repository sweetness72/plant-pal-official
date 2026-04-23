"""Shared UI strings for recommendation confidence."""

from core.schema import Confidence
from core.ui_copy import recommendation_confidence_for_ui


def test_recommendation_confidence_for_ui_short_tier():
    h = recommendation_confidence_for_ui(Confidence.HIGH)
    assert h["short"] == "High"
    assert "confidence" not in h["short"].lower()
    assert h["variant"] == "high"
    assert "today_title" in h
