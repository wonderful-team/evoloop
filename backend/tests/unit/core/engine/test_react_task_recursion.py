"""React `agent` tool recursion guard tests (对齐 OpenCode 子代理默认 deny task)."""

from unittest.mock import AsyncMock, patch

from app.core.engine.tools.react_task import MAX_SUBAGENT_DEPTH, agent


async def test_agent_rejects_spawn_at_max_depth():
    cfg = {"metadata": {"subagent_depth": MAX_SUBAGENT_DEPTH}}
    with patch(
        "app.core.engine.react.subagent.spawner.spawn_subagent", AsyncMock()
    ) as spawn:
        out = await agent(
            action="run",
            subagent_type="general",
            description="d",
            prompt="p",
            config=cfg,
        )
    assert "深度已达上限" in out
    spawn.assert_not_awaited()


async def test_task_allows_spawn_below_depth():
    # MAX_SUBAGENT_DEPTH=1（对齐 OpenCode subagent_depth 默认）：主 Agent（depth 0，
    # 低于上限）可 spawn 一级子代理。
    cfg = {"metadata": {"subagent_depth": 0}}
    with patch(
        "app.core.engine.react.subagent.spawner.spawn_subagent",
        AsyncMock(return_value={"content": "done"}),
    ) as spawn:
        out = await agent(
            action="run",
            subagent_type="general",
            description="d",
            prompt="p",
            config=cfg,
        )
    assert out == "done"
    spawn.assert_awaited_once()


async def test_task_default_depth_zero_allows_spawn():
    with patch(
        "app.core.engine.react.subagent.spawner.spawn_subagent",
        AsyncMock(return_value={"content": "ok"}),
    ) as spawn:
        out = await agent(
            action="run", subagent_type="general", description="d", prompt="p"
        )
    assert out == "ok"
    spawn.assert_awaited_once()
