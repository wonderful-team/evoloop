"""hitl → monitoring 的依赖倒置缝（ActivitySink）。

hitl 领域在发起/清除 HITL 等待状态时调用观测回调，避免反向依赖监测层
（``app.core.monitoring.activity``）。实现由 monitoring 侧在
``app.core.monitoring.hitl_sink`` 注册；装配策略与 ``engine_runtime`` 一致：
首次 get 惰性装配、幂等、加锁。环破除后 hitl 对 monitoring 归零，仅保留
monitoring → hitl 的合法单向（观测领域类型）。
"""

import importlib
import logging
import threading
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ActivitySink(Protocol):
    async def set_human_request(self, *, thread_id: str, request_data: dict) -> None:
        """记录一个 HITL 请求处于等待人类应答状态。"""
        ...

    async def clear_human_request(self, thread_id: str) -> None:
        """清除该会话的 HITL 等待状态。"""
        ...


_sink: ActivitySink | None = None
# RLock：get_activity_sink 持锁惰性装配时，模块副作用 register() 会重入加锁。
_sink_lock = threading.RLock()


def register_activity_sink(sink: ActivitySink) -> None:
    """注入观测实现（monitoring 侧注册 / 测试注入 fake）。"""
    global _sink
    with _sink_lock:
        _sink = sink


def reset_activity_sink() -> None:
    """清除已注册观测实现，主要用于测试隔离。"""
    global _sink
    with _sink_lock:
        _sink = None


def get_activity_sink() -> ActivitySink:
    """返回已注册的观测实现；未注册时惰性装配一次并缓存。

    仅当实现模块缺失或未注册时才抛错（Fail-Fast，便于测试直接注入 fake）。
    """
    global _sink
    if _sink is None:
        with _sink_lock:
            if _sink is None:
                mod = importlib.import_module("app.core.monitoring.hitl_sink")
                register = getattr(mod, "register", None)
                if callable(register):
                    register()
    if _sink is None:
        raise RuntimeError(
            "ActivitySink not registered: import app.core.monitoring.hitl_sink "
            "or inject via register_activity_sink() (e.g. pytest fixture)."
        )
    return _sink
