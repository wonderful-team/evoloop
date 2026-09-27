"""Unit tests for VoiceChannelLifecycleSubscriber (APP_STARTED WS wiring)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.channel.output.voice_channel import VoiceChannel
from app.core.voice.event.subscribers import VoiceChannelLifecycleSubscriber


@pytest.fixture(autouse=True)
def _reset_binding():
    prev = (VoiceChannel._manager, VoiceChannel._envelope_fn, VoiceChannel._message_type)
    VoiceChannel._manager = None
    VoiceChannel._envelope_fn = None
    VoiceChannel._message_type = None
    yield
    (VoiceChannel._manager, VoiceChannel._envelope_fn, VoiceChannel._message_type) = prev


async def test_app_started_binds_voice_channel_transport():
    VoiceChannelLifecycleSubscriber()
    await VoiceChannelLifecycleSubscriber().on_application_started(SimpleNamespace(data={}))

    assert VoiceChannel._manager is not None
    assert VoiceChannel._envelope_fn is not None
    assert VoiceChannel._message_type is not None
