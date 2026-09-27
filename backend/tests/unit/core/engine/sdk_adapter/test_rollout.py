from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.engine.react.loop import run_agent_loop
from app.core.engine.sdk_adapter import session_bridge
from app.core.engine.state import AgentState


@pytest.mark.asyncio
async def test_run_agent_loop_delegates_to_sdk_bridge_and_resolves_steps(monkeypatch) -> None:
    sdk_run = AsyncMock(
        return_value={
            "messages": [],
            "tool_history": [],
            "is_truncated": False,
            "outcome": "success",
        }
    )
    monkeypatch.setattr(session_bridge, "run_turn", sdk_run)

    result = await run_agent_loop(
        AgentState(thread_id="rollout-test", messages=[]),
        {"configurable": {"model": ""}, "metadata": {}},
        "rollout-test",
        max_steps=42,
    )

    assert result["outcome"] == "success"
    sdk_run.assert_awaited_once()
    assert sdk_run.await_args.kwargs["max_steps"] == 42
