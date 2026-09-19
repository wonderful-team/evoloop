import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context.manager import ContextManager, EvoContext
from app.core.context.plugins import plugin_registry
from app.core.identity import identity_service
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


def _header_bytes(scope: Scope, name: str) -> str | None:
    target = name.lower().encode()
    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            return value.decode("latin-1")
    return None


class ContextMiddleware:
    """Pure-ASGI EvoContext middleware (no BaseHTTPMiddleware).

    BaseHTTPMiddleware spawns the downstream app in a separate task and
    cancels it on client disconnect; when the cancellation lands inside an
    await in the handler's session teardown, the checked-out DB connection
    is never returned (observed as one leaked pool connection per aborted
    request, sqlalchemy#12710 fairy abandonment). A plain ASGI middleware
    keeps the downstream app in the same coroutine, so FastAPI's standard
    AsyncExitStack teardown runs on cancel and connections return to the
    pool. Contextvars propagate natively within the same coroutine, so
    ContextManager.set/reset keep working unchanged.
    """

    app: ASGIApp

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        trace_id = _header_bytes(scope, "X-Trace-ID") or gen_uuid()
        request_id = _header_bytes(scope, "X-Request-ID") or gen_uuid()

        member_id = None
        auth_header = _header_bytes(scope, "Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                member_id = await identity_service.resolve_member_id_from_token(token)
                state = scope.setdefault("state", {})
                state["resolved_member_id"] = member_id
                state["resolved_token"] = token
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        ctx = EvoContext(
            request_id=request_id,
            trace_id=trace_id,
            timestamp=start_time,
            member_id=member_id,
            thread_id=_header_bytes(scope, "X-Thread-ID"),
        )

        context_token = ContextManager.set(ctx)
        try:
            await plugin_registry.ahydrate_context(ctx)

            async def send_with_ids(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers") or [])
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                    headers.append((b"x-trace-id", trace_id.encode("latin-1")))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, send_with_ids)
        finally:
            ContextManager.reset(context_token)
