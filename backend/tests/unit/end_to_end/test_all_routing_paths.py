"""
全链路回归测试 — 验证 Agent Graph 所有主要路由路径

覆盖链路：
1. Supervisor -> Worker -> Finish
2. Supervisor -> Worker -> Finish(失败) -> Supervisor -> Worker -> Finish
3. Supervisor -> Worker(Subtask) -> Finish
4. Supervisor -> SequentialWorkflow -> Finish/Supervisor
5. Supervisor -> Finish (直接结束)
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


# =============================================================================
# 路由函数测试
# =============================================================================
def test_route_by_next_node_follows_state():
    """route_by_next_node 跟随 state.next_node"""
    from app.core.engine.routers import route_by_next_node
    from app.core.engine.state import AgentState

    state = AgentState(messages=[], next_node="finish")
    assert route_by_next_node(state) == "finish"

    state = AgentState(messages=[], next_node="supervisor")
    assert route_by_next_node(state) == "supervisor"

    state = AgentState(messages=[], next_node=None)
    assert route_by_next_node(state) == "finish"


def test_route_worker_by_outcome():
    """route_worker_by_outcome 根据 worker_outcome 路由"""
    from app.core.engine.routers import route_worker_by_outcome
    from app.core.engine.state import AgentState

    # success → finish
    state = AgentState(messages=[], worker_outcome="success")
    assert route_worker_by_outcome(state) == "finish"

    # truncated → supervisor
    state = AgentState(messages=[], worker_outcome="truncated")
    assert route_worker_by_outcome(state) == "supervisor"

    # failed → supervisor
    state = AgentState(messages=[], worker_outcome="failed")
    assert route_worker_by_outcome(state) == "supervisor"

    # no outcome → finish (safe fallback)
    state = AgentState(messages=[])
    assert route_worker_by_outcome(state) == "finish"


def test_route_finish_blocked_by_hook():
    """Finish 被 hook 阻塞时返回 Supervisor"""
    from app.core.engine.routers import route_finish
    from app.core.engine.state import AgentState

    state = AgentState(messages=[], blocked_by_hook=True)
    assert route_finish(state) == "supervisor"


def test_route_finish_explicit_end():
    """Finish 显式设置 next_node=END 时返回 END"""
    from app.core.engine.routers import route_finish
    from app.core.engine.state import AgentState

    state = AgentState(messages=[], next_node="END")
    assert route_finish(state) == "END"


def test_route_finish_normal():
    """Finish 正常结束时返回 END"""
    from app.core.engine.routers import route_finish
    from app.core.engine.state import AgentState

    state = AgentState(messages=[])
    assert route_finish(state) == "END"


@pytest.mark.asyncio
async def test_route_supervisor_respects_iteration_limit():
    """Supervisor 达到迭代上限时强制返回 FINISH"""
    from app.core.engine.routers import route_supervisor
    from app.core.engine.state import AgentState

    state = AgentState(messages=[], iteration_count=9999)
    result = route_supervisor(state)
    assert result == "finish"


@pytest.mark.asyncio
async def test_route_supervisor_worker_target_with_ticket():
    """Supervisor 路由到 worker（有 ticket）"""
    from app.core.engine.routers import route_supervisor
    from app.core.engine.state import AgentState
    from app.core.engine.state.config import ExecutionTicket

    ticket = ExecutionTicket(topic="test", reason="test", ticket_type="task")
    state = AgentState(messages=[], next_node="worker", ticket=ticket)
    result = route_supervisor(state)
    assert result == "worker"


# =============================================================================
# SignalDispatcher 全路径测试
# =============================================================================
@pytest.mark.asyncio
async def test_signal_dispatcher_none():
    """signal=None 返回 None（走 fallback）"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    result = await SignalDispatcher.dispatch(state, None, RunnableConfig())
    assert result is None


