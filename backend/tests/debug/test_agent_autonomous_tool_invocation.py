"""
Agent 自主触发工具的端到端集成测试。

核心设计：
- Graph: 真实 YAML 配置编译的 StateGraph（supervisor / worker / finish）
- Checkpointer: MemorySaver
- Engine: 真实的 AgentEngine，但注入 SmartMockInferenceEngine（模拟 LLM 决策）
- 工具执行: 完全真实（AgentToolExecutor → ToolExecutor → 真实工具函数）

验证点：
1. Agent（Mock LLM）自主决定调用 edit_file / apply_patch_file
2. 工具通过完整的生产链路被真实执行（hooks、diff tracking、ToolMessage 回传）
3. 文件修改正确落地
"""

import asyncio
import os
import sys

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 项目路径设置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------------------------
# 跳过需要 DB / 外部服务的环节
# ---------------------------------------------------------------------------
from app.core.engine.context_hydrator import EvoContextMiddleware
_orig_hydrate = EvoContextMiddleware.hydrate
async def _mock_hydrate(state, config):
    return state
EvoContextMiddleware.hydrate = _mock_hydrate

from app.core.engine.skill_hydrator import SkillHydrator
from app.core.engine.nodes.utils.skill_resolver import SkillResolver

_orig_get_node_skills = SkillHydrator.get_node_skills
async def _mock_get_node_skills(state, node_name):
    return []
SkillHydrator.get_node_skills = _mock_get_node_skills

_orig_inject_fallback = SkillResolver.inject_fallback_sops
async def _mock_inject_fallback(sops, config):
    return sops
SkillResolver.inject_fallback_sops = _mock_inject_fallback

# ---------------------------------------------------------------------------
# 修复 settings 缺失属性（Finish 节点 audit_service 需要）
# ---------------------------------------------------------------------------
from app.core.config import settings
if not hasattr(settings, "DEFAULT_PROJECT_ID"):
    object.__setattr__(settings, "DEFAULT_PROJECT_ID", 1)

# ---------------------------------------------------------------------------
# 导入核心组件
# ---------------------------------------------------------------------------
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph


# ---------------------------------------------------------------------------
# SmartMockInferenceEngine — 模拟 LLM 决策并真实执行工具
# ---------------------------------------------------------------------------
class SmartMockInferenceEngine(InferenceEngine):
    """
    Mock InferenceEngine，模拟 LLM 决定调用工具，
    然后通过真实的 tool_executor 执行工具调用。
    """

    def __init__(self, scenarios: dict):
        # 不调用 super().__init__，避免触发 LLMFactory 导入
        self._llm_factory = MagicMock()
        self._scenarios = scenarios
        self._counters = {}

    async def create_llm(self, model, temperature):
        return MagicMock(), "openai"

    def bind_tools(self, llm, tools):
        # 返回真实的 tool_map，让 AgentEngine 构建真实的 tool_executor
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
    ):
        idx = self._counters.get(name, 0)
        self._counters[name] = idx + 1

        scenario_list = self._scenarios.get(name, [])
        if idx >= len(scenario_list):
            # 默认返回完成消息
            ai_msg = AIMessage(content="任务完成")
            return {
                "messages": [ai_msg],
                "tool_history": [],
                "last_response": ai_msg,
                "is_truncated": False,
                "signal": None,
            }

        step = scenario_list[idx]
        new_messages = []
        local_tool_history = []

        # 1. 构建 AIMessage（可能包含 tool_calls）
        ai_msg = AIMessage(
            content=step.get("content", ""),
            tool_calls=step.get("tool_calls", []),
        )
        new_messages.append(ai_msg)

        # 2. 通过真实的 tool_executor 执行工具调用
        remaining = []
        for tc in step.get("tool_calls", []):
            if not interceptors or tc["name"] not in interceptors:
                remaining.append(tc)

        if remaining and tool_executor is not None:
            tool_results = await tool_executor.execute_batch(remaining, local_tool_history)
            new_messages.extend(tool_results)

        # 3. 如果场景定义了最终 AI 消息，追加它
        if step.get("final_content"):
            new_messages.append(AIMessage(content=step["final_content"]))

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": ai_msg,
            "is_truncated": False,
            "signal": step.get("signal"),
        }

    async def run_single_shot(self, llm_with_tools, messages, system_prompt, provider, config, name, tool_executor=None, interceptors=None):
        return await self.run_react_loop(
            llm_with_tools, messages, system_prompt, provider, config, name,
            max_steps=1, tool_executor=tool_executor, interceptors=interceptors
        )


