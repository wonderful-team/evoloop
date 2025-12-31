import logging
import sys
import contextvars
from datetime import datetime, timezone
from app.utils import json as json_utils
from app.utils.context import get_context, set_context
from app.core.config import settings

# Re-export set_context/get_context for backwards compatibility if needed, 
# or consumers should import from utils.context directly.
# For now, we keep them here but implementation delegates to utils.


# set_context and get_context are imported from app.utils.context

class ContextFilter(logging.Filter):
    """
    Inject context variables into the log record.
    """
    def filter(self, record):
        ctx = get_context()
        record.thread_id = ctx.get("thread_id", "-")
        record.project_id = ctx.get("project_id", "-")
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
            "project_id": getattr(record, "project_id", "-")
        }
        
        # Include exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json_utils.dumps(log_obj)

def setup_logging():
    """
    Configure the logging for the application.
    """
    handler = logging.StreamHandler(sys.stderr)
    
    if settings.APP_ENV == "development":
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


logger = logging.getLogger("evoloop")
setup_logging()
