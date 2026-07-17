"""Agent conversation integration test for macro discovery and execution.

This test simulates a natural human request to the Agent and verifies that:
1. The Agent routes to the worker node for an actionable request.
2. The Worker uses `list_macros` to discover a verified macro matching the task.
3. The Worker then calls `run_macro(macro_id, params)` to execute the whole
   macro script as one deterministic replay, instead of manually replaying steps.
4. In a project context, only project-scoped macros are visible; in a global
   context (no project_id), only global macros (project_id IS NULL) are visible.

The LLM is mocked to make the test deterministic, but the agent loop, tools, DB,
and macro execution orchestration are all real production code.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.context import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.loop import run_node_loop
from app.core.engine.message.native_classes import AIMessage, HumanMessage, ToolMessage
from app.core.engine.routers import RoutingTarget
from app.core.engine.signals import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.execution.macro.schemas import MacroRunResult
from app.infrastructure.database import session_scope
from app.models.macro import Macro
from app.utils.yaml import macro_to_yaml


# ---------------------------------------------------------------------------
# Test setup — same patches used by the existing end-to-end agent tests to
# avoid DB lookups that are not relevant to this macro flow.
# ---------------------------------------------------------------------------
def _apply_test_patches():
    from app.core.engine.context_hydrator import AgentContextHydrator
    from app.core.engine.nodes.utils.skill_resolver import SkillResolver
    from app.core.engine.skill_hydrator import SkillHydrator

    async def _mock_hydrate(*_args, **_kwargs):
        return None

    AgentContextHydrator.hydrate = _mock_hydrate

    async def _mock_get_node_skills(_state, _node_name):
        return []

    SkillHydrator.get_node_skills = _mock_get_node_skills

    async def _mock_inject_fallback(sops, _config):
        return sops

    SkillResolver.inject_fallback_sops = _mock_inject_fallback

    if not hasattr(settings, "DEFAULT_PROJECT_ID"):
        object.__setattr__(settings, "DEFAULT_PROJECT_ID", 1)


_apply_test_patches()


# ---------------------------------------------------------------------------
# Multi-turn mock LLM
# ---------------------------------------------------------------------------
class MultiTurnMockInferenceEngine(InferenceEngine):
    """Mock inference engine that can run multiple deterministic ReAct turns.

    Each entry in a node's scenario list is one LLM turn.  If a turn contains
    `tool_calls`, the engine executes them through the real tool executor and
    then proceeds to the next turn, exactly like a real LLM seeing the tool
    results before continuing.
    """

    def __init__(self, scenarios: dict[str, list[dict]]):
        self._llm_factory = MagicMock()
        self._scenarios = scenarios
        self._counters: dict[str, int] = {}

    async def create_llm(self, model, temperature):
        return MagicMock(), "openai"

    def bind_tools(self, llm, tools):
        if tools:
            return llm, {t.name: t for t in tools}
        return llm, {}

    async def run_react_loop(
        self,
        llm_with_tools,
        messages,
        system_prompt,
        provider,
        config,
        name,
        max_steps=5,
        tool_executor=None,
        interceptors=None,
        on_thinking=None,
        model=None,
        iteration_count=None,
    ):
        all_messages: list[AIMessage | ToolMessage] = []
        local_tool_history: list[str] = []
        last_response: AIMessage | None = None

        for _ in range(max_steps):
            idx = self._counters.get(name, 0)
            turns = self._scenarios.get(name, [])
            if idx >= len(turns):
                break

            self._counters[name] = idx + 1
            turn = turns[idx]

            ai_msg = AIMessage(
                content=turn.get("content", ""),
                tool_calls=turn.get("tool_calls", []),
            )
            all_messages.append(ai_msg)
            last_response = ai_msg

            if turn.get("tool_calls"):
                remaining = [
                    tc
                    for tc in turn["tool_calls"]
                    if not interceptors or tc["name"] not in interceptors
                ]
                if remaining and tool_executor is not None:
                    tool_results, _batch_signal = await tool_executor.execute_batch(
                        remaining, local_tool_history
                    )
                    all_messages.extend(tool_results)

            if turn.get("signal"):
                return {
                    "messages": all_messages,
                    "tool_history": local_tool_history,
                    "last_response": last_response,
                    "is_truncated": False,
                    "signal": turn["signal"],
                }

            if not turn.get("tool_calls"):
                if turn.get("final_content"):
                    all_messages.append(AIMessage(content=turn["final_content"]))
                break

        return {
            "messages": all_messages,
            "tool_history": local_tool_history,
            "last_response": last_response,
            "is_truncated": False,
            "signal": None,
        }

    async def run_single_shot(
        self,
        llm_with_tools,
        messages,
        system_prompt,
        provider,
        config,
        name,
        tool_executor=None,
        interceptors=None,
    ):
        return await self.run_react_loop(
            llm_with_tools,
            messages,
            system_prompt,
            provider,
            config,
            name,
            max_steps=1,
            tool_executor=tool_executor,
            interceptors=interceptors,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_WAIT_SCRIPT = macro_to_yaml(
    [
        {
            "type": "action",
            "event_type": "wait",
            "payload": {"duration_ms": 0},
        }
    ]
)


async def _insert_macro(
    *,
    name: str,
    description: str,
    project_id: int | None,
    namespace: str | None = None,
    entity: str | None = None,
    macro_script: str = _WAIT_SCRIPT,
    parameters: list[dict] | None = None,
) -> Macro:
    macro = Macro(
        name=name,
        description=description,
        trigger_patterns=[],
        parameters=parameters or [],
        macro_script=macro_script,
        risk_tier="ui",
        requires_confirmation=False,
        allow_self_healing=True,
        status="verified",
        is_active=True,
        project_id=project_id,
        member_id=0,
        namespace=namespace,
        entity=entity,
    )
    async with session_scope() as db:
        db.add(macro)
        await db.flush()
        return macro


async def _run_agent_scenario(
    scenarios: dict[str, list[dict]],
    thread_id: str,
    project_id: int | None,
    human_message: str,
) -> list[Any]:
    """Set up the real agent loop with a mock engine and run one turn."""
    from app.core.monitoring.activity import activity_monitor

    engine = AgentEngine(inference_engine=MultiTurnMockInferenceEngine(scenarios))
    set_default_engine(engine)

    ctx = EvoContext(
        thread_id=thread_id,
        project_id=project_id,
        active_model="mock-model",
    )
    ContextManager.set(ctx)

    state = AgentState(
        messages=[HumanMessage(content=human_message)],
        next_node="supervisor",
        session_goal=human_message,
        thread_id=thread_id,
        project_id=project_id,
    )

    config = {
        "configurable": {
            "thread_id": thread_id,
            "model": "mock-model",
            "project_id": project_id,
        }
    }

    async with activity_monitor.run_scope(
        thread_id=thread_id,
        main_goal=human_message,
        project_id=project_id,
    ) as run_id:
        config["configurable"]["run_id"] = run_id
        await run_node_loop(state, config, thread_id, max_loop_steps=20)

    return state.messages


async def _run_agent_conversation(
    engine: AgentEngine,
    thread_id: str,
    turns: list[dict],
) -> tuple[list[Any], list[ToolMessage]]:
    """Run multiple conversation turns on the same thread.

    Each turn is a fresh run that starts at the supervisor node, allowing the
    same AgentState to accumulate messages across a multi-turn chat.  The
    project_id may change per turn to verify context-dependent macro scope.

    Returns the final message list and all tool messages captured across turns
    (the Supervisor filters tool messages between turns, so they are captured
    before the next turn starts).
    """
    from app.core.monitoring.activity import activity_monitor

    set_default_engine(engine)

    initial_turn = turns[0]
    ctx = EvoContext(
        thread_id=thread_id,
        project_id=initial_turn["project_id"],
        active_model="mock-model",
    )
    ContextManager.set(ctx)

    state = AgentState(
        messages=[HumanMessage(content=initial_turn["human_message"])],
        next_node=RoutingTarget.SUPERVISOR,
        session_goal=initial_turn["human_message"],
        thread_id=thread_id,
        project_id=initial_turn["project_id"],
    )

    config = {
        "configurable": {
            "thread_id": thread_id,
            "model": "mock-model",
            "project_id": initial_turn["project_id"],
        }
    }

    all_tool_messages: list[ToolMessage] = []

    for idx, turn in enumerate(turns):
        if idx > 0:
            ctx.project_id = turn["project_id"]
            ContextManager.set(ctx)
            state.messages.append(HumanMessage(content=turn["human_message"]))
            state.session_goal = turn["human_message"]
            state.project_id = turn["project_id"]
            state.next_node = RoutingTarget.SUPERVISOR
            config["configurable"]["project_id"] = turn["project_id"]

        async with activity_monitor.run_scope(
            thread_id=thread_id,
            main_goal=turn["human_message"],
            project_id=turn["project_id"],
        ) as run_id:
            config["configurable"]["run_id"] = run_id
            await run_node_loop(state, config, thread_id, max_loop_steps=20)

        all_tool_messages.extend(
            [m for m in state.messages if isinstance(m, ToolMessage)]
        )

    return state.messages, all_tool_messages


# ---------------------------------------------------------------------------
# Test: project context
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.db
async def test_agent_discovers_and_executes_project_macro(_real_db):
    """Human asks for a repeatable action; Agent finds and runs the project macro."""
    project_id = 42

    global_macro = await _insert_macro(
        name="打开 Chrome",
        description="Open Chrome browser",
        project_id=None,
        namespace="desktop/macos",
        entity="chrome",
    )
    project_macro = await _insert_macro(
        name="登录测试后台",
        description="Login to the test admin dashboard",
        project_id=project_id,
        namespace="web/admin",
        entity="admin",
    )
    other_project_macro = await _insert_macro(
        name="登录生产后台",
        description="Login to the production admin dashboard",
        project_id=99,
        namespace="web/admin",
        entity="admin",
    )

    executed_macro_ids: list[int] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
        return MacroRunResult(success=True, message="done", extracted_data={})

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="用户请求登录后台",
                    context=RoutingContext(topic="后台登录"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "登录测试后台"},
                        "id": "tc-list-1",
                    }
                ],
            },
            {
                "tool_calls": [
                    {
                        "name": "run_macro",
                        "args": {"macro_id": project_macro.id, "params": {}},
                        "id": "tc-run-1",
                    }
                ],
                "final_content": "已登录测试后台。",
            },
        ],
    }

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs = await _run_agent_scenario(
            scenarios,
            thread_id=f"test-proj-macro-{uuid4().hex[:8]}",
            project_id=project_id,
            human_message="帮我登录一下测试后台",
        )

    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    list_macro_msgs = [m for m in tool_msgs if m.name == "list_macros"]
    run_macro_msgs = [m for m in tool_msgs if m.name == "run_macro"]

    assert len(list_macro_msgs) >= 1, "Agent should call list_macros"
    assert len(run_macro_msgs) >= 1, "Agent should call run_macro"

    list_result = list_macro_msgs[0].content
    assert (
        "登录测试后台" in list_result
    ), "Project macro should appear in list_macros result"
    assert (
        "打开 Chrome" not in list_result
    ), "Global macro should not leak into project context"
    assert "登录生产后台" not in list_result, "Other project macro should not leak"

    assert project_macro.id in executed_macro_ids, "Project macro should be executed"
    assert global_macro.id not in executed_macro_ids, "Global macro should not run"
    assert (
        other_project_macro.id not in executed_macro_ids
    ), "Other project macro should not run"


# ---------------------------------------------------------------------------
# Test: global context
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.db
async def test_agent_discovers_and_executes_global_macro(_real_db):
    """Human asks for a cross-project action; Agent finds and runs the global macro."""
    project_macro = await _insert_macro(
        name="登录测试后台",
        description="Login to the test admin dashboard",
        project_id=42,
        namespace="web/admin",
        entity="admin",
    )
    global_macro = await _insert_macro(
        name="打开 Chrome",
        description="Open Chrome browser",
        project_id=None,
        namespace="desktop/macos",
        entity="chrome",
    )

    executed_macro_ids: list[int] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
        return MacroRunResult(success=True, message="done", extracted_data={})

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="用户请求打开浏览器",
                    context=RoutingContext(topic="打开浏览器"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "打开 Chrome"},
                        "id": "tc-list-global-1",
                    }
                ],
            },
            {
                "tool_calls": [
                    {
                        "name": "run_macro",
                        "args": {"macro_id": global_macro.id, "params": {}},
                        "id": "tc-run-global-1",
                    }
                ],
                "final_content": "已打开 Chrome。",
            },
        ],
    }

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs = await _run_agent_scenario(
            scenarios,
            thread_id=f"test-global-macro-{uuid4().hex[:8]}",
            project_id=None,
            human_message="帮我打开 Chrome",
        )

    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    list_macro_msgs = [m for m in tool_msgs if m.name == "list_macros"]
    run_macro_msgs = [m for m in tool_msgs if m.name == "run_macro"]

    assert len(list_macro_msgs) >= 1, "Agent should call list_macros"
    assert len(run_macro_msgs) >= 1, "Agent should call run_macro"

    list_result = list_macro_msgs[0].content
    assert (
        "打开 Chrome" in list_result
    ), "Global macro should appear in list_macros result"
    assert (
        "登录测试后台" not in list_result
    ), "Project macro should not leak into global context"

    assert global_macro.id in executed_macro_ids, "Global macro should be executed"
    assert project_macro.id not in executed_macro_ids, "Project macro should not run"


# ---------------------------------------------------------------------------
# Multi-turn & repeated tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.parametrize("iteration", range(3))
async def test_multi_turn_project_macro_isolates_global_and_other_project(
    _real_db, iteration
):
    """Project chat: first asks for a global-only action, then for a project one.

    The Agent must not leak the global macro or macros from other projects into
    the project context, and must execute only the project-scoped macro.
    """
    project_id = 42

    global_macro = await _insert_macro(
        name="打开 Chrome",
        description="Open Chrome browser",
        project_id=None,
        namespace="desktop/macos",
        entity="chrome",
    )
    project_macro = await _insert_macro(
        name="登录测试后台",
        description="Login to the test admin dashboard",
        project_id=project_id,
        namespace="web/admin",
        entity="admin",
    )
    other_project_macro = await _insert_macro(
        name="登录生产后台",
        description="Login to the production admin dashboard",
        project_id=99,
        namespace="web/admin",
        entity="admin",
    )

    executed_macro_ids: list[int] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
        return MacroRunResult(success=True, message="done", extracted_data={})

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="打开浏览器",
                    context=RoutingContext(topic="打开浏览器"),
                ),
            },
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="登录后台",
                    context=RoutingContext(topic="后台登录"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "打开 Chrome"},
                        "id": f"tc-list-chrome-{iteration}",
                    }
                ],
            },
            {
                "final_content": "当前项目没有可用的 Chrome 宏。",
            },
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "登录测试后台"},
                        "id": f"tc-list-login-{iteration}",
                    }
                ],
            },
            {
                "tool_calls": [
                    {
                        "name": "run_macro",
                        "args": {"macro_id": project_macro.id, "params": {}},
                        "id": f"tc-run-login-{iteration}",
                    }
                ],
            },
            {
                "final_content": "已登录测试后台。",
            },
        ],
    }

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs, tool_msgs = await _run_agent_conversation(
            engine=AgentEngine(inference_engine=MultiTurnMockInferenceEngine(scenarios)),
            thread_id=f"test-multi-turn-proj-{iteration}-{uuid4().hex[:8]}",
            turns=[
                {"human_message": "帮我打开 Chrome", "project_id": project_id},
                {"human_message": "那帮我登录测试后台", "project_id": project_id},
            ],
        )

    list_calls = [m for m in tool_msgs if m.name == "list_macros"]
    run_calls = [m for m in tool_msgs if m.name == "run_macro"]

    assert len(list_calls) == 2, f"Expected 2 list_macros calls, got {len(list_calls)}: {list_calls}"
    assert "No verified macros found" in list_calls[0].content, (
        "Global macro should not be visible in project context"
    )
    assert "登录测试后台" in list_calls[1].content, (
        "Project macro should be found in the second turn"
    )

    assert len(run_calls) == 1, "Only the project macro should run"
    assert executed_macro_ids == [project_macro.id]
    assert global_macro.id not in executed_macro_ids
    assert other_project_macro.id not in executed_macro_ids


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.parametrize("iteration", range(3))
async def test_multi_turn_global_then_project_context_switch(_real_db, iteration):
    """Same thread: first turn is global, second turn switches to a project.

    Verifies that the Agent adjusts the macro catalog to the active context.
    """
    global_macro = await _insert_macro(
        name="打开 Chrome",
        description="Open Chrome browser",
        project_id=None,
        namespace="desktop/macos",
        entity="chrome",
    )
    project_macro = await _insert_macro(
        name="登录测试后台",
        description="Login to the test admin dashboard",
        project_id=42,
        namespace="web/admin",
        entity="admin",
    )

    executed_macro_ids: list[int] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
        return MacroRunResult(success=True, message="done", extracted_data={})

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="打开浏览器",
                    context=RoutingContext(topic="打开浏览器"),
                ),
            },
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="登录后台",
                    context=RoutingContext(topic="后台登录"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "打开 Chrome"},
                        "id": f"tc-list-global-{iteration}",
                    }
                ],
            },
            {
                "tool_calls": [
                    {
                        "name": "run_macro",
                        "args": {"macro_id": global_macro.id, "params": {}},
                        "id": f"tc-run-global-{iteration}",
                    }
                ],
            },
            {
                "final_content": "已打开 Chrome。",
            },
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "登录测试后台"},
                        "id": f"tc-list-proj-{iteration}",
                    }
                ],
            },
            {
                "tool_calls": [
                    {
                        "name": "run_macro",
                        "args": {"macro_id": project_macro.id, "params": {}},
                        "id": f"tc-run-proj-{iteration}",
                    }
                ],
            },
            {
                "final_content": "已登录测试后台。",
            },
        ],
    }

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs, tool_msgs = await _run_agent_conversation(
            engine=AgentEngine(inference_engine=MultiTurnMockInferenceEngine(scenarios)),
            thread_id=f"test-switch-{iteration}-{uuid4().hex[:8]}",
            turns=[
                {"human_message": "帮我打开 Chrome", "project_id": None},
                {"human_message": "现在帮我登录测试后台", "project_id": 42},
            ],
        )

    list_calls = [m for m in tool_msgs if m.name == "list_macros"]
    run_calls = [m for m in tool_msgs if m.name == "run_macro"]

    assert len(list_calls) == 2, "Expected one list_macros per turn"
    assert "打开 Chrome" in list_calls[0].content, "Global macro should be listed first"
    assert "登录测试后台" in list_calls[1].content, "Project macro should be listed second"

    assert len(run_calls) == 2, "Expected one run_macro per turn"
    assert executed_macro_ids == [global_macro.id, project_macro.id]


@pytest.mark.asyncio
@pytest.mark.db
async def test_no_verified_macro_falls_back_to_manual(_real_db):
    """When no macro matches, the Agent should not hallucinate a run_macro call."""
    project_id = 42

    executed_macro_ids: list[int] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
        return MacroRunResult(success=True, message="done", extracted_data={})

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="删除日志",
                    context=RoutingContext(topic="删除日志"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "删除日志"},
                        "id": "tc-list-nomatch",
                    }
                ],
            },
            {
                "final_content": "未找到相关宏，请手动处理。",
            },
        ],
    }

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs = await _run_agent_scenario(
            scenarios,
            thread_id=f"test-no-macro-{uuid4().hex[:8]}",
            project_id=project_id,
            human_message="帮我删除所有旧日志",
        )

    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    list_calls = [m for m in tool_msgs if m.name == "list_macros"]
    run_calls = [m for m in tool_msgs if m.name == "run_macro"]

    assert len(list_calls) == 1, "Agent should search macros first"
    assert "No verified macros found" in list_calls[0].content
    assert len(run_calls) == 0, "No macro should run when none matches"
    assert executed_macro_ids == []


@pytest.mark.asyncio
@pytest.mark.db
async def test_agent_executes_macro_with_required_parameters(_real_db):
    """A macro with required parameters should be passed through run_macro."""
    project_id = 42

    macro = await _insert_macro(
        name="提交 GitHub Issue",
        description="Create a GitHub issue",
        project_id=project_id,
        namespace="web/github",
        entity="github",
        parameters=[
            {"name": "title", "required": True},
            {"name": "body", "required": False},
        ],
    )

    executed_macro_ids: list[int] = []
    captured_params: list[dict | None] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
            captured_params.append(kwargs.get("params"))
        return MacroRunResult(success=True, message="done", extracted_data={})

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="创建 issue",
                    context=RoutingContext(topic="创建 issue"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "list_macros",
                        "args": {"query": "提交 GitHub Issue"},
                        "id": "tc-list-issue",
                    }
                ],
            },
            {
                "tool_calls": [
                    {
                        "name": "run_macro",
                        "args": {
                            "macro_id": macro.id,
                            "params": {"title": "Bug report", "body": "It is broken"},
                        },
                        "id": "tc-run-issue",
                    }
                ],
            },
            {
                "final_content": "已提交 GitHub Issue。",
            },
        ],
    }

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs = await _run_agent_scenario(
            scenarios,
            thread_id=f"test-params-{uuid4().hex[:8]}",
            project_id=project_id,
            human_message="帮我提交一个 GitHub Issue，标题是 Bug report",
        )

    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    run_calls = [m for m in tool_msgs if m.name == "run_macro"]

    assert len(run_calls) == 1, "Macro should run once"
    assert executed_macro_ids == [macro.id]
    assert captured_params
    assert captured_params[0]["title"] == "Bug report"
    assert captured_params[0]["body"] == "It is broken"


@pytest.mark.asyncio
@pytest.mark.db
@pytest.mark.parametrize("iteration", range(3))
async def test_same_name_macro_isolated_by_context(_real_db, iteration):
    """A macro with the same name but different scope is selected by context."""
    global_macro = await _insert_macro(
        name="登录后台",
        description="Global login macro",
        project_id=None,
        namespace="web/admin",
        entity="admin",
    )
    project_macro = await _insert_macro(
        name="登录后台",
        description="Project login macro",
        project_id=42,
        namespace="web/admin",
        entity="admin",
    )

    executed_macro_ids: list[int] = []

    async def spy_macro_service_run(*_args, **kwargs):
        macro = kwargs.get("macro")
        if macro is not None:
            executed_macro_ids.append(macro.id)
        return MacroRunResult(success=True, message="done", extracted_data={})

    def build_scenarios(macro_id: int):
        return {
            "Supervisor": [
                {
                    "content": '<route_to target="worker"/>',
                    "signal": RouteToSignal(
                        target="worker",
                        reason="登录后台",
                        context=RoutingContext(topic="登录后台"),
                    ),
                },
            ],
            "Worker": [
                {
                    "tool_calls": [
                        {
                            "name": "list_macros",
                            "args": {"query": "登录后台"},
                            "id": f"tc-list-{iteration}",
                        }
                    ],
                },
                {
                    "tool_calls": [
                        {
                            "name": "run_macro",
                            "args": {"macro_id": macro_id, "params": {}},
                            "id": f"tc-run-{iteration}",
                        }
                    ],
                },
                {
                    "final_content": "已登录后台。",
                },
            ],
        }

    # Global context
    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs = await _run_agent_scenario(
            build_scenarios(global_macro.id),
            thread_id=f"test-dup-global-{iteration}-{uuid4().hex[:8]}",
            project_id=None,
            human_message="帮我登录后台",
        )
    list_result = [
        m for m in msgs if isinstance(m, ToolMessage) and m.name == "list_macros"
    ][0].content
    assert f"#{global_macro.id}" in list_result, "Global catalog should contain the global macro"
    assert f"#{project_macro.id}" not in list_result, "Project macro should not leak globally"
    assert executed_macro_ids == [global_macro.id]

    # Project context
    with patch(
        "app.core.execution.macro.service.MacroService.run",
        side_effect=spy_macro_service_run,
    ):
        msgs = await _run_agent_scenario(
            build_scenarios(project_macro.id),
            thread_id=f"test-dup-proj-{iteration}-{uuid4().hex[:8]}",
            project_id=42,
            human_message="帮我登录后台",
        )
    list_result = [
        m for m in msgs if isinstance(m, ToolMessage) and m.name == "list_macros"
    ][0].content
    assert f"#{project_macro.id}" in list_result, "Project catalog should contain the project macro"
    assert f"#{global_macro.id}" not in list_result, "Global macro should not leak into project"
    assert executed_macro_ids == [global_macro.id, project_macro.id]
