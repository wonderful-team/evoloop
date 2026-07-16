"""Loopback guard shared by the voice WebSocket and HTTP routes.

The whole backend is expected to bind `127.0.0.1` (see design §8). This guard
is a defence-in-depth layer on top of that binding.
"""

from __future__ import annotations

import ipaddress
import logging

from fastapi import HTTPException, Request, WebSocket

logger = logging.getLogger(__name__)

_LOOPBACK_NAMES = {"localhost", "testclient"}  # "testclient": Starlette TestClient host


def is_loopback_host(host: str | None) -> bool:
    """Return True if `host` is a loopback address."""
    if not host:
        return False
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def require_loopback(request: Request) -> None:
    """FastAPI dependency (HTTP): reject non-loopback clients with 403."""
    host = request.client.host if request.client else None
    if not is_loopback_host(host):
        logger.warning("[voice] rejected non-loopback HTTP client: %s", host)
        raise HTTPException(status_code=403, detail="loopback only")


async def enforce_loopback_ws(websocket: WebSocket) -> bool:
    """Return True if the WS client is loopback; otherwise close(4403) and False."""
    host = websocket.client.host if websocket.client else None
    if not is_loopback_host(host):
        logger.warning("[voice] rejected non-loopback WS client: %s", host)
        await websocket.close(code=4403, reason="loopback only")
        return False
    return True
