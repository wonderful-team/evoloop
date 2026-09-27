"""Unit tests for the generic background agent loop (app/core/engine/agent/runner.py).

Covers dict-input coercion, the happy path, cancellation (silent return),
generic-exception fallback (handle_task_exception + AgentRunCompletedEvent
failed publish) and HITL interrupt re-raise/return.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.engine.agent.runner import run_agent_background
from app.core.exceptions import (
    AgentCancelledException,
    AgentHumanInterruptException,
)


def _run_scope(return_value="run-1", raise_exc=None):
    @asynccontextmanager
    async def scope(*_args, **_kwargs):
        if raise_exc is not None:
            raise raise_exc
        yield return_value

    return scope


def _config():
    return {"configurable": {"message_handler": MagicMock()}, "metadata": {}}


def _inputs():
    from app.core.engine.agent.models import BackgroundAgentInputs

    return BackgroundAgentInputs(
        session_goal="目标",
        goal="目标",
        project_id=None,
        metadata={"task_type": "subagent"},
    )


@pytest.mark.asyncio
class TestRunAgentBackground:
    @pytest.fixture(autouse=True)
    def _patch_runner_base(self):
        with patch(
            "app.core.engine.runner_base.build_ctx", AsyncMock(return_value=MagicMock())
        ), patch(
            "app.core.engine.runner_base.build_execution_config",
            MagicMock(return_value=_config()),
        ), patch(
            "app.core.engine.runner_base.build_agent_state", AsyncMock(return_value=MagicMock())
        ), patch(
            "app.core.engine.context_hydrator.AgentContextHydrator.hydrate", AsyncMock()
        ), patch(
            "app.core.engine.react.loop.run_agent_loop", AsyncMock()
        ):
            yield

    async def test_dict_inputs_happy_path(self):
        run_agent_loop = AsyncMock()
        save = AsyncMock()
        with patch(
            "app.core.monitoring.activity.activity_monitor.run_scope",
            _run_scope(),
        ), patch("app.core.engine.react.loop.run_agent_loop", run_agent_loop), patch(
            "app.core.context.manager.ContextManager.save", save
        ):
            result = await run_agent_background(
                "p-1-s0", {"session_goal": "目标", "goal": "目标"}
            )

        assert result is None
        run_agent_loop.assert_awaited_once()
        save.assert_awaited_once_with("p-1-s0")

    async def test_cancelled_returns_silently(self):
        with patch(
            "app.core.monitoring.activity.activity_monitor.run_scope",
            _run_scope(),
        ), patch(
            "app.core.engine.runner_base.build_ctx",
            AsyncMock(side_effect=AgentCancelledException()),
        ), patch(
            "app.core.engine.event.publishers.publish_agent_run_completed", AsyncMock()
        ):
            result = await run_agent_background("p-1-s0", _inputs())
        assert result is None

    async def test_generic_exception_falls_back(self):
        handle_exc = AsyncMock()
        publish = AsyncMock()
        with patch(
            "app.core.monitoring.activity.activity_monitor.run_scope",
            _run_scope(),
        ), patch(
            "app.core.engine.runner_base.build_ctx",
            AsyncMock(side_effect=RuntimeError("boom")),
        ), patch(
            "app.core.engine.agent.runner.handle_task_exception", handle_exc
        ), patch(
            "app.core.engine.event.publishers.publish_agent_run_completed", publish
        ):
            result = await run_agent_background("p-1-s0", _inputs())

        assert result is None
        handle_exc.assert_awaited_once()
        publish.assert_awaited_once()
        args = publish.await_args
        assert args.kwargs["status"] == "failed"
        assert args.kwargs["thread_id"] == "p-1-s0"

    async def test_hitl_interrupt_returns(self):
        with patch(
            "app.core.monitoring.activity.activity_monitor.run_scope",
            _run_scope(),
        ), patch(
            "app.core.engine.runner_base.build_ctx",
            AsyncMock(side_effect=AgentHumanInterruptException("ask")),
        ), patch(
            "app.core.engine.event.publishers.publish_agent_run_completed", AsyncMock()
        ):
            result = await run_agent_background("p-1-s0", _inputs())
        assert result is None
