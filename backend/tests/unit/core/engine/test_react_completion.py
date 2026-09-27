"""React completion-pipeline unit tests — no DB, no real LLM.

Covers ``run_completion_pipeline`` concurrent gather, SESSION_COMPLETED publish,
episodic memory, auto-macro gating, skill-candidate heuristics and metrics.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.message.native_classes import AIMessage, HumanMessage, ToolMessage
from app.core.learning.macro import MacroCreatorService
from app.core.memory.schemas import Episode


def _tool_msg(content: str, name: str = "bash") -> ToolMessage:
    return ToolMessage(content=content, tool_call_id="c", name=name)


# ---------------------------------------------------------------------------
# run_completion_pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_completion_pipeline_runs_all_tasks_concurrently():
    from app.core.engine.react import completion

    state = SimpleNamespace(session_goal="goal")
    with (
        patch.object(completion, "_record_episode", AsyncMock()) as ep,
        patch.object(completion, "_maybe_auto_macro", AsyncMock()) as macro,
        patch.object(completion, "_record_metrics", AsyncMock()) as metrics,
    ):
        await completion.run_completion_pipeline("t1", 7, {"k": "v"}, state, summary="s")

    ep.assert_awaited_once_with("t1", 7, {"k": "v"}, state, "s")
    macro.assert_awaited_once_with("t1", 7, {"k": "v"}, state)
    metrics.assert_awaited_once_with("t1", state, {"k": "v"})


@pytest.mark.asyncio
async def test_run_completion_pipeline_survives_individual_failures():
    from app.core.engine.react import completion

    with (
        patch.object(completion, "_record_episode", AsyncMock(side_effect=RuntimeError("x"))),
        patch.object(completion, "_maybe_auto_macro", AsyncMock(side_effect=RuntimeError("y"))),
        patch.object(completion, "_record_metrics", AsyncMock(side_effect=RuntimeError("z"))),
    ):
        await completion.run_completion_pipeline("t1", None, {}, SimpleNamespace(), summary="")


# ---------------------------------------------------------------------------
# _record_metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_metrics_counts_calls_errors_tokens():
    from app.core.engine.react.completion import _record_metrics

    messages = [
        AIMessage(content="a"),
        HumanMessage(content="h"),
        ToolMessage(content="everything ok", tool_call_id="c1", name="bash"),
        ToolMessage(content="command failed with an error", tool_call_id="c2", name="bash"),
        AIMessage(
            content="b",
            additional_kwargs={"input_tokens": 100, "output_tokens": 50},
        ),
        AIMessage(
            content="c",
            additional_kwargs={"input_tokens": "40", "output_tokens": 0},
        ),
    ]
    state = SimpleNamespace(messages=messages)

    with patch("app.core.monitoring.activity_state.ActivityStateService") as svc:
        svc.return_value.update_metrics = AsyncMock()
        await _record_metrics("t1", state, {})

    svc.return_value.update_metrics.assert_awaited_once_with(
        "t1",
        llm_calls=3,
        tool_errors=1,
        input_tokens=140,
        output_tokens=50,
    )


@pytest.mark.asyncio
async def test_record_metrics_no_messages_posts_zeros():
    from app.core.engine.react.completion import _record_metrics

    with patch("app.core.monitoring.activity_state.ActivityStateService") as svc:
        svc.return_value.update_metrics = AsyncMock()
        await _record_metrics("t1", SimpleNamespace(messages=None), {})
    svc.return_value.update_metrics.assert_awaited_once_with(
        "t1", llm_calls=0, tool_errors=0, input_tokens=0, output_tokens=0
    )


@pytest.mark.asyncio
async def test_record_metrics_failure_is_swallowed():
    from app.core.engine.react.completion import _record_metrics

    with patch("app.core.monitoring.activity_state.ActivityStateService") as svc:
        svc.return_value.update_metrics = AsyncMock(side_effect=RuntimeError("db down"))
        await _record_metrics("t1", SimpleNamespace(messages=[]), {})  # must not raise


# ---------------------------------------------------------------------------
# _record_episode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_episode_builds_episode_and_records():
    from app.core.engine.react.completion import _record_episode

    memory_manager = AsyncMock()
    container = MagicMock(memory_manager=memory_manager)
    lifespan = MagicMock()
    lifespan.is_initialized.return_value = False
    lifespan.ainitialize = AsyncMock()
    lifespan.get_container.return_value = container

    ctx = EvoContext(project_id=5, thread_id="t1")
    state = SimpleNamespace(session_goal="目标：完成迁移")
    with (
        patch("app.core.memory.lifespan.MemoryLifespanManager", lifespan),
        patch.object(ContextManager, "current", return_value=ctx),
    ):
        await _record_episode("t1", 1, {}, state, summary="结果摘要")

    lifespan.is_initialized.assert_called_once()
    lifespan.ainitialize.assert_awaited_once()
    memory_manager.record_episode.assert_awaited_once()
    episode: Episode = memory_manager.record_episode.await_args.args[0]
    assert isinstance(episode, Episode)
    assert episode.goal == "目标：完成迁移"
    assert episode.result == "结果摘要"
    assert episode.project_id == 1
    assert episode.source_message_id == "t1"


@pytest.mark.asyncio
async def test_record_episode_project_id_falls_back_to_context():
    from app.core.engine.react.completion import _record_episode

    memory_manager = AsyncMock()
    container = MagicMock(memory_manager=memory_manager)
    lifespan = MagicMock()
    lifespan.is_initialized.return_value = True
    lifespan.get_container.return_value = container
    ctx = EvoContext(project_id=5)

    with (
        patch("app.core.memory.lifespan.MemoryLifespanManager", lifespan),
        patch.object(ContextManager, "current", return_value=ctx),
    ):
        await _record_episode("t1", None, {}, SimpleNamespace(session_goal="g"), "")

    episode: Episode = memory_manager.record_episode.await_args.args[0]
    assert episode.project_id == 5


@pytest.mark.asyncio
async def test_record_episode_skips_when_no_goal_or_summary():
    from app.core.engine.react.completion import _record_episode

    lifespan = MagicMock()
    with (
        patch("app.core.memory.lifespan.MemoryLifespanManager", lifespan),
        patch.object(ContextManager, "current", return_value=EvoContext()),
    ):
        await _record_episode("t1", None, {}, SimpleNamespace(session_goal=None), "")

    lifespan.get_container.assert_not_called()


@pytest.mark.asyncio
async def test_record_episode_recording_failure_is_swallowed():
    from app.core.engine.react.completion import _record_episode

    memory_manager = AsyncMock(side_effect=RuntimeError("oom"))
    container = MagicMock(memory_manager=memory_manager)
    lifespan = MagicMock()
    lifespan.is_initialized.return_value = True
    lifespan.get_container.return_value = container

    with (
        patch("app.core.memory.lifespan.MemoryLifespanManager", lifespan),
        patch.object(ContextManager, "current", return_value=EvoContext(project_id=1)),
    ):
        await _record_episode("t1", None, {}, SimpleNamespace(session_goal="g"), "r")


# ---------------------------------------------------------------------------
# _maybe_auto_macro
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_macro_disabled_by_default_skips():
    from app.core.engine.react.completion import _maybe_auto_macro

    with (
        patch.object(MacroCreatorService, "is_eligible", AsyncMock()) as is_eligible,
        patch.object(settings, "AUTO_MACRO_CREATION_ENABLED", False),
    ):
        await _maybe_auto_macro("t1", None, {}, SimpleNamespace())
    is_eligible.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_macro_eligible_passes_thread_id():
    from app.core.engine.react.completion import _maybe_auto_macro

    with (
        patch.object(MacroCreatorService, "is_eligible", AsyncMock(return_value=True)) as is_eligible,
        patch.object(settings, "AUTO_MACRO_CREATION_ENABLED", True),
    ):
        await _maybe_auto_macro("t1", 7, {}, SimpleNamespace())

    is_eligible.assert_awaited_once_with("t1")


@pytest.mark.asyncio
async def test_auto_macro_not_eligible_no_error():
    from app.core.engine.react.completion import _maybe_auto_macro

    with (
        patch.object(MacroCreatorService, "is_eligible", AsyncMock(return_value=False)) as is_eligible,
        patch.object(settings, "AUTO_MACRO_CREATION_ENABLED", True),
    ):
        await _maybe_auto_macro("t1", None, {}, SimpleNamespace())
    is_eligible.assert_awaited_once_with("t1")


@pytest.mark.asyncio
async def test_auto_macro_check_failure_is_swallowed():
    from app.core.engine.react.completion import _maybe_auto_macro

    with (
        patch.object(MacroCreatorService, "is_eligible", AsyncMock(side_effect=RuntimeError("db"))),
        patch.object(settings, "AUTO_MACRO_CREATION_ENABLED", True),
    ):
        await _maybe_auto_macro("t1", None, {}, SimpleNamespace())





# ---------------------------------------------------------------------------
# publish_session_completed_react
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_session_completed_react_builds_data_and_triggers_pipeline():
    from app.core.engine.react.completion import publish_session_completed_react
    from app.core.events.schemas.lifecycle import SessionCompletedData

    ctx = EvoContext(
        thread_id="t1",
        project_id=9,
        member_id=3,
        active_model="doubao-x",
    )
    cfg = {"configurable": {"run_id": "r1"}, "metadata": {"source": "web"}}

    with (
        patch("app.core.events.publishers.publish_session_completed", AsyncMock()) as publish,
        patch(
            "app.core.engine.react.completion.run_completion_pipeline", AsyncMock()
        ) as pipeline,
    ):
        with ContextManager.use(ctx):
            await publish_session_completed_react("t1", 9, cfg, SimpleNamespace(), summary="s")

    publish.assert_awaited_once()
    data: SessionCompletedData = publish.await_args.kwargs["data"]
    assert data.thread_id == "t1"
    assert data.run_id == "r1"
    assert data.project_id == 9
    assert data.member_id == 3
    assert data.summary == "s"
    assert data.outcome == "completed"
    assert data.audit_tier == "react"
    assert data.model == "doubao-x"

    # 异步管线已调度到事件循环
    for _ in range(5):
        if pipeline.await_count:
            break
        await asyncio.sleep(0)
    assert pipeline.await_count == 1
    assert pipeline.await_args.kwargs["summary"] == "s"


@pytest.mark.asyncio
async def test_publish_session_completed_source_precedence_and_publish_failure():
    from app.core.engine.react.completion import publish_session_completed_react

    ctx = EvoContext(metadata={"source": "voice"})
    cfg = {"configurable": {}, "metadata": {"source": "web"}}

    with (
        patch("app.core.events.publishers.publish_session_completed", AsyncMock(side_effect=RuntimeError("publish down"))) as publish,
        patch("app.core.engine.react.completion.run_completion_pipeline", AsyncMock()) as pipeline,
    ):
        with ContextManager.use(ctx):
            await publish_session_completed_react("t1", None, cfg, SimpleNamespace(), summary="")

    publish.assert_awaited_once()
    data = publish.await_args.kwargs["data"]
    assert data.source == "voice"  # ctx 优先于 config

    for _ in range(5):
        if pipeline.await_count:
            break
        await asyncio.sleep(0)
    assert pipeline.await_count == 1


@pytest.mark.asyncio
async def test_publish_session_completed_source_from_config_without_context():
    from app.core.engine.react.completion import publish_session_completed_react

    cfg = {"configurable": {}, "metadata": {"source": "duty"}}
    with (
        patch("app.core.events.publishers.publish_session_completed", AsyncMock()) as publish,
        patch("app.core.engine.react.completion.run_completion_pipeline", AsyncMock()),
    ):
        with ContextManager.use(EvoContext()):
            await publish_session_completed_react("t1", None, cfg, SimpleNamespace(), summary="")
    assert publish.await_args.kwargs["data"].source == "duty"
