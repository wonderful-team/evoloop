from typing import Any, Optional

_graph: Optional[Any] = None

def set_graph(g: Any):
    global _graph
    _graph = g

def get_graph() -> Any:
    return _graph
