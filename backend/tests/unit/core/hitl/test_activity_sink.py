"""ActivitySink 协议、装配与 monitoring 适配器测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.hitl.activity_sink import (
    ActivitySink,
    get_activity_sink,
    register_activity_sink,
    reset_activity_sink,
)


def test_protocol_accepts_monitor_adapter():
    from app.core.monitoring.hitl_sink import ActivityMonitorSink

    assert isinstance(ActivityMonitorSink(), ActivitySink)


def test_register_then_get_returns_same_instance():
    fake = MagicMock()
    try:
        register_activity_sink(fake)
        assert get_activity_sink() is fake
    finally:
        reset_activity_sink()


def test_get_activity_sink_assembles_monitor_adapter_when_unregistered():
    """未注册时惰性装配 monitoring 侧适配器（monitoring → hitl 单向）。"""
    from app.core.monitoring.hitl_sink import ActivityMonitorSink

    try:
        reset_activity_sink()
        sink = get_activity_sink()
        assert isinstance(sink, ActivityMonitorSink)
    finally:
        reset_activity_sink()


@pytest.mark.asyncio
async def test_monitor_adapter_proxies_activity_monitor():
    from app.core.monitoring.hitl_sink import ActivityMonitorSink

    with patch("app.core.monitoring.hitl_sink.activity_monitor") as mock_mon:
        mock_mon.set_human_request = AsyncMock()
        mock_mon.clear_human_request = AsyncMock()

        sink = ActivityMonitorSink()
        await sink.set_human_request(thread_id="t-1", request_data={"type": "text"})
        await sink.clear_human_request("t-1")

    mock_mon.set_human_request.assert_awaited_once_with("t-1", {"type": "text"})
    mock_mon.clear_human_request.assert_awaited_once_with("t-1")
