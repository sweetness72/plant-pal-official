"""
Security middleware for Plant Pal.

Scope: a self-hosted app that sits on a Raspberry Pi behind a LAN, possibly
shared across one or two devices. The goal is a small set of defenses that
are cheap, don't break the cozy Tailwind Play CDN setup, and can be
tightened later without a refactor.

What we install
---------------
1. ``TrustedHostMiddleware`` — reject requests whose Host header isn't in
   our allowlist. Stops DNS rebinding and accidental exposure via an
   unexpected hostname. Allowlist is env-configurable; default ``*`` keeps
   local development friction-free and logs a single warning at startup
   so it's visible if you forget to set it in a real deployment.

2. A response-header pass that adds the boring-but-useful set:
     * X-Content-Type-Options: nosniff
     * X-Frame-Options: DENY
     * Referrer-Policy: strict-origin-when-cross-origin
     * X-Permitted-Cross-Domain-Policies: none

3. Optional Content-Security-Policy (off by default; flip
   ``PLANTPAL_ENABLE_CSP=1`` to enable). The policy is intentionally
   permissive — it allows the Tailwind Play CDN, Google Fonts, and the
   inline ``tw-config`` script — so turning it on doesn't break the UI.
   When you eventually move off Play CDN, tighten this to ``'self'`` only.

Environment variables
---------------------
PLANTPAL_ALLOWED_HOSTS
    Comma-separated list for TrustedHostMiddleware. Use wildcards like
    ``*.local`` or ``*.ts.net``. Default: ``*``.

PLANTPAL_ENABLE_CSP
    ``1`` to emit a CSP header. Anything else = off.

PLANTPAL_CSP_REPORT_ONLY
    ``1`` to emit ``Content-Security-Policy-Report-Only`` instead of the
    enforcing header. Useful for auditing before switching to enforce.
    Ignored unless ``PLANTPAL_ENABLE_CSP`` is also set.

Notes on the Server header
--------------------------
Uvicorn prints ``Server: uvicorn`` on every response, which leaks the
server name. The cleanest fix is passing ``--no-server-header`` to uvicorn
(already done in run.sh + Dockerfile CMD). Stripping it from middleware
alone is unreliable because uvicorn writes the header at the protocol
layer if the response doesn't already contain one.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ENV_ALLOWED_HOSTS = "PLANTPAL_ALLOWED_HOSTS"
_ENV_ENABLE_CSP = "PLANTPAL_ENABLE_CSP"
_ENV_CSP_REPORT_ONLY = "PLANTPAL_CSP_REPORT_ONLY"

# Permissive CSP. Each directive earns its spot:
#   default-src 'self'               -> fallback for anything unlisted
#   script-src                       -> includes 'unsafe-inline' for the
#                                       inline tw-config <script> block
#                                       in the templates. Tailwind Play
#                                       lives on cdn.tailwindcss.com.
#   style-src                        -> 'unsafe-inline' for Tailwind's
#                                       generated style tag + Google Fonts
#                                       CSS at fonts.googleapis.com.
#   font-src                         -> fonts.gstatic.com hosts the actual
#                                       font files for Google Fonts.
#   img-src 'self' data: blob:       -> app images + inline SVG data URIs.
#   frame-ancestors 'none'           -> duplicates X-Frame-Options: DENY,
#                                       but frame-ancestors is the modern
#                                       spec; both are cheap.
#   base-uri 'self'; form-action 'self' -> defense-in-depth; prevents
#                                          injection of alternate action
#                                          targets.
_PERMISSIVE_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)


def _parse_allowed_hosts(raw: str | None) -> list[str]:
    """Split + trim the env var. Empty/absent -> wildcard (with a warning
    logged by the caller)."""
    if not raw:
        return ["*"]
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return hosts or ["*"]


def _csp_enabled() -> bool:
    return os.environ.get(_ENV_ENABLE_CSP, "") == "1"


def _csp_report_only() -> bool:
    return os.environ.get(_ENV_CSP_REPORT_ONLY, "") == "1"


# ---------------------------------------------------------------------------
# Wire-up
# ---------------------------------------------------------------------------


def install_security_middleware(app: FastAPI) -> None:
    """Attach all security middleware to ``app``. Idempotent for tests."""
    allowed_hosts = _parse_allowed_hosts(os.environ.get(_ENV_ALLOWED_HOSTS))
    if allowed_hosts == ["*"]:
        # One-shot warning so the default is visible but not noisy in logs.
        logger.warning(
            "security: PLANTPAL_ALLOWED_HOSTS not set, accepting any Host "
            "header. Set a comma-separated list for production (example: "
            "'plantpal.local,*.ts.net,127.0.0.1')."
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # Header middleware is registered LAST so it becomes the outermost
    # wrapper (Starlette prepends to its middleware list). That way the
    # 400 responses TrustedHost emits still get the security headers
    # applied, which is what we want.
    enable_csp = _csp_enabled()
    csp_header_name = (
        "Content-Security-Policy-Report-Only" if _csp_report_only() else "Content-Security-Policy"
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        _apply_headers(response.headers, enable_csp=enable_csp, csp_header_name=csp_header_name)
        return response


def _apply_headers(
    headers: Iterable[tuple[str, str]],  # duck-typed; Starlette's MutableHeaders
    *,
    enable_csp: bool,
    csp_header_name: str,
) -> None:
    """Set our security headers on an outgoing response.

    Uses setdefault semantics so a route handler can still override (e.g. a
    future embed-friendly page could loosen X-Frame-Options intentionally).
    """
    headers.setdefault("X-Content-Type-Options", "nosniff")  # type: ignore[attr-defined]
    headers.setdefault("X-Frame-Options", "DENY")  # type: ignore[attr-defined]
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")  # type: ignore[attr-defined]
    headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")  # type: ignore[attr-defined]
    if enable_csp:
        headers.setdefault(csp_header_name, _PERMISSIVE_CSP)  # type: ignore[attr-defined]


__all__ = ["install_security_middleware"]
