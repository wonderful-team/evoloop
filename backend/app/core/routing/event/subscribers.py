"""
Routing Lifecycle Handlers
==========================

Dispatches the L0 init-spec build on ``APP_STARTED``. The Huey worker writes the
enriched RouteCatalog to the shared cache; the API-side L0 matcher lazily loads
from the same cache on the first route request, so the build can be fire-and-forget.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class RoutingLifecycleSubscriber:
    """Lifecycle handlers for the routing subsystem."""

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        try:
            from app.core.routing import tasks as routing_tasks

            routing_tasks.build_l0_init_spec.delay()
            logger.info("[Routing] L0 Init Spec build dispatched")
        except Exception as e:
            logger.warning(f"[Routing] L0 Init Spec dispatch failed (non-critical): {e}", exc_info=True)
