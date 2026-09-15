"""任务域事件接线（订阅者注册入口）。"""

from app.domain.tasks.event import (
    subscribers,  # noqa: F401 — 导入触发 @event_register 注册
)
