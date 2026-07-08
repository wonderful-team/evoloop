"""
EvoLoop Message System - 统一消息处理系统

提供消息分类、持久化和推送的完整解决方案。
"""

import importlib

_module_lazy = {
    "MessageCategory": "app.core.engine.message.category",
    "MessageClassifier": "app.core.engine.message.classifier",
    "MessageHandler": "app.core.engine.message.handler",
    "BlockMapper": "app.core.engine.message.mapper",
    "MessagePersistencePolicy": "app.core.engine.message.persistence",
    "MessagePublisher": "app.core.engine.message.publisher",
    "MessageBlock": "app.core.engine.message.schemas",
    "ToolBlock": "app.core.engine.message.schemas",
    "MessageStreamPolicy": "app.core.engine.message.stream",
}

__all__ = list(_module_lazy.keys())


def __getattr__(name):
    module_path = _module_lazy.get(name)
    if module_path is not None:
        mod = importlib.import_module(module_path)
        attr = getattr(mod, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
