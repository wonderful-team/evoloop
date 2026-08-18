"""Global exception handlers that wrap all API errors in a uniform envelope.

Envelope shape::

    {"success": false, "code": "...", "message": "...", "detail": <original>}

``detail`` keeps its original value (string or dict) so existing frontends that
read ``error.body.detail`` keep working unchanged; ``code`` / ``message`` are
new top-level fields for progressive adoption.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Benefit errors carry extra fields the frontend relies on (feature/upgrade_url…).
_DETAIL_DICT_COPY_KEYS = (
    "code",
    "feature",
    "feature_name",
    "message",
    "required_plan",
    "current_level",
    "upgrade_url",
    "errors",
)


def _http_error_payload(status_code: int, detail) -> dict:
    code = f"HTTP_{status_code}"
    message = str(detail)
    extra: dict = {}

    if isinstance(detail, dict):
        if detail.get("code"):
            code = str(detail["code"])
        if detail.get("message"):
            message = str(detail["message"])
        for key in _DETAIL_DICT_COPY_KEYS:
            if key in detail:
                extra[key] = detail[key]

    payload: dict = {
        "success": False,
        "code": code,
        "message": message,
        "detail": detail,
    }
    payload.update(extra)
    return payload


async def http_exception_handler(request: Request, exc: StarletteHTTPException):  # noqa: ARG001
    return JSONResponse(
        status_code=exc.status_code,
        content=_http_error_payload(exc.status_code, exc.detail),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):  # noqa: ARG001
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(x) for x in first.get("loc", [])) if first else ""
    msg = first.get("msg", "Invalid request") if first else "Invalid request"
    detail = f"{loc}: {msg}" if loc else msg
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "code": "VALIDATION_ERROR",
            "message": detail,
            "detail": detail,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: ARG001
    logger.exception("Unhandled exception in request %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "detail": "Internal server error",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the uniform error envelope handlers to a FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
