"""Pull-mode Init Spec delivery (post §6.4.2 simplification): real cache + real handler.

No mocks: exercises the actual ``route_init`` handler against the real
embedded cache singleton to prove the 200 / unchanged / 202-pending states
after the ``voice.init_updated`` push was removed. Client-side NSTimer/reconnect
pull is covered by cmake build + §14.6 on-machine E2E, not here.
"""

from __future__ import annotations

import json

import pytest

from app.api.routes.route import route_init
from app.core.routing.tasks import SPEC_CACHE_KEY


@pytest.mark.asyncio
async def test_route_init_pull_states():
    from app.infrastructure.cache import cache

    await cache.delete(SPEC_CACHE_KEY)

    empty = await route_init(version="", platform="macos")
    assert getattr(empty, "status_code", None) == 202, "empty cache → 202 pending"

    await cache.set(SPEC_CACHE_KEY, json.dumps({"version": "v1", "actions": []}))

    full = await route_init(version="", platform="macos")
    assert full["version"] == "v1" and full["unchanged"] is False

    same = await route_init(version="v1", platform="macos")
    assert same == {"version": "v1", "unchanged": True}

    newer = await route_init(version="v0", platform="macos")
    assert newer["version"] == "v1" and newer["unchanged"] is False

    await cache.delete(SPEC_CACHE_KEY)
