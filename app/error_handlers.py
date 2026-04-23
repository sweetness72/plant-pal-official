"""
Last-resort exception handler.

``HTTPException``, ``RequestValidationError``, etc. stay on Starlette's
more specific handlers (MRO wins). This one only runs for errors that
don't have a dedicated handler — typically unexpected bugs. One
``logger.exception`` per failure (with stack trace), no log on 4xx
validation noise.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("plantpal.errors")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception method=%s path=%s",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


__all__ = ["register_exception_handlers"]
