"""Unit tests for RoutingLifecycleSubscriber (APP_STARTED L0 init-spec dispatch)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.core.routing.event.subscribers import RoutingLifecycleSubscriber


async def test_app_started_dispatches_l0_init_spec():
    RoutingLifecycleSubscriber()
    with patch("app.core.routing.tasks.build_l0_init_spec.delay") as delay:
        await RoutingLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))
        delay.assert_called_once()


async def test_app_started_survives_dispatch_failure():
    RoutingLifecycleSubscriber()
    with patch(
        "app.core.routing.tasks.build_l0_init_spec.delay",
        side_effect=RuntimeError("queue down"),
    ):
        # 不应抛出异常（handler 内 try/except 兜底）
        await RoutingLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))
