"""
Sandbox Lifecycle Handlers
==========================

Tears down the sandbox singleton (stops the docker container when in docker
mode) on ``APP_STOPPING``. Registered via ``@event_register`` + discovery, so
there is no hardcoded dependency in ``app/main.py``.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class SandboxLifecycleSubscriber:
    """Lifecycle handlers for the execution sandbox."""

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_application_stopping(self, event):
        from app.core.execution.sandbox.factory import SandboxFactory

        SandboxFactory.reset()
        logger.info("[Sandbox] Sandbox torn down")