# ---------------------------------------------------------------------------
# 测试辅助函数
# ---------------------------------------------------------------------------
def make_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def cleanup(path: str):
    if os.path.exists(path):
        os.remove(path)


async def read_checkpoint_messages(saver, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    cp = await saver.aget_tuple(cfg)
    if cp is None:
        return []
    return cp.checkpoint.get("channel_values", {}).get("messages", [])


# ---------------------------------------------------------------------------
# 通用 Graph 运行器
# ---------------------------------------------------------------------------
async def run_autonomous_scenario(scenarios: dict, thread_id: str, project_id: int = 43):
    """
    构建真实 Graph，注入 SmartMockInferenceEngine，运行一个完整的 Agent 回合。
    """
    saver = MemorySaver()
    config_path = os.path.join(BASE_DIR, "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    # 注入 SmartMockInferenceEngine
    smart_engine = AgentEngine(inference_engine=SmartMockInferenceEngine(scenarios))
    set_default_engine(smart_engine)

    # 设置 EvoContext
    ctx = EvoContext(thread_id=thread_id, project_id=project_id, active_model="mock-model")
    ContextManager.set(ctx)

    base_config = {"configurable": {"thread_id": thread_id, "model": "mock-model"}}

    # 运行 Graph
    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="请帮我修改文件")]),
        config=base_config,
    )

    return saver, base_config


# =============================================================================
# TEST 1: Agent 自主调用 edit_file
# =============================================================================
async def test_agent_autonomous_edit_file():
    print("\n" + "=" * 70)
    print("TEST 1: Agent 自主调用 edit_file")
    print("=" * 70)

    test_file = os.path.join(BASE_DIR, "_test_agent_edit.txt")
    original = "old content\nsecond line\n"
    make_file(test_file, original)

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="用户请求修改文件",
                    context=RoutingContext(topic="文件编辑"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "edit_file",
                        "args": {
                            "path": test_file,
                            "target": "old content",
                            "replacement": "new content",
                        },
                        "id": "tc-edit-1",
                    }
                ],
                "final_content": "文件已成功编辑。",
            },
        ],
    }

    saver, cfg = await run_autonomous_scenario(scenarios, "test-edit-file")

    # 验证文件内容
    content = read_file(test_file)
    assert "new content" in content, f"edit_file 未生效: {repr(content)}"
    assert "second line" in content, f"未修改行被意外改动: {repr(content)}"
    assert "old content" not in content, f"旧内容仍残留: {repr(content)}"

    # 验证 checkpoint 中包含 ToolMessage
    msgs = await read_checkpoint_messages(saver, "test-edit-file")
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) >= 1, f"checkpoint 中应有 ToolMessage，实际只有 {len(tool_msgs)} 个"
    assert any(m.name == "edit_file" for m in tool_msgs), "应有 edit_file 的 ToolMessage"

    cleanup(test_file)
    print("  ✅ Agent 自主调用 edit_file 验证通过")
    print(f"     文件内容: {repr(content)}")
    print(f"     Checkpoint ToolMessages: {len(tool_msgs)}")


