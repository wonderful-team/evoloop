"""
端到端修复验证 — 验证多轮对话核心路径

覆盖：
1. SignalDispatcher: signal=None 时返回 None（防止 Supervisor→Chat 循环）
2. TokenFilter: 过滤 hidden audit tags
3. DatabaseCallbackHandler: 提取原生 reasoning_content
4. ChatNode: fallback 返回 FINISH
5. MessageHandler.stream_token: TokenEvent 格式正确
"""

import pytest


# =============================================================================
# 1. SignalDispatcher — signal=None 必须返回 None
# =============================================================================
@pytest.mark.asyncio
async def test_signal_dispatcher_none_returns_none():
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    config = RunnableConfig()

    result = await SignalDispatcher.dispatch(state, None, config)
    assert result is None, f"Expected None, got {result}"


@pytest.mark.asyncio
async def test_signal_dispatcher_route_to_signal_returns_state_update():
    """RouteToSignal 仍然正常工作"""
    from app.core.engine.signals.dispatcher import SignalDispatcher
    from app.core.engine.signals.schemas import RouteToSignal
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    state = AgentState(messages=[])
    config = RunnableConfig()
    signal = RouteToSignal(target="chat", reason="test routing")

    result = await SignalDispatcher.dispatch(state, signal, config)
    # signal_manager 会处理 RouteToSignal，返回 StateUpdate
    assert result is not None


# =============================================================================
# 2. TokenFilter — 过滤 hidden audit tags
# =============================================================================
def test_token_filter_hidden_audit_tags():
    """Hidden audit tags should be suppressed from publish stream"""
    from app.core.engine.callbacks.token_filter import TokenFilter

    f = TokenFilter()
    tokens = ['H', 'i', '<', 'e', 'v', 'o', 'l', 'o', 'o', 'p', '_', 's', 'e', 's', 's', 'i', 'o', 'n', '_', 'a', 'u', 'd', 'i', 't', '>', 's', 'e', 'c', 'r', 'e', 't', '<', '/', 'e', 'v', 'o', 'l', 'o', 'o', 'p', '_', 's', 'e', 's', 's', 'i', 'o', 'n', '_', 'a', 'u', 'd', 'i', 't', '>', 'B', 'y', 'e']
    publish_results = []
    for t in tokens:
        pub, _ = f.process(t)
        if pub is not None:
            publish_results.append(pub)

    filtered = ''.join(publish_results)
    assert 'secret' not in filtered.lower()
    assert 'Hi' in filtered
    assert 'Bye' in filtered


# =============================================================================
# 3. DatabaseCallbackHandler — 提取原生 reasoning_content
# =============================================================================
def test_extract_thinking_native_reasoning():
    """Native reasoning_content via additional_kwargs"""
    from app.core.engine.message.reasoning import extract_reasoning_from_kwargs

    # Native reasoning_content
    thinking = extract_reasoning_from_kwargs({"reasoning_content": "deep analysis"})
    assert thinking == "deep analysis"

    # No reasoning_content
    thinking2 = extract_reasoning_from_kwargs({})
    assert thinking2 is None

    # None additional_kwargs
    thinking3 = extract_reasoning_from_kwargs(None)
    assert thinking3 is None


# =============================================================================
# 4. ChatNode — fallback 返回 FINISH
# =============================================================================
@pytest.mark.asyncio
async def test_chat_node_fallback_returns_finish():
    """Chat 节点完成后必须返回 FINISH，不能返回 supervisor"""
    from app.core.engine.nodes.chat import ChatNode
    from app.core.engine.engine import EngineResult
    from app.core.engine.state import AgentState
    from langchain_core.runnables import RunnableConfig

    node = ChatNode()
    state = AgentState(messages=[])
    config = RunnableConfig()
    engine_result = EngineResult(messages=[])

    outcome = await node._build_fallback_outcome(state, engine_result, config)
    assert outcome.next_node == "finish", f"Expected finish, got {outcome.next_node}"


# =============================================================================
# 5. MessageHandler.stream_token — TokenEvent 格式
# =============================================================================
@pytest.mark.asyncio
async def test_stream_token_publishes_token_event():
    """stream_token 发布的是 TokenEvent，格式匹配前端期望"""
    from app.core.engine.message.handler import MessageHandler
    from app.core.engine.message.broker import get_message_broker
    from app.infrastructure.cache import get_cache
    
    # Reset cached singletons to prevent leaks from other tests
    get_message_broker.__globals__["_message_broker"] = None
    get_cache.__globals__["_cache_instance"] = None

    broker = get_message_broker()
    ps = broker.pubsub()
    await ps.subscribe("chat:test-stream-token:events")

    # thread_id 不要带 "chat:" 前缀，stream_token 会自动拼接
    await MessageHandler.stream_token("test-stream-token", "hello")

    msg = await ps.get_message(ignore_subscribe_messages=True, timeout=2.0)
    await ps.close()


    assert msg is not None, "No message received from pubsub"
    import json
    data = json.loads(msg["data"])
    assert data["type"] == "token"
    assert data["content"] == "hello"