@pytest.mark.asyncio
async def test_signal_dispatcher_route_to_worker():
    """RouteToSignal -> worker 正常工作"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.signals.schemas import RouteToSignal
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    signal = RouteToSignal(target="worker", reason="test routing")
    result = await SignalDispatcher.dispatch(state, signal, RunnableConfig())
    assert result is not None
    assert result.next_node == "worker"


@pytest.mark.asyncio
async def test_signal_dispatcher_route_to_finish():
    """RouteToSignal -> finish 正常工作"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.signals.schemas import RouteToSignal
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    signal = RouteToSignal(target="finish", reason="test routing")
    result = await SignalDispatcher.dispatch(state, signal, RunnableConfig())
    assert result is not None
    assert result.next_node == "finish"


@pytest.mark.asyncio
async def test_signal_dispatcher_terminate():
    """TerminateSignal 正常工作"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.signals.schemas import TerminateSignal
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    signal = TerminateSignal(summary="done")
    result = await SignalDispatcher.dispatch(state, signal, RunnableConfig())
    assert result is not None
    # TerminateSignal 被处理为 finish（进入 Finish 节点做审计）
    assert result.next_node == "finish"


# =============================================================================
# 节点 Fallback 路径测试
# =============================================================================
@pytest.mark.asyncio
async def test_worker_node_fallback():
    """Worker 节点 fallback 不设 next_node（由 route_worker_by_outcome 决定路由）"""
    from app.core.engine.nodes.worker import WorkerNode
    from app.core.engine.engine import EngineResult
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    from app.core.engine.state.config import ExecutionTicket
    node = WorkerNode()
    ticket = ExecutionTicket(topic="test", reason="test", ticket_type="task")
    state = AgentState(messages=[], ticket=ticket)
    engine_result = EngineResult(messages=[])

    outcome = await node._build_fallback_outcome(state, engine_result, RunnableConfig())
    assert outcome.next_node is None


@pytest.mark.asyncio
async def test_supervisor_node_fallback():
    """Supervisor 节点 fallback 返回 FINISH（无 AI 内容时兜底）"""
    from app.core.engine.nodes.supervisor import SupervisorNode
    from app.core.engine.engine import EngineResult
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    node = SupervisorNode()
    state = AgentState(messages=[])
    engine_result = EngineResult(messages=[])

    outcome = await node._build_fallback_outcome(state, engine_result, RunnableConfig())
    assert outcome.next_node == "finish"


@pytest.mark.asyncio
async def test_sequential_workflow_node_fallback():
    """SequentialWorkflow 节点 fallback 返回 FINISH"""
    from app.core.engine.nodes.sequential_workflow import SequentialWorkflowNode
    from app.core.engine.engine import EngineResult
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    node = SequentialWorkflowNode()
    state = AgentState(messages=[])
    engine_result = EngineResult(messages=[])

    outcome = await node._build_fallback_outcome(state, engine_result, RunnableConfig())
    assert outcome.next_node == "finish"





# =============================================================================
# 错误恢复链路测试
# =============================================================================
@pytest.mark.asyncio
async def test_node_error_handler_returns_finish():
    """节点执行出错时直接抛出异常（避免不一致状态和无限循环）"""
    from app.core.engine.nodes.base import BaseAgentNode
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    class TestNode(BaseAgentNode):
        def __init__(self):
            super().__init__("Test")

        async def build_prompt_pair(self, state, config):
            return "", ""

    node = TestNode()
    state = AgentState(messages=[])

    with pytest.raises(Exception, match="test error"):
        await node.handle_error(state, Exception("test error"), config=RunnableConfig())


# =============================================================================
# 信号队列化机制测试（多 route_to 串行派发）
# =============================================================================

@pytest.mark.asyncio
async def test_process_tool_executions_queues_multiple_signals():
    """
    T1: 单回合内多个 route_to 调用时，第一个立即生效，其余入队而非丢弃。
    验证 inference_engine._process_tool_executions 返回三元组中的 queued_signals。
    """
    from app.core.engine.inference_engine import InferenceEngine
    from app.core.engine.signals.schemas import RouteToSignal
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableConfig

    engine = InferenceEngine()

    response = AIMessage(content="", tool_calls=[
        {"id": "tc1", "name": "route_to", "args": {"target": "worker", "reason": "task1"}},
        {"id": "tc2", "name": "route_to", "args": {"target": "worker", "reason": "task2"}},
        {"id": "tc3", "name": "route_to", "args": {"target": "worker", "reason": "task3"}},
    ])

    async def fake_interceptor(tc, config):
        return RouteToSignal(target=tc["args"]["target"], reason=tc["args"]["reason"])

    tool_results, primary_signal, queued_signals = await engine._process_tool_executions(
        response=response,
        name="TestSupervisor",
        config=RunnableConfig(),
        interceptors={"route_to": fake_interceptor},
        tool_executor=None,
        local_tool_history=[],
    )

    assert primary_signal is not None
    assert primary_signal.reason == "task1"        # 第一个立即生效
    assert len(queued_signals) == 2                 # 后两个入队，不丢弃
    assert queued_signals[0].reason == "task2"
    assert queued_signals[1].reason == "task3"
    assert tool_results == []


@pytest.mark.asyncio
async def test_process_tool_executions_single_signal_backward_compat():
    """
    T4（回归保护）: 单个 route_to 时，行为与改动前完全一致：primary_signal 正常，queued_signals 为空列表。
    """
    from app.core.engine.inference_engine import InferenceEngine
    from app.core.engine.signals.schemas import RouteToSignal
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableConfig

    engine = InferenceEngine()

    response = AIMessage(content="", tool_calls=[
        {"id": "tc1", "name": "route_to", "args": {"target": "worker", "reason": "single_task"}},
    ])

    async def fake_interceptor(tc, config):
        return RouteToSignal(target=tc["args"]["target"], reason=tc["args"]["reason"])

    tool_results, primary_signal, queued_signals = await engine._process_tool_executions(
        response=response,
        name="TestSupervisor",
        config=RunnableConfig(),
        interceptors={"route_to": fake_interceptor},
        tool_executor=None,
        local_tool_history=[],
    )

    assert primary_signal is not None
    assert primary_signal.reason == "single_task"
    assert queued_signals == []                     # 无额外信号，队列为空（回归保护）


@pytest.mark.asyncio
async def test_supervisor_prepare_state_drains_pending_signals():
    """
    T2: blackboard.pending_signals 非空时，SupervisorNode.prepare_state 直接消费队列头部，
    绕过 LLM，并将剩余信号写回 blackboard。
    """
    from app.core.engine.nodes.supervisor import SupervisorNode
    from app.core.engine.state import AgentState
    from app.core.engine.signals.schemas import RouteToSignal
    from langchain_core.runnables import RunnableConfig

    node = SupervisorNode()
    pending_signals = [
        RouteToSignal(target="worker", reason="task2").model_dump(),
        RouteToSignal(target="worker", reason="task3").model_dump(),
    ]
    state = AgentState(messages=[], pending_signals=pending_signals)

    result = await node.prepare_state(state, RunnableConfig())

    assert result is not None, "应立即返回 StateUpdate，不需要 LLM"
    assert result.next_node == "worker"
    assert result.pending_signals is not None
    assert len(result.pending_signals) == 1
    assert result.pending_signals[0]["reason"] == "task3"


@pytest.mark.asyncio
async def test_supervisor_prepare_state_empty_queue_routes_normally():
    """
    T3: pending_signals 为空 + worker_outcome=success 时，
    Supervisor 清除 ticket 后返回 None，让 LLM 自行决策下一步路由。
    """
    from app.core.engine.nodes.supervisor import SupervisorNode
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    node = SupervisorNode()
    state = AgentState(messages=[], pending_signals=[], worker_outcome="success")

    result = await node.prepare_state(state, RunnableConfig())

    # 队列空 + worker_outcome=success → 清 ticket 并让 LLM 决策
    assert result is None

