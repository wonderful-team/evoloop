import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.context.manager import ContextManager, EvoContext
from app.core.context.plugins import plugin_registry
from app.core.identity import identity_service
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)


class ContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to initialize EvoContext for every HTTP request.
    Extracts:
    - Trace ID (X-Trace-ID)
    - User Identity (Authorization Header - simplified parse)
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 1. Extract IDs
        trace_id = request.headers.get("X-Trace-ID", gen_uuid())
        request_id = request.headers.get("X-Request-ID", gen_uuid())

        # 2. Attempt Identify User (Best Effort)
        # We don't enforce auth here (deps.py does that), we just populate context if possible.
        member_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                member_id = await identity_service.resolve_member_id_from_token(token)
                # Store on request.state so route deps can reuse without re-resolving
                request.state.resolved_member_id = member_id
                request.state.resolved_token = token
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        # 3. Create Context
        ctx = EvoContext(
            request_id=request_id,
            trace_id=trace_id,
            timestamp=start_time,
            member_id=member_id,
            thread_id=request.headers.get("X-Thread-ID")  # Optional: thread hint
        )

        # 4. Set Context FIRST so plugins relying on ContextManager.current() work correctly
        token = ContextManager.set(ctx)

        try:
            # 3b. Hydrate Subconscious Plugins
            plugin_registry.hydrate_context(ctx)

            response = await call_next(request)

            # Inject Headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id

            return response
        finally:
            ContextManager.reset(token)
