#!/usr/bin/env python3.10
"""
直接调用 WorkerNode + 真实 LLM 测试工具链
跳过 Supervisor，手动构造 ExecutionTicket

Usage:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python3.10 tests/manual_worker_real_llm.py
"""
import asyncio
import os
import sys
import traceback

BASE_DIR = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend"
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------------------------
# 0. 环境
# ---------------------------------------------------------------------------
os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

from pathlib import Path
env_path = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value

# ---------------------------------------------------------------------------
# 1. Mock 数据库依赖（不改动系统代码）
# ---------------------------------------------------------------------------
from app.core.engine.context_hydrator import EvoContextMiddleware
async def _mock_hydrate(state, config):
    return state
EvoContextMiddleware.hydrate = _mock_hydrate

from app.core.engine.skill_hydrator import SkillHydrator
from app.core.engine.nodes.utils.skill_resolver import SkillResolver
async def _mock_get_node_skills(state, node_name):
    return []
SkillHydrator.get_node_skills = _mock_get_node_skills
async def _mock_inject_fallback(sops, config):
    return sops
SkillResolver.inject_fallback_sops = _mock_inject_fallback

# Mock activity monitor（避免 DB 调用）
from app.core.monitoring import activity
async def _noop(*args, **kwargs):
    pass
activity.activity_monitor.start_run = _noop
activity.activity_monitor.end_run = _noop
activity.activity_monitor.check_cancellation = _noop

# Patch SignalDispatcher：signal 为 None 时走 fallback 路径
from app.core.engine.signals.dispatcher import SignalDispatcher
_orig_dispatch = SignalDispatcher.dispatch
async def _patched_dispatch(state, signal, config):
    if signal is None:
        return None
    return await _orig_dispatch(state, signal, config)
SignalDispatcher.dispatch = staticmethod(_patched_dispatch)

# ---------------------------------------------------------------------------
# 2. 自定义 InferenceEngine：强制 direct 模式连接 LM Studio
# ---------------------------------------------------------------------------
from app.core.engine.inference_engine import InferenceEngine

class DirectInferenceEngine(InferenceEngine):
    async def create_llm(self, model, temperature):
        from app.infrastructure.llm.factory import LLMFactory
        llm = await LLMFactory.create_llm(
            model_name=model, temperature=temperature,
            base_url="http://localhost:1234/v1", api_key="not-needed",
            provider_type="openai",
        )
        return llm, self._detect_provider(llm)

# ---------------------------------------------------------------------------
# 3. 导入核心组件
# ---------------------------------------------------------------------------
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.nodes.worker import WorkerNode
from app.core.engine.state import AgentState, BlackboardState
from app.core.engine.state.config import ExecutionTicket, AgentRuntimeConfig
from app.core.config import settings

if not hasattr(settings, "DEFAULT_PROJECT_ID"):
    object.__setattr__(settings, "DEFAULT_PROJECT_ID", 1)
if not hasattr(settings, "WORKER_AGENT_MAX_STEPS"):
    object.__setattr__(settings, "WORKER_AGENT_MAX_STEPS", 10)

# ---------------------------------------------------------------------------
# 4. 初始化
# ---------------------------------------------------------------------------
agent_engine = AgentEngine(inference_engine=DirectInferenceEngine())
set_default_engine(agent_engine)

# ---------------------------------------------------------------------------
# 5. 构造 ExecutionTicket + AgentState
# ---------------------------------------------------------------------------
def make_state(user_message: str, tools: list[str] = None) -> AgentState:
    ticket = ExecutionTicket(
        ticket_type="task",
        topic=user_message[:50],
        agent_config=AgentRuntimeConfig(
            role_name="Explorer",
            system_instructions="你是一个文件系统探索助手。使用工具来完成任务。",
            tools=tools or ["list_dir", "read_file"],
        ),
    )
    blackboard = BlackboardState(ticket=ticket)
    return AgentState(
        messages=[HumanMessage(content=user_message)],
        blackboard=blackboard,
    )

# ---------------------------------------------------------------------------
# 6. 运行 Worker
# ---------------------------------------------------------------------------
async def run_worker(state: AgentState, model: str = "google/gemma-4-e4b"):
    thread_id = "manual-worker-test"
    ctx = EvoContext(
        thread_id=thread_id, project_id=1,
        active_model=model, working_directory=BASE_DIR,
    )
    ContextManager.set(ctx)
    config = RunnableConfig(configurable={
        "thread_id": thread_id, "model": model, "project_id": 1,
    })

    worker = WorkerNode()
    # 给 LLM 足够的步数完成任务
    worker.max_steps = 5
    result = await worker(state, config)
    return result


def print_result(result):
    msgs = getattr(result, "messages", None) or []
    print(f"\n[Result] next_node={getattr(result, 'next_node', 'N/A')}, messages={len(msgs)}")
    for i, msg in enumerate(msgs):
        tc = getattr(msg, "tool_calls", None)
        name = getattr(msg, "name", "")
        print(f"\n  [{i}] {type(msg).__name__}", end="")
        if name:
            print(f" name={name}", end="")
        if tc:
            print(f" tool_calls={len(tc)}")
            for t in tc:
                args = t.get("args", t.get("function", {}).get("arguments", {}))
                print(f"      → {t.get('name', '?')}: {str(args)[:120]}")
        else:
            print()
        c = getattr(msg, "content", "")
        if c and isinstance(c, str):
            preview = c[:400] + "..." if len(c) > 400 else c
            print(f"      content: {preview!r}")


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
async def main():
    print("=" * 70)
    print("WorkerNode + 真实 LLM 测试")
    print("=" * 70)

    # 场景：找 wechat 相关文件
    state = make_state(
        "在 software-ecommerce/addon 目录下找到 wechat 模块的配置文件。"
        "如果目录输出被截断，不要尝试 filter，直接缩小 path 范围进入子目录查看。"
        "最终读取 info.php 或 event.php 的内容。"
    )
    print(f"\n[Task] {state.messages[0].content}")

    result = await run_worker(state)
    print_result(result)

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
