"""
全链路回归测试 — 验证 Agent Graph 所有主要路由路径

覆盖链路：
1. Supervisor -> Chat -> Finish
2. Supervisor -> Worker -> Finish
3. Supervisor -> Worker -> Finish(失败) -> Supervisor -> Worker -> Finish
4. Supervisor -> Worker(Subtask) -> Finish
5. Supervisor -> Aggregator -> Supervisor
6. Supervisor -> SequentialWorkflow -> Finish/Supervisor
7. Supervisor -> Finish (直接结束)
8. Chat -> Supervisor (已修复，防止循环)
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


# =============================================================================
# Graph 构建测试
# =============================================================================
def test_graph_builds_without_errors():
    """agent_main.yaml 能正确编译成 LangGraph"""
    from app.core.engine.graph_builder import GraphBuilder
    import os

    builder = GraphBuilder()
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../../../app/core/engine/config/agent_main.yaml"
    )
    config_path = os.path.abspath(config_path)

    workflow = builder.build(config_path)
    assert workflow is not None

    # 验证所有节点都存在
    nodes = workflow.get_graph().nodes
    node_ids = {n for n in nodes.keys()}
    expected = {"supervisor", "worker", "chat", "finish", "aggregator", "sequential_workflow"}
    assert expected.issubset(node_ids), f"Missing nodes: {expected - node_ids}"


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
    assert route_by_next_node(state) == "supervisor"


def test_route_finish_blocked_by_hook():
    """Finish 被 hook 阻塞时返回 Supervisor"""
    from app.core.engine.routers import route_finish
    from app.core.engine.state import AgentState
    from app.core.engine.state.blackboard import BlackboardState

    blackboard = BlackboardState(metadata={"blocked_by_hook": True})
    state = AgentState(messages=[], blackboard=blackboard.model_dump())
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
async def test_route_supervisor_chat_target():
    """Supervisor 路由到 chat"""
    from app.core.engine.routers import route_supervisor
    from app.core.engine.state import AgentState

    state = AgentState(messages=[], next_node="chat")
    result = route_supervisor(state)
    assert result == "chat"


@pytest.mark.asyncio
async def test_route_supervisor_worker_target_with_ticket():
    """Supervisor 路由到 worker（有 ticket）"""
    from app.core.engine.routers import route_supervisor
    from app.core.engine.state import AgentState
    from app.core.engine.state.blackboard import BlackboardState

    from app.core.engine.state.blackboard import ExecutionTicket
    blackboard = BlackboardState()
    blackboard.ticket = ExecutionTicket(topic="test", reason="test", ticket_type="task")
    state = AgentState(messages=[], next_node="worker", blackboard=blackboard.model_dump())
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
async def test_signal_dispatcher_route_to_chat():
    """RouteToSignal -> chat 正常工作"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.signals.schemas import RouteToSignal
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    signal = RouteToSignal(target="chat", reason="test routing")
    result = await SignalDispatcher.dispatch(state, signal, RunnableConfig())
    assert result is not None
    assert result.next_node == "chat"


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
async def test_signal_dispatcher_spawn_subtasks():
    """SpawnSubtasksSignal 正常工作"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.signals.schemas import SpawnSubtasksSignal
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    signal = SpawnSubtasksSignal()
    result = await SignalDispatcher.dispatch(state, signal, RunnableConfig())
    assert result is not None


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
async def test_chat_node_fallback():
    """Chat 节点 fallback 返回 FINISH"""
    from app.core.engine.nodes.chat import ChatNode
    from app.core.engine.engine import EngineResult
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    node = ChatNode()
    state = AgentState(messages=[])
    engine_result = EngineResult(messages=[])

    outcome = await node._build_fallback_outcome(state, engine_result, RunnableConfig())
    assert outcome.next_node == "finish"


@pytest.mark.asyncio
async def test_worker_node_fallback():
    """Worker 节点 fallback 返回 SUPERVISOR（以便 Supervisor 继续决策）"""
    from app.core.engine.nodes.worker import WorkerNode
    from app.core.engine.engine import EngineResult
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    from app.core.engine.state.blackboard import ExecutionTicket, BlackboardState
    node = WorkerNode()
    blackboard = BlackboardState()
    blackboard.ticket = ExecutionTicket(topic="test", reason="test", ticket_type="task")
    state = AgentState(messages=[], blackboard=blackboard.model_dump())
    engine_result = EngineResult(messages=[])

    outcome = await node._build_fallback_outcome(state, engine_result, RunnableConfig())
    assert outcome.next_node == "supervisor"


@pytest.mark.asyncio
async def test_supervisor_node_fallback():
    """Supervisor 节点 fallback 返回 FINISH（兜底安全网）"""
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
async def test_aggregator_node_returns_supervisor():
    """Aggregator 节点返回 SUPERVISOR"""
    from app.core.engine.nodes.aggregator import AggregatorNode
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    node = AggregatorNode()
    state = AgentState(messages=[])

    result = await node(state, RunnableConfig())
    assert result.next_node == "supervisor"


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
# Graph 条件边映射完整性测试
# =============================================================================
def test_chat_node_edge_map_has_all_targets():
    """chat 节点的条件边映射包含所有可能的目标"""
    from app.core.engine.graph_builder import GraphBuilder
    import os

    builder = GraphBuilder()
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../../../app/core/engine/config/agent_main.yaml"
    )
    config_path = os.path.abspath(config_path)

    workflow = builder.build(config_path)
    graph = workflow.get_graph()

    # 验证 chat 节点的出边
    edges = graph.edges
    chat_edges = [e for e in edges if e[0] == "chat"]
    targets = {e[1] for e in chat_edges}

    assert "finish" in targets, "chat -> finish 边缺失"
    assert "__end__" in targets or "END" in targets, "chat -> END 边缺失"


def test_worker_node_edge_map_has_all_targets():
    """worker 节点的条件边映射包含所有可能的目标"""
    from app.core.engine.graph_builder import GraphBuilder
    import os

    builder = GraphBuilder()
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../../../app/core/engine/config/agent_main.yaml"
    )
    config_path = os.path.abspath(config_path)

    workflow = builder.build(config_path)
    graph = workflow.get_graph()

    edges = graph.edges
    worker_edges = [e for e in edges if e[0] == "worker"]
    targets = {e[1] for e in worker_edges}

    assert "supervisor" in targets, "worker -> supervisor 边缺失"
    assert "sequential_workflow" in targets, "worker -> sequential_workflow 边缺失"
    assert "finish" in targets, "worker -> finish 边缺失"


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
