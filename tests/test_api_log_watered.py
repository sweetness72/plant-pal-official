"""POST /api/plants/{id}/log-watered applies soil feedback to ``drying_coefficient``."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core import db as db_module


def _client() -> TestClient:
    return TestClient(app)


def _add_plant() -> str:
    p = db_module.add_plant(
        display_name="Fern",
        room_name="Lab",
        pot_diameter_inches=8,
        pot_material="plastic",
        light_level="medium",
        template_id=None,
    )
    return str(p.id)


class TestApiLogWateredSoilFeedback:
    def test_wet_increases_coefficient(self, tmp_db):
        pid = _add_plant()
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(1.0)
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "wet"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(1.05)

    def test_dry_decreases_coefficient(self, tmp_db):
        pid = _add_plant()
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "dry"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(0.95)

    def test_ok_unchanged_at_one(self, tmp_db):
        pid = _add_plant()
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "ok"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(1.0)

    def test_empty_body_defaults_to_ok(self, tmp_db):
        pid = _add_plant()
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db_module.get_plant(pid).drying_coefficient == pytest.approx(1.0)

    def test_invalid_soil_rejected(self, tmp_db):
        pid = _add_plant()
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "mushy"},
        )
        assert r.status_code == 422

    def test_backdated_watering_stores_date(self, tmp_db):
        pid = _add_plant()
        when = date.today() - timedelta(days=3)
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "ok", "watered_date": when.isoformat()},
            follow_redirects=False,
        )
        assert r.status_code == 303
        p = db_module.get_plant(pid)
        assert p is not None
        assert p.last_watered_date == when

    def test_future_watering_rejected(self, tmp_db):
        pid = _add_plant()
        tmr = date.today() + timedelta(days=1)
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "ok", "watered_date": tmr.isoformat()},
        )
        assert r.status_code == 422
        assert "future" in r.text.lower() or "future" in str(r.json()).lower()

    def test_watering_before_last_rejected(self, tmp_db):
        pid = _add_plant()
        t = date.today()
        d_recent = t - timedelta(days=1)
        d_older = t - timedelta(days=4)
        db_module.log_watered(pid, watered_date=d_recent, soil_feeling="ok")
        r = _client().post(
            f"/api/plants/{pid}/log-watered",
            json={"soil_feeling": "ok", "watered_date": d_older.isoformat()},
        )
        assert r.status_code == 422
        assert "last" in r.text.lower() or "last" in str(r.json()).lower()
