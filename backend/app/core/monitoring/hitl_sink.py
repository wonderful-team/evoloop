"""monitoring 侧 ActivityMonitor 的 ActivitySink 适配器（hitl 单向装配）。

hitl 不再引用 monitoring；本模块成为 monitoring → hitl 方向的注册点，
把 ActivityMonitor 的能力注入 hitl 定义的 ``ActivitySink`` 协议。
"""

from app.core.hitl.activity_sink import register_activity_sink
from app.core.monitoring.activity import activity_monitor


class ActivityMonitorSink:
    async def set_human_request(self, *, thread_id: str, request_data: dict) -> None:
        await activity_monitor.set_human_request(thread_id, request_data)

    async def clear_human_request(self, thread_id: str) -> None:
        await activity_monitor.clear_human_request(thread_id)


def register() -> None:
    """装配适配器（幂等）；模块 import 时自动执行一次。"""
    register_activity_sink(ActivityMonitorSink())


register()
