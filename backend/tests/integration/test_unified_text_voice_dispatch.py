"""Entry-to-supervisor integration tests for unified text/voice dispatch.

These tests verify that the unified chat and voice entry pipelines:

1. Normalize raw input into the same agent-run inputs shape.
2. Preserve the L1 ``intent_hint`` as a Pydantic object on message metadata.
3. Correctly hand off to the real ``SupervisorNode`` (with the Worker cut off).

The Agent Worker is cut off by mocking the LLM engine inside the Supervisor node:
- Task-like prompts return ``RouteToSignal(target="worker")`` → Supervisor routes to worker.
- Chitchat prompts return a direct AI answer → Supervisor falls back to END.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.engine.dispatch import DispatchResult
from app.core.engine.message.converter import EvoMessageConverter
from app.core.engine.message.native_classes import AIMessage
from app.core.engine.nodes.supervisor import SupervisorNode
from app.core.engine.schemas import EngineResult
from app.core.engine.signals.signals import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState


@dataclass
class _Captured:
    inputs: list[dict[str, Any]] = field(default_factory=list)
    supervisor_results: list[Any] = field(default_factory=list)


async def run_supervisor_cutoff(
    inputs: dict[str, Any], *, engine_result: EngineResult
) -> Any:
    """Run a single SupervisorNode step with the given mocked engine result.

    Returns the ``StateUpdate`` produced by the Supervisor.  All heavy side
    effects (prompt rendering, context hydration, tool loading, status pings,
    session-complete publishing) are mocked away so the test focuses on the
    Supervisor's signal/fallback handling.
    """
    inputs_obj = BackgroundAgentInputs(**inputs)
    raw_data = inputs_obj.model_dump(exclude={"blackboard"})
    messages = EvoMessageConverter.repair(raw_data.get("messages", []))

    thread_id = inputs_obj.metadata.get("thread_id", "test-thread")
    state = AgentState.model_validate(
        {
            **raw_data,
            "messages": messages,
            "thread_id": thread_id,
            "session_goal": inputs_obj.session_goal or inputs_obj.goal,
            "next_node": "supervisor",
        }
    )

    ctx = EvoContext(
        thread_id=thread_id,
        project_id=inputs_obj.project_id,
        active_model=inputs_obj.model,
        working_directory=inputs_obj.working_directory or "/tmp",
    )
    token = ContextManager.set(ctx)

    config = {
        "configurable": {
            "thread_id": thread_id,
            "working_directory": inputs_obj.working_directory or "/tmp",
            "run_id": "run-test",
            "model": inputs_obj.model,
        },
        "metadata": {
            "project_id": inputs_obj.project_id,
            **inputs_obj.metadata,
        },
    }

    try:
        with (
            patch.object(
                SupervisorNode,
                "build_prompt_pair",
                new=AsyncMock(return_value=("", "")),
            ),
            patch.object(SupervisorNode, "get_tools", new=AsyncMock(return_value=[])),
            patch(
                "app.core.monitoring.activity.activity_monitor.update_agent_state",
                new=AsyncMock(),
            ),
            patch(
                "app.core.monitoring.activity.activity_monitor.update_goal",
                new=AsyncMock(),
            ),
            patch(
                "app.core.events.publishers.publish_session_completed", new=AsyncMock()
            ),
            patch("app.core.engine.nodes.base.get_default_engine") as mock_engine,
        ):
            mock_engine.return_value.run_node = AsyncMock(return_value=engine_result)
            supervisor = SupervisorNode()
            update = await supervisor(state, config)
            return update
    finally:
        ContextManager.reset(token)


def _make_patched_run_agent(captured: _Captured, engine_result: EngineResult):
    async def _patched_run_agent_background(
        _thread_id: str, inputs: dict[str, Any]
    ) -> None:
        captured.inputs.append(inputs)
        update = await run_supervisor_cutoff(inputs, engine_result=engine_result)
        captured.supervisor_results.append(update)

    return _patched_run_agent_background


# ─────────────────────────── Chat entry tests ───────────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_entry_to_supervisor_routes_to_worker(monkeypatch):
    """HTTP /chat → unified dispatcher → Supervisor routes to worker."""
    from app.api.routes.agent import _chat
    from app.api.schemas.agent import ChatRequest

    captured = _Captured()
    worker_signal = EngineResult(
        signal=RouteToSignal(
            target="worker",
            reason="test task",
            context=RoutingContext(topic="test task"),
        )
    )

    # Patch the agent worker and the DB dispatch preparation so we cut off at Supervisor.
    monkeypatch.setattr(
        "app.api.routes.agent._chat.run_agent_background",
        _make_patched_run_agent(captured, worker_signal),
    )
    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run",
        _fake_dispatch_agent_run,
    )
    monkeypatch.setattr(
        _chat.activity_monitor, "get_activity", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(_chat.activity_monitor._state_service, "start_run", AsyncMock())
    monkeypatch.setattr(_chat.activity_monitor._state_service, "end_run", AsyncMock())

    from fastapi import BackgroundTasks

    bg_tasks = BackgroundTasks()
    bg_tasks._tasks = []  # type: ignore[attr-defined]
    original_add = bg_tasks.add_task

    def _add_task(func, *args, **kwargs):
        bg_tasks._tasks.append((func, args, kwargs))  # type: ignore[attr-defined]
        return original_add(func, *args, **kwargs)

    bg_tasks.add_task = _add_task  # type: ignore[method-assign]

    req = ChatRequest(
        thread_id="t-chat-worker",
        message="帮我登录后台",
        project_id=1,
        model="mock-model",
    )
    response = await _chat.chat_endpoint(req, bg_tasks, None)

    assert response["status"] == "queued"
    assert response["thread_id"] == "t-chat-worker"

    # Run the background task so the patched run_agent_background executes.
    await bg_tasks()

    assert len(captured.inputs) == 1
    inputs = captured.inputs[0]
    assert inputs["metadata"]["source"] == "web"
    intent_hint = inputs["metadata"].get("intent_hint")
    assert isinstance(intent_hint, dict)
    assert intent_hint["domain"] == "coding_ops"

    assert len(captured.supervisor_results) == 1
    update = captured.supervisor_results[0]
    assert update.next_node == "worker"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_entry_to_supervisor_direct_answer(monkeypatch):
    """HTTP /chat with chitchat → Supervisor falls back to END without worker."""
    from app.api.routes.agent import _chat
    from app.api.schemas.agent import ChatRequest

    captured = _Captured()
    direct_answer = EngineResult(
        messages=[AIMessage(content="你好！有什么可以帮你的吗？")]
    )

    monkeypatch.setattr(
        "app.api.routes.agent._chat.run_agent_background",
        _make_patched_run_agent(captured, direct_answer),
    )
    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run",
        _fake_dispatch_agent_run,
    )
    monkeypatch.setattr(
        _chat.activity_monitor, "get_activity", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(_chat.activity_monitor._state_service, "start_run", AsyncMock())
    monkeypatch.setattr(_chat.activity_monitor._state_service, "end_run", AsyncMock())

    from fastapi import BackgroundTasks

    bg_tasks = BackgroundTasks()
    bg_tasks._tasks = []  # type: ignore[attr-defined]
    original_add = bg_tasks.add_task

    def _add_task(func, *args, **kwargs):
        bg_tasks._tasks.append((func, args, kwargs))  # type: ignore[attr-defined]
        return original_add(func, *args, **kwargs)

    bg_tasks.add_task = _add_task  # type: ignore[method-assign]

    req = ChatRequest(
        thread_id="t-chat-chitchat",
        message="你好",
        project_id=1,
        model="mock-model",
    )
    response = await _chat.chat_endpoint(req, bg_tasks, None)
    assert response["status"] == "queued"

    await bg_tasks()

    assert len(captured.inputs) == 1
    assert captured.inputs[0]["metadata"]["source"] == "web"
    intent_hint = captured.inputs[0]["metadata"].get("intent_hint")
    assert isinstance(intent_hint, dict)
    assert intent_hint["domain"] == "greeting"

    update = captured.supervisor_results[0]
    from app.core.engine.routers import RoutingTarget

    assert update.next_node == RoutingTarget.END


async def _fake_dispatch_agent_run(**kwargs: Any) -> DispatchResult:
    """Capture the normalized message and metadata, return a queued dispatch result."""
    metadata = kwargs.get("metadata") or {}
    inputs = {
        "messages": [{"type": "human", "content": kwargs.get("message_content", "")}],
        "project_id": kwargs.get("project_id"),
        "model": kwargs.get("model"),
        "command_id": kwargs.get("command_id"),
        "checkpoint_id": kwargs.get("checkpoint_id"),
        "is_retry": kwargs.get("is_retry"),
        "goal": kwargs.get("message_content", ""),
        "session_goal": kwargs.get("message_content", ""),
        "working_directory": "/tmp",
        "metadata": {
            "source": kwargs.get("source", ""),
            "member_id": kwargs.get("member_id", 0),
            **metadata,
        },
    }
    return DispatchResult(
        status="queued",
        thread_id=kwargs.get("thread_id", ""),
        message_id="msg-test",
        inputs=inputs,
    )


# ─────────────────────────── Voice entry tests ───────────────────────────


class _FakeManager:
    bind_thread = AsyncMock()
    push = AsyncMock()
    get_terminal_result = AsyncMock(return_value=None)


class _FakeStateMachine:
    can_accept_route = AsyncMock(return_value=True)
    set = AsyncMock()
    force_set = AsyncMock()
    clear = AsyncMock()


class _FakeWorkerRegistry:
    get_worker = AsyncMock(return_value=None)
    register_worker = AsyncMock()
    cancel_worker = AsyncMock()


@pytest.fixture
def fake_voice_deps(monkeypatch):
    """Bind the voice route handler to lightweight fakes."""
    from app.api.routes import voice_ws as voice_module
    from app.core.channel.output.voice_channel import VoiceChannel

    manager = _FakeManager()
    state_machine = _FakeStateMachine()
    worker_registry = _FakeWorkerRegistry()

    monkeypatch.setattr(voice_module, "manager", manager)
    monkeypatch.setattr(voice_module, "voice_state_machine", state_machine)
    monkeypatch.setattr(voice_module, "is_duplicate", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "app.core.shared_state.shared_state.get",
        AsyncMock(return_value="1"),
    )
    monkeypatch.setattr(
        "app.core.identity.identity_service.get_member_id",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        "app.core.engine.worker_registry.worker_registry",
        worker_registry,
    )

    # Patch the agent worker and the DB dispatch preparation so we cut off at Supervisor.
    monkeypatch.setattr(
        "app.core.engine.dispatch.dispatch_agent_run",
        _fake_dispatch_agent_run,
    )

    # Voice WS output now lives in VoiceChannel. Bind it to the fake manager so
    # the voice presenters can push without a real WebSocket server.
    VoiceChannel.bind(
        manager=manager,
        envelope_fn=lambda mt, body: {"type": mt, "body": body},
        message_type=MagicMock(VOICE_ROUTE_RESULT="voice.route_result"),
    )

    # Cancel task still delegates to the worker registry, not to WS output.
    monkeypatch.setattr("app.core.voice.executor.cancel_voice_task", AsyncMock())
    yield


@pytest.mark.asyncio
@pytest.mark.integration
async def test_voice_route_to_supervisor_routes_to_worker(monkeypatch, fake_voice_deps):  # noqa: ARG001
    """voice.route WS → unified dispatcher → Supervisor routes to worker."""
    from app.api.routes import voice_ws as voice_module

    captured = _Captured()
    worker_signal = EngineResult(
        signal=RouteToSignal(
            target="worker",
            reason="test task",
            context=RoutingContext(topic="test task"),
        )
    )
    monkeypatch.setattr(
        "app.core.engine.background_agent.run_agent_background",
        _make_patched_run_agent(captured, worker_signal),
    )

    await voice_module._handle_route(
        {
            "thread_id": "t-voice-worker",
            "text": "帮我登录后台",
            "project_id": 1,
            "message_id": "m1",
        },
        "conn-1",
    )

    assert len(captured.inputs) == 1
    inputs = captured.inputs[0]
    assert inputs["metadata"]["source"] == "voice"
    intent_hint = inputs["metadata"].get("intent_hint")
    assert isinstance(intent_hint, dict)
    assert intent_hint["domain"] == "coding_ops"

    update = captured.supervisor_results[0]
    assert update.next_node == "worker"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_voice_route_to_supervisor_direct_answer(monkeypatch, fake_voice_deps):  # noqa: ARG001
    """voice.route with chitchat → Supervisor falls back to END without worker."""
    from app.api.routes import voice_ws as voice_module

    captured = _Captured()
    direct_answer = EngineResult(messages=[AIMessage(content="你好呀！")])
    monkeypatch.setattr(
        "app.core.engine.background_agent.run_agent_background",
        _make_patched_run_agent(captured, direct_answer),
    )

    await voice_module._handle_route(
        {"thread_id": "t-voice-chitchat", "text": "你好", "project_id": 1},
        "conn-1",
    )

    assert len(captured.inputs) == 1
    assert captured.inputs[0]["metadata"]["source"] == "voice"
    intent_hint = captured.inputs[0]["metadata"].get("intent_hint")
    assert isinstance(intent_hint, dict)
    assert intent_hint["domain"] == "greeting"

    update = captured.supervisor_results[0]
    from app.core.engine.routers import RoutingTarget

    assert update.next_node == RoutingTarget.END


@pytest.mark.asyncio
@pytest.mark.integration
async def test_voice_l0_hit_does_not_invoke_supervisor(monkeypatch, fake_voice_deps):  # noqa: ARG001
    """An L0 builtin (e.g., '再见') is handled locally and never reaches the Supervisor."""
    from app.api.routes import voice_ws as voice_module

    captured = _Captured()
    monkeypatch.setattr(
        "app.core.engine.background_agent.run_agent_background",
        _make_patched_run_agent(captured, EngineResult()),
    )

    await voice_module._handle_route(
        {"thread_id": "t-voice-l0", "text": "再见", "project_id": 1},
        "conn-1",
    )

    assert len(captured.inputs) == 0
    from app.api.routes import voice_ws as voice_module

    # Builtin L0 results are pushed via VoiceChannel (bound to the fake manager).
    voice_module.manager.push.assert_awaited()
    calls = voice_module.manager.push.call_args_list
    assert any(
        call.args[0] == "t-voice-l0"
        and call.args[1].get("body", {}).get("status") == "done"
        for call in calls
    )
