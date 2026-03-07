import os
import time
import logging
from typing import Any

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


def get_graph() -> Any:
    global _graph, _config_path, _last_load_time, _checkpointer
    
    # Hot Reload Logic
    if _config_path and os.path.exists(_config_path):
        mtime = os.path.getmtime(_config_path)
        if mtime > _last_load_time:
            logger.info(f"[HotReload] Detected change in {_config_path}. Rebuilding graph...")
            try:
                from app.core.engine.graph_builder import GraphBuilder
                builder = GraphBuilder()
                # Re-build with existing checkpointer to maintain state capability
                new_graph = builder.build(_config_path, checkpointer=_checkpointer)
                set_graph(new_graph, _config_path, _checkpointer)
            except Exception as e:
                logger.error(f"[HotReload] Failed to reload graph: {e}")
                
    return _graph
