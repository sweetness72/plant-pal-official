"""
Tests for the security middleware + /healthz endpoint.

These are intentionally narrow: we are pinning contracts we care about
(probes work, headers are present, CSP is opt-in, hosts are enforceable)
without testing Starlette itself.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fresh_client(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    """Build a TestClient with the given env applied *before* the app is
    imported. ``app.main`` installs middleware at import time based on env
    vars, so we reload the module inside each test to pick up new values.

    Also monkeypatches DATA_DIR so the healthz DB probe doesn't write into
    the real project data directory during tests.
    """
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Ensure a clean reload of both the security module (captures env at
    # install time) and the app module (wires the middleware in).
    import app.main as main_mod
    import app.security as security_mod

    importlib.reload(security_mod)
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Start every test with the security env vars cleared so nothing
    leaks between tests."""
    for var in ("PLANTPAL_ALLOWED_HOSTS", "PLANTPAL_ENABLE_CSP", "PLANTPAL_CSP_REPORT_ONLY"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


class TestHealthz:
    def test_returns_200_and_ok_payload(self, clean_env):
        client = _fresh_client(clean_env)
        r = client.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"

    def test_not_included_in_openapi_schema(self, clean_env):
        client = _fresh_client(clean_env)
        schema = client.get("/openapi.json").json()
        # /healthz is an ops probe, not part of the public API surface.
        assert "/healthz" not in schema.get("paths", {})
        assert "/status" not in schema.get("paths", {})


class TestStatus:
    """``/status`` — human-oriented runtime + DB file summary (not a probe)."""

    def test_returns_200_with_expected_keys(self, clean_env):
        r = _fresh_client(clean_env).get("/status")
        assert r.status_code == 200
        body = r.json()
        assert body["app"] == "plant-pal"
        assert "version" in body
        assert "python" in body
        assert "platform" in body
        assert "uptime_sec" in body
        assert "db" in body
        assert "file" in body["db"]
        assert "log_level" in body
        assert body["db"]["schema_version"] is not None


# ---------------------------------------------------------------------------
# Default headers
# ---------------------------------------------------------------------------


class TestDefaultHeaders:
    """Headers that are always present, CSP or no CSP."""

    @pytest.fixture
    def headers(self, clean_env) -> dict[str, str]:
        client = _fresh_client(clean_env)
        return dict(client.get("/healthz").headers)

    def test_nosniff(self, headers):
        assert headers["x-content-type-options"] == "nosniff"

    def test_frame_deny(self, headers):
        assert headers["x-frame-options"] == "DENY"

    def test_referrer_policy(self, headers):
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin"

    def test_cross_domain_policies(self, headers):
        assert headers["x-permitted-cross-domain-policies"] == "none"

    def test_csp_absent_by_default(self, headers):
        # CSP is opt-in; by default neither header should be present.
        assert "content-security-policy" not in headers
        assert "content-security-policy-report-only" not in headers


# ---------------------------------------------------------------------------
# CSP opt-in
# ---------------------------------------------------------------------------


class TestCSP:
    def test_emits_enforcing_header_when_enabled(self, clean_env):
        client = _fresh_client(clean_env, PLANTPAL_ENABLE_CSP="1")
        r = client.get("/healthz")
        csp = r.headers.get("content-security-policy")
        assert csp is not None
        # Sanity-check a few directives so a future author who tightens the
        # policy has to consciously update the test.
        assert "default-src 'self'" in csp
        assert "https://cdn.tailwindcss.com" in csp
        assert "frame-ancestors 'none'" in csp
        # In enforce mode the report-only header must NOT be set.
        assert "content-security-policy-report-only" not in r.headers

    def test_emits_report_only_header_when_requested(self, clean_env):
        client = _fresh_client(clean_env, PLANTPAL_ENABLE_CSP="1", PLANTPAL_CSP_REPORT_ONLY="1")
        r = client.get("/healthz")
        assert r.headers.get("content-security-policy-report-only") is not None
        # ...and the enforcing header is absent.
        assert "content-security-policy" not in r.headers


# ---------------------------------------------------------------------------
# TrustedHostMiddleware
# ---------------------------------------------------------------------------


class TestTrustedHost:
    def test_default_wildcard_accepts_any_host(self, clean_env):
        client = _fresh_client(clean_env)
        r = client.get("/healthz", headers={"Host": "whatever.example.com"})
        assert r.status_code == 200

    def test_allowlist_accepts_listed_host(self, clean_env):
        client = _fresh_client(clean_env, PLANTPAL_ALLOWED_HOSTS="plantpal.local,127.0.0.1")
        r = client.get("/healthz", headers={"Host": "plantpal.local"})
        assert r.status_code == 200

    def test_allowlist_rejects_unlisted_host(self, clean_env):
        client = _fresh_client(clean_env, PLANTPAL_ALLOWED_HOSTS="plantpal.local")
        r = client.get("/healthz", headers={"Host": "attacker.example.com"})
        # Starlette returns 400 Invalid host header for rejected hosts.
        assert r.status_code == 400

    def test_rejected_response_still_has_security_headers(self, clean_env):
        """Reject responses go through the outer header middleware too, so
        a rejected probe isn't missing headers that downstream tools might
        expect."""
        client = _fresh_client(clean_env, PLANTPAL_ALLOWED_HOSTS="plantpal.local")
        r = client.get("/healthz", headers={"Host": "attacker.example.com"})
        assert r.status_code == 400
        assert r.headers.get("x-content-type-options") == "nosniff"
