"""
Voice Lifecycle Handlers
========================

Wires the VoiceChannel WebSocket transport on ``APP_STARTED`` so Agent TTS
streaming and macro presenters can push to WS regardless of which code path
triggered the Agent — not just the first ``voice.route``.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class VoiceChannelLifecycleSubscriber:
    """Lifecycle handlers for the voice channel WS transport."""

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        try:
            from app.api.routes.voice_ws import _envelope as _ws_envelope
            from app.core.channel.output.voice_channel import VoiceChannel
            from app.core.schemas.canonical import MessageType as _MsgType
            from app.core.voice.connection import manager as _ws_manager

            VoiceChannel.bind(
                manager=_ws_manager,
                envelope_fn=_ws_envelope,
                message_type=_MsgType,
            )
            logger.info("[Voice] VoiceChannel WS transport wired")
        except (ImportError, TypeError) as e:
            logger.warning("[Voice] VoiceChannel wiring failed (non-critical): %s", e)
