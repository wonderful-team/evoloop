import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.utils.json import dumps


class ContextFilter(logging.Filter):
    """
    Inject context variables into the log record.

    防御性实现（2026-09-19 测试污染事故 + 生产等价风险）：日志 filter 绝不
    向调用方抛异常——ctx 可能是测试替身/无 thread_id 的局部对象；filter 崩溃
    会把无关的日志行变成业务调用失败（实测炸穿 tool wrapper → 9 个无辜测试 FAILED）。
    """

    def filter(self, record):
        try:
            ctx = ContextManager.current()
            record.thread_id = getattr(ctx, "thread_id", None) or "-"
            project_id = getattr(ctx, "project_id", None)
            record.project_id = project_id if project_id is not None else "-"
        except Exception:
            record.thread_id = "-"
            record.project_id = "-"
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
    handler.addFilter(context_filter)

    # DB driver diagnostics are extremely verbose. Keep them quiet even when
    # the application is running with LOG_LEVEL=DEBUG.
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # 第三方噪声日志仅在非 DEBUG 时压到 WARNING，保证 LOG_LEVEL 是唯一权威开关。
    # 设 LOG_LEVEL=DEBUG 时不抑制，让这些库的 DEBUG 也能输出。
    if str(settings.LOG_LEVEL).upper() != "DEBUG":
        for name in (
            "uvicorn.access",
            "neo4j",
            "httpx",
            "httpcore",
            "openai",
            "mcp",
            "watchfiles",
            "websockets.client",
            "websockets.server",
            "huey.consumer",
            "hpack",
            "hpack.hpack",
            "fsevents",
        ):
            logging.getLogger(name).setLevel(logging.WARNING)

    # 应用日志级别跟随配置（LOG_LEVEL，默认 INFO）。需要细粒度调试时在 .env
    # 设 LOG_LEVEL=DEBUG，或用 worker 的 --verbose 手动开启。
    logging.getLogger("app").setLevel(settings.LOG_LEVEL)


logger = logging.getLogger("evoloop")
setup_logging()
