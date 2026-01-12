from typing import Any

_graph: Any | None = None

def set_graph(g: Any):
    global _graph
    _graph = g

def get_graph() -> Any:
    return _graph
