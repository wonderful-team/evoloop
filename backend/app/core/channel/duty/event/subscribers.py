"""
Duty Channel Lifecycle Handlers
===============================

Registers the wecom_duty output channel on ``APP_STARTED``. The duty Agent runs
in the API process, so its output channel must be registered here; the worker
process does not publish ``APP_STARTED`` and does not need it.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class DutyChannelLifecycleSubscriber:
    """Lifecycle handlers for duty output channels."""

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        try:
            from app.core.channel import channel_registry
            from app.core.channel.duty.wecom.channel import WeComDutyChannel

            if not channel_registry.has("wecom_duty"):
                channel_registry.register(WeComDutyChannel())
                logger.info("[Duty] wecom_duty 输出渠道已注册 (API)")
            else:
                logger.debug("[Duty] wecom_duty 输出渠道已存在，跳过")
        except Exception as e:
            logger.warning(
                f"[Duty] wecom_duty 渠道注册失败 (非关键): {e}", exc_info=True
            )
