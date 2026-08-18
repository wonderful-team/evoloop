"""值守渠道（duty）— 客服值守的主动轮巡渠道。

与 ``input/``（被动接收）和 ``output/``（投递）不同，值守是"主动拉取 + 处理 + 回复"
的完整闭环：定时轮巡扫描新消息 → 增量派发 Agent → Agent 回复客户 / 升级操作者。

结构：
- ``base.py``            DutyChannel 基类 + ContactDelta/RawInbound
- ``wecom/``             企业微信值守实现（channel.py + common/read/reply/scan_all）
- ``scheduler.py``       run_duty_poll 调度接入
"""

from app.core.channel.duty.base import (
    ContactDelta,
    DutyChannel,
    RawInbound,
)
from app.core.channel.duty.wecom.channel import WeComDutyChannel


def is_duty_source(source: str | None) -> bool:
    """值守场景判定：source 是否为值守场景（固定场景标识）。

    场景标识是固定的（与渠道无关）：语音 = "voice"、网页 = "web"、
    移动 = "mobile"、值守 = "duty"。具体渠道（wecom/slack/dingtalk）是
    用户可选的实现，由 metadata.channel 记录，不影响场景判定。

    兼容历史命名：duty 前缀/后缀的旧 source（如 wecom_duty）也识别，
    避免历史数据判定失效。
    """
    s = source or ""
    return s == "duty" or s.startswith("duty_") or s.endswith("_duty")


__all__ = [
    "ContactDelta",
    "DutyChannel",
    "RawInbound",
    "WeComDutyChannel",
    "is_duty_source",
]
