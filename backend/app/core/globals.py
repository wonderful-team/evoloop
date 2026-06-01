import logging
import os
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_graph: Any | None = None
_config_path: str | None = None
_last_load_time: float = 0
_checkpointer: Any | None = None


def set_graph(g: Any, config_path: str | None = None, checkpointer: Any | None = None):
    global _graph, _config_path, _last_load_time, _checkpointer
    _graph = g
    _config_path = config_path
    _last_load_time = time.time()
    if checkpointer:
        _checkpointer = checkpointer


def init_agent_graph(checkpointer: Any | None = None) -> Any:
    """Initialize and set the Agent Graph from the YAML config."""
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.core.engine.graph_builder import GraphBuilder

    if checkpointer is None:
        checkpointer = db_resource_manager.checkpointer

    builder = GraphBuilder()
    
    # Try different paths for robustness (e.g., worker vs main process context)
    base_dir = os.path.dirname(__file__)
    config_paths = [
        os.path.join(base_dir, "engine/config/agent_main.yaml"),
        os.path.join(base_dir, "core/engine/config/agent_main.yaml")
    ]
    
    config_path = next((p for p in config_paths if os.path.exists(p)), config_paths[1])

    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    return graph


def get_graph() -> Any:
    global _graph, _config_path, _last_load_time, _checkpointer

    if _graph is None:
        try:
            logger.info("Initializing Agent Graph lazily (e.g. within worker process)...")
            init_agent_graph()
        except Exception as e:
            logger.error(f"Failed to lazily initialize Agent Graph: {e}", exc_info=True)

        # Auto discover event handlers to ensure worker process receives event broadcasts
        try:
            from app.core.events.discovery import auto_discover_handlers
            auto_discover_handlers()
            logger.info("Lazy discovery of event handlers complete in worker.")
        except Exception as ex:
            logger.warning(f"Lazy discovery of event handlers failed (non-critical): {ex}")

    # Hot Reload Logic
    if settings.ENVIRONMENT == "local" and _config_path and os.path.exists(_config_path):
        mtime = os.path.getmtime(_config_path)
        if mtime > _last_load_time:
            logger.info(f"[HotReload] Detected change in {_config_path}. Rebuilding graph...")
            try:
                init_agent_graph(checkpointer=_checkpointer)
            except Exception as e:
                logger.error(f"[HotReload] Failed to reload graph: {e}")

    return _graph
