import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.utils.json import dumps


class ContextFilter(logging.Filter):
    """
    Inject context variables into the log record.
    """

    def filter(self, record):
        ctx = ContextManager.current()
        record.thread_id = ctx.thread_id or "-"
        record.project_id = ctx.project_id if ctx.project_id is not None else "-"
        return True


class JSONFormatter(logging.Formatter):
    """
    Format logs as JSON lines.
    """

    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "thread_id": getattr(record, "thread_id", "-"),
            "project_id": getattr(record, "project_id", "-"),
        }

        # Include exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return dumps(log_obj)


def setup_logging():
    """
    Configure the logging for the application.
    """
    handler = logging.StreamHandler(sys.stderr)

    if settings.ENVIRONMENT == "local":
        # Dev: Human Readable but with Context
        formatter = logging.Formatter(
            "%(asctime)s - [%(thread_id)s|%(project_id)s] - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        # Prod: JSON
        formatter = JSONFormatter()

    handler.setFormatter(formatter)

    # Root Logger
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)
    root.handlers = [handler]

    # Add Filter
    context_filter = ContextFilter()
    handler.addFilter(context_filter) # Filter on handler ensuring it applies to formatter

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)
    logging.getLogger("huey.consumer").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("hpack.hpack").setLevel(logging.WARNING)
    logging.getLogger("fsevents").setLevel(logging.WARNING)

    # Enable detailed logs for our app
    logging.getLogger("app").setLevel(logging.DEBUG)


logger = logging.getLogger("evoloop")
setup_logging()
