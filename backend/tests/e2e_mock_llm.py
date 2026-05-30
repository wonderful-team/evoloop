"""
MockInferenceEngine — 仅用于 E2E/集成测试，替换真实 LLM 调用。

除了 LLM 推理外，所有其他组件（数据库、路由、AuditService、Hooks、事件总线）
都使用真实实现。这是为了保证测试的真实性。
"""
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.signals.schemas import RouteToSignal
from app.core.engine.signals.handlers.routing import RoutingContext
from app.core.engine.routers import RoutingTarget


class MockInferenceEngine(InferenceEngine):
    """
    替换 InferenceEngine 的 LLM 调用，返回预定义的确定性响应。
    """

    def __init__(self, responses: dict[str, list[dict]] | None = None):
        # 不调用 super().__init__，避免触发 LLMFactory 导入
        self._llm_factory = MagicMock()
        self._responses = responses or {}

    async def create_llm(self, model, temperature):
        return MagicMock(), "openai"

    def bind_tools(self, llm, tools):
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
    ):
        return self._make_response(name, config, messages)

    async def run_single_shot(
        self,
        llm_with_tools,
        messages,
        system_prompt,
        provider,
        config,
        name,
        tool_executor=None,
    ):
        return self._make_response(name, config, messages)

    def _make_response(self, name: str, config, messages):
        """根据节点名称生成 deterministic 的 LLM 响应。"""
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")

        node_responses = self._responses.get(name, [])
        if node_responses:
            idx = getattr(self, f"_idx_{name}", 0)
            resp = node_responses[idx % len(node_responses)]
            setattr(self, f"_idx_{name}", idx + 1)
        else:
            resp = self._default_response(name, thread_id)

        ai_msg = AIMessage(
            content=resp.get("content", ""),
            metadata=resp.get("metadata", {}),
        )
        return {
            "messages": [ai_msg],
            "tool_history": resp.get("tool_history", []),
            "last_response": ai_msg,
            "is_truncated": resp.get("is_truncated", False),
            "signal": resp.get("signal"),
        }

    def _default_response(self, name: str, thread_id: str):
        """默认响应 —— 让 graph 能正常流转到 finish。"""
        if name == "Supervisor":
            return {
                "content": f'<route_to target="worker" reason="处理用户请求"/>',
                "signal": RouteToSignal(
                    target=RoutingTarget.WORKER,
                    reason="处理用户请求",
                    context=RoutingContext(topic="用户请求"),
                ),
            }
        if name == "Worker":
            return {
                "content": "```python\ndef quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[0]\n    left = [x for x in arr[1:] if x < pivot]\n    right = [x for x in arr[1:] if x >= pivot]\n    return quicksort(left) + [pivot] + quicksort(right)\n```",
                "metadata": {},
            }
        if name == "Finish":
            return {
                "content": f"<evoloop_session_audit>Session completed successfully for {thread_id}</evoloop_session_audit>",
            }
        return {"content": f"Mock response from {name}"}


def make_mock_engine(responses: dict | None = None):
    """创建带有 MockInferenceEngine 的 AgentEngine。"""
    from app.core.engine.engine import AgentEngine
    return AgentEngine(inference_engine=MockInferenceEngine(responses))
