import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.context.manager import ContextManager, EvoContext
from app.core.context.plugins import plugin_registry
from app.core.identity import decode_local_jwt
from app.utils.id import gen_uuid


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
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                # Try local decode first (fast)
                payload = decode_local_jwt(token)
                if payload:
                    user_id = payload.get("member_id") or payload.get("sub")
            except Exception:
                pass

        # 3. Create Context
        ctx = EvoContext(
            request_id=request_id,
            trace_id=trace_id,
            timestamp=start_time,
            user_id=str(user_id) if user_id else None,
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
