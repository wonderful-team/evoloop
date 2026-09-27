"""MCP 单元测试共享 fixture。

server-runner 生命周期（capabilityPackages 稳定性修复）：runner 是常驻任务，
测试结束后必须经 stop 事件干净退出，否则 pytest-asyncio 关闭 event loop 时
runner 泄漏（Task was destroyed / 挂死）。
"""

from __future__ import annotations

import pytest

from app.core.mcp.client.manager import mcp_client_manager


@pytest.fixture(autouse=True)
async def _cleanup_mcp_runners():
    """每个测试结束后断开所有 MCP 连接（runner stop → 同任务清理）。"""
    yield
    try:
        await mcp_client_manager.disconnect_all()
    except Exception:
        pass
    # 兜底：强制取消仍存活的 runner（防御 runner 挂在不可取消的等待上）
    for name, task in list(mcp_client_manager._runners.items()):
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        mcp_client_manager._runners.pop(name, None)
