"""skill 激活降级语义契约测试（2026-09-18，记账与连接解耦）。

锁定（外部连接不可靠是常态）：
1. SOP 正文已交付即记账 loaded_packages + packages_dirty（与 server 连接状态解耦）；
2. server 故障 → 结构化降级报告：可用比例 + 自愈说明 + 防绕过指引；
3. server 正常 → 既有 connected: yes 报告不变。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.context.schemas import ContextMetadata


def _resolved(name: str, server: str) -> dict:
    return {
        "name": name,
        "content": "# SOP",
        "base_dir": "/x",
        "files": [],
        "capability": {
            "domain": "mall_ops",
            "tools": [{"mcp_server": server, "include": ["list_goods"]}],
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("connected", [False, True])
async def test_activation_records_loaded_regardless_of_connection(
    connected, monkeypatch
):
    from app.core.engine.tools.react_skill import _activate_package_capability

    ctx = MagicMock()
    ctx.metadata = ContextMetadata()
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    monkeypatch.setattr(
        "app.core.mcp.mcp_client_manager.ensure_connected",
        AsyncMock(return_value=connected),
    )

    note = await _activate_package_capability(
        _resolved("mall-products", "mall-backend-ops")
    )

    # 记账与连接状态解耦：两种情况下包都进入 loaded（自愈前提）
    assert ctx.metadata.loaded_packages == ["mall-products"]
    assert ctx.metadata.packages_dirty is True

    if connected:
        assert "connected: yes" in note
        assert "DEGRADED" not in note
    else:
        assert "connected: FAILED" in note
        assert "DEGRADED" in note
        # 行动指引：自愈说明 + 防绕过
        assert "automatically once they reconnect" in note
        assert "Do NOT try to access MCP internals" in note


@pytest.mark.asyncio
async def test_activation_idempotent_and_non_package_noop(monkeypatch):
    from app.core.engine.tools.react_skill import _activate_package_capability

    ctx = MagicMock()
    ctx.metadata = ContextMetadata(loaded_packages=["mall-products"])
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    monkeypatch.setattr(
        "app.core.mcp.mcp_client_manager.ensure_connected",
        AsyncMock(return_value=True),
    )

    # 非包技能：无 capability → 空注记，不动记账
    plain = {
        "name": "plain",
        "content": "c",
        "base_dir": "/x",
        "files": [],
        "capability": None,
    }
    assert await _activate_package_capability(plain) == ""

    # 幂等：已加载不重复记账
    note = await _activate_package_capability(
        _resolved("mall-products", "mall-backend-ops")
    )
    assert ctx.metadata.loaded_packages == ["mall-products"]
    assert "mall-backend-ops" in note