# =============================================================================
# TEST 2: Agent 自主调用 edit_file 多编辑
# =============================================================================
async def test_agent_autonomous_multiedit_via_edit_file():
    print("\n" + "=" * 70)
    print("TEST 2: Agent 自主调用 edit_file 多编辑")
    print("=" * 70)

    test_file = os.path.join(BASE_DIR, "_test_agent_multiedit.txt")
    original = "line one\nline two\nline three\n"
    make_file(test_file, original)

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="批量编辑文件",
                    context=RoutingContext(topic="批量文件编辑"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "edit_file",
                        "args": {
                            "path": test_file,
                            "edits": [
                                {"target": "line one", "replacement": "LINE ONE"},
                                {"target": "line three", "replacement": "LINE THREE"},
                            ],
                        },
                        "id": "tc-multi-1",
                    }
                ],
                "final_content": "批量编辑完成。",
            },
        ],
    }

    saver, cfg = await run_autonomous_scenario(scenarios, "test-multiedit-file")

    content = read_file(test_file)
    assert "LINE ONE" in content, f"第一个 edit 未生效: {repr(content)}"
    assert "LINE THREE" in content, f"第二个 edit 未生效: {repr(content)}"
    assert "line two" in content, f"未修改行被意外改动: {repr(content)}"

    msgs = await read_checkpoint_messages(saver, "test-multiedit-file")
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert any(m.name == "edit_file" for m in tool_msgs), "应有 edit_file 的 ToolMessage"

    cleanup(test_file)
    print("  ✅ Agent 自主调用 edit_file 验证通过")
    print(f"     文件内容: {repr(content)}")


# =============================================================================
# TEST 3: Agent 自主调用 apply_patch_file（同一文件多 operation 缓存累积）
# =============================================================================
async def test_agent_autonomous_apply_patch_file():
    print("\n" + "=" * 70)
    print("TEST 3: Agent 自主调用 apply_patch_file（同一文件多 operation）")
    print("=" * 70)

    test_file = os.path.join(BASE_DIR, "_test_agent_patch.txt")
    original = "line one\nline two\nline three\nline four\n"
    make_file(test_file, original)

    patch = f"""*** Begin Patch

*** Update File: {test_file}
@@
-line one
+LINE ONE

*** Update File: {test_file}
@@
-line three
+LINE THREE

*** End Patch
"""

    scenarios = {
        "Supervisor": [
            {
                "content": '<route_to target="worker"/>',
                "signal": RouteToSignal(
                    target="worker",
                    reason="应用补丁",
                    context=RoutingContext(topic="补丁应用"),
                ),
            },
        ],
        "Worker": [
            {
                "tool_calls": [
                    {
                        "name": "apply_patch_file",
                        "args": {"patch_text": patch},
                        "id": "tc-patch-1",
                    }
                ],
                "final_content": "补丁应用完成。",
            },
        ],
    }

    saver, cfg = await run_autonomous_scenario(scenarios, "test-patch-file")

    content = read_file(test_file)
    assert "LINE ONE" in content, f"第一个 operation 未生效: {repr(content)}"
    assert "LINE THREE" in content, f"第二个 operation 未生效: {repr(content)}"
    assert "line two" in content, f"未修改行被意外改动: {repr(content)}"
    assert "line four" in content, f"未修改行被意外改动: {repr(content)}"

    msgs = await read_checkpoint_messages(saver, "test-patch-file")
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert any(m.name == "apply_patch_file" for m in tool_msgs), "应有 apply_patch_file 的 ToolMessage"

    cleanup(test_file)
    print("  ✅ Agent 自主调用 apply_patch_file 验证通过")
    print(f"     文件内容: {repr(content)}")


# =============================================================================
# 主入口
# =============================================================================
async def main():
    print("=" * 70)
    print("🚀 Agent 自主触发工具 — 端到端集成测试")
    print("=" * 70)

    await test_agent_autonomous_edit_file()
    await test_agent_autonomous_multiedit_via_edit_file()
    await test_agent_autonomous_apply_patch_file()

    print("\n" + "=" * 70)
    print("🎉 全部通过！Agent 自主触发工具的端到端链路验证成功。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
