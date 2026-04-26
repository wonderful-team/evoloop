"""
EvoCloud WebSocket Message Handlers
====================================

Subscribers to the unified ``WebSocketMessageReceivedEvent``.

Each handler filters by ``msg_type`` internally and processes only the
messages it cares about. This architecture follows the Open/Closed Principle:
adding a new Gateway message type does NOT require modifying the transport
layer (``websocket_link.py``) — just add a new subscriber.
"""

import asyncio
import logging

from app.core.engine.events import WebSocketMessageReceivedEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.evocloud.manager import evocloud_manager
from app.core.evocloud.schemas import QueryResponse
from app.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Query Handler — Delegates to registered query callback
# =============================================================================

@event_register()
class QueryWebSocketHandler:
    """
    Handles ``query`` messages from Gateway.

    Delegates to the query handler registered on the EvoCloudWebSocketLink.
    """

    @event_subscribe("websocket.message_received")
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type != "query":
            return
        await self._handle_query(event.raw)

    async def _handle_query(self, data: dict) -> None:
        link = evocloud_manager.link
        if link is None:
            logger.warning("[EvoCloud] Query received but link not available")
            return

        request_id = data.get("request_id")
        query_data = data.get("data", {})
        query_type = query_data.get("query_type")
        thread_id = query_data.get("thread_id")
        params = query_data.get("params", {})

        logger.debug(f"[EvoCloud] Query request: {query_type} (req_id={request_id})")

        result = None
        error = None

        try:
            if link._query_handler:
                if asyncio.iscoroutinefunction(link._query_handler):
                    result = await link._query_handler(query_type, thread_id, params)
                else:
                    result = await run_in_thread(link._query_handler, query_type, thread_id, params)
            else:
                error = "Query handler not registered"
        except Exception as e:
            logger.error(f"[EvoCloud] Query error: {e}")
            error = str(e)

        response = QueryResponse(
            request_id=request_id,
            data={
                "code": 0 if error is None else 500,
                "message": error or "success",
                "request_id": request_id,
                "data": result,
            },
        )
        await link.send_message(response.model_dump())


# =============================================================================
# 3. Init Handler — Updates client_id on the link
# =============================================================================

@event_register()
class InitWebSocketHandler:
    """
    Handles ``init`` messages from Gateway.

    Updates ``client_id`` on the EvoCloudWebSocketLink instance.
    """

    @event_subscribe("websocket.message_received")
    async def on_ws_message(self, event: WebSocketMessageReceivedEvent) -> None:
        if event.msg_type != "init":
            return

        client_id = event.payload.get("client_id")
        if not client_id:
            return

        link = evocloud_manager.link
        if link:
            link.client_id = client_id
            logger.info(f"[EvoCloud] client_id updated via event: {client_id}")
