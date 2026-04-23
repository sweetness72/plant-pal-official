"""Invalid JSON/query/path inputs on /api/* return 422 (FastAPI + Pydantic)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_VALID_ADD = {
    "display_name": "Fern",
    "room_name": "Lab",
    "pot_diameter_inches": 8,
    "pot_material": "plastic",
    "light_level": "medium",
    "template_id": None,
}


class TestAddPlantJsonValidation:
    def test_rejects_zero_pot_diameter(self, tmp_db):
        p = {**_VALID_ADD, "pot_diameter_inches": 0}
        r = client.post(
            "/api/plants",
            content=json.dumps(p),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_rejects_unknown_light_level(self, tmp_db):
        p = {**_VALID_ADD, "light_level": "extreme"}
        r = client.post(
            "/api/plants",
            content=json.dumps(p),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
        assert "extreme" in r.text

    def test_rejects_unknown_material(self, tmp_db):
        p = {**_VALID_ADD, "pot_material": "wood"}
        r = client.post(
            "/api/plants",
            content=json.dumps(p),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_rejects_empty_display_name(self, tmp_db):
        p = {**_VALID_ADD, "display_name": ""}
        r = client.post(
            "/api/plants",
            content=json.dumps(p),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_rejects_extra_json_fields(self, tmp_db):
        p = {**_VALID_ADD, "hacked": 1}
        r = client.post(
            "/api/plants",
            content=json.dumps(p),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        # Pydantic extra="forbid" or similar validation message
        assert any("hacked" in str(item).lower() or "extra" in str(item).lower() for item in detail)


class TestLogWateredJsonValidation:
    def test_rejects_mushy_soil(self, tmp_db):
        p = {**_VALID_ADD}
        c = client.post(
            "/api/plants", content=json.dumps(p), headers={"content-type": "application/json"}
        )
        assert c.status_code == 200, c.text
        pid = c.json()["id"]
        r = client.post(
            f"/api/plants/{pid}/log-watered",
            content=json.dumps({"soil_feeling": "mushy"}),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422

    def test_rejects_extra_log_body_fields(self, tmp_db):
        p = {**_VALID_ADD}
        c = client.post(
            "/api/plants", content=json.dumps(p), headers={"content-type": "application/json"}
        )
        assert c.status_code == 200
        pid = c.json()["id"]
        r = client.post(
            f"/api/plants/{pid}/log-watered",
            content=json.dumps({"soil_feeling": "ok", "nope": 1}),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
        assert any("nope" in str(d).lower() or "extra" in str(d).lower() for d in r.json()["detail"])

    def test_rejects_non_uuid_path(self, tmp_db):
        r = client.post(
            "/api/plants/not-a-uuid/log-watered",
            content=json.dumps({"soil_feeling": "ok"}),
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422


class TestTemplateQueryValidation:
    def test_invalid_environment_rejected(self, tmp_db):
        r = client.get("/api/templates?environment=garage")
        assert r.status_code == 422

    def test_invalid_search_environment_rejected(self, tmp_db):
        r = client.get("/api/templates/search?q=fern&environment=attic")
        assert r.status_code == 422


class TestMyPlantsPage:
    """``GET /plants`` is a real HTML page (not only a redirect to ``/#all-plants``)."""

    def test_my_plants_renders(self, tmp_db):
        r = client.get("/plants")
        assert r.status_code == 200
        assert "My plants" in r.text
        assert 'href="/plants"' in r.text  # nav self-link
        assert 'href="/library"' in r.text


class TestHtmlWaterFormRedirects:
    """Form ``POST /plants/{id}/water`` matches API rules; bad date returns to *next* with query."""

    def test_invalid_water_date_redirects_home_with_e_param(self, tmp_db):
        c = client.post(
            "/api/plants",
            content=json.dumps(_VALID_ADD),
            headers={"content-type": "application/json"},
        )
        assert c.status_code == 200, c.text
        pid = c.json()["id"]
        r = client.post(
            f"/plants/{pid}/water",
            data={
                "next": "/",
                "soil_feeling": "ok",
                "watered_on": "2099-12-31",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers.get("location") == "/?e=water_date"

    def test_invalid_water_date_redirects_plant_detail_with_e_param(self, tmp_db):
        c = client.post(
            "/api/plants",
            content=json.dumps(_VALID_ADD),
            headers={"content-type": "application/json"},
        )
        pid = c.json()["id"]
        r = client.post(
            f"/plants/{pid}/water",
            data={
                "next": f"/plants/{pid}",
                "soil_feeling": "ok",
                "watered_on": "2099-12-31",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers.get("location") == f"/plants/{pid}?e=water_date"
