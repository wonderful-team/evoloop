"""Unit tests for DutyChannelLifecycleSubscriber (APP_STARTED channel registration)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.channel import channel_registry
from app.core.channel.duty.event.subscribers import DutyChannelLifecycleSubscriber


@pytest.fixture(autouse=True)
def _clear_wecom():
    channel_registry._channels.pop("wecom_duty", None)
    yield
    channel_registry._channels.pop("wecom_duty", None)


async def test_app_started_registers_wecom_duty_channel():
    DutyChannelLifecycleSubscriber()
    await DutyChannelLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))

    assert channel_registry.has("wecom_duty")


async def test_registration_is_idempotent():
    DutyChannelLifecycleSubscriber()
    sub = DutyChannelLifecycleSubscriber()
    await sub.on_application_started(SimpleNamespace(data={}))
    await sub.on_application_started(SimpleNamespace(data={}))

    assert channel_registry.has("wecom_duty")
