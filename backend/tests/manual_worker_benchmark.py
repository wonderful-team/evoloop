#!/usr/bin/env python3.10
"""
WorkerNode + 真实 LLM 批量测试
多个场景，统计步数、工具调用序列、成功率
"""
import asyncio
import os
import sys
import time

BASE_DIR = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend"
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

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

# 1. Mock 依赖
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

from app.core.monitoring import activity
async def _noop(*args, **kwargs):
    pass
for m in ['start_run', 'end_run', 'check_cancellation', 'add_step', 'update_step', 'complete_step']:
    setattr(activity.activity_monitor, m, _noop)

from app.core.engine.signals.dispatcher import SignalDispatcher
_orig_dispatch = SignalDispatcher.dispatch
async def _patched_dispatch(state, signal, config):
    if signal is None:
        return None
    return await _orig_dispatch(state, signal, config)
SignalDispatcher.dispatch = staticmethod(_patched_dispatch)

# 2. 自定义 InferenceEngine
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

# 3. 导入核心组件
from langchain_core.messages import HumanMessage, ToolMessage
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

agent_engine = AgentEngine(inference_engine=DirectInferenceEngine())
set_default_engine(agent_engine)

# 4. 场景定义
SCENARIOS = [
    {
        "name": "找订单控制器",
        "task": "在 software-ecommerce 项目中找到处理订单流程的 PHP 控制器文件，读取 Order.php 的内容。",
        "target_file": "software-ecommerce/app/shopapi/controller/Order.php",
        "max_steps": 5,
    },
    {
        "name": "找支付控制器",
        "task": "找到 software-ecommerce 项目中负责支付逻辑的控制器文件，读取其内容。",
        "target_file": "software-ecommerce/app/pay/controller/Pay.php",
        "max_steps": 5,
    },
    {
        "name": "找数据库安装脚本",
        "task": "找到 software-ecommerce 项目的数据库安装 SQL 文件并读取。",
        "target_file": "software-ecommerce/app/install/source/database.sql",
        "max_steps": 5,
    },
    {
        "name": "找前端 QuestionRenderer",
        "task": "在 software-ecommerce/src 目录下找到 QuestionRenderer 组件文件并读取。",
        "target_file": "software-ecommerce/src/components/QuestionRenderer.js",
        "max_steps": 5,
    },
    {
        "name": "找 wechat 配置",
        "task": "在 software-ecommerce/addon 目录下找到 wechat 模块的配置文件并读取 info.php。",
        "target_file": "software-ecommerce/addon/wechat/config/info.php",
        "max_steps": 5,
    },
]

# 5. 运行单个场景
async def run_scenario(scenario: dict, model: str = "google/gemma-4-e4b") -> dict:
    ticket = ExecutionTicket(
        ticket_type="task",
        topic=scenario["name"],
        agent_config=AgentRuntimeConfig(
            role_name="Explorer",
            system_instructions="你是一个文件系统探索助手。使用 list_directory 和 read_file 工具来完成任务。",
            tools=["list_directory", "read_file"],
        ),
    )
    blackboard = BlackboardState(ticket=ticket)
    state = AgentState(
        messages=[HumanMessage(content=scenario["task"])],
        blackboard=blackboard,
    )

    thread_id = f"bench-{scenario['name']}"
    ctx = EvoContext(thread_id=thread_id, project_id=1, active_model=model, working_directory=BASE_DIR)
    ContextManager.set(ctx)
    config = RunnableConfig(configurable={"thread_id": thread_id, "model": model, "project_id": 1})

    worker = WorkerNode()
    worker.max_steps = scenario["max_steps"]

    start = time.perf_counter()
    try:
        result = await worker(state, config)
    except Exception as e:
        return {
            "name": scenario["name"],
            "error": str(e),
            "steps": 0,
            "tool_calls": [],
            "found_target": False,
            "elapsed_ms": (time.perf_counter() - start) * 1000,
        }
    elapsed = (time.perf_counter() - start) * 1000

    msgs = getattr(result, "messages", None) or []
    tool_calls = []
    found_target = False
    step_count = 0

    for msg in msgs:
        if isinstance(msg, ToolMessage) and msg.name == "read_file":
            step_count += 1
            if scenario["target_file"] in str(msg.content):
                found_target = True
        tc = getattr(msg, "tool_calls", None)
        if tc:
            for t in tc:
                args = t.get("args", t.get("function", {}).get("arguments", {}))
                tool_calls.append({
                    "tool": t.get("name", "?"),
                    "path": args.get("path", "?") if isinstance(args, dict) else "?",
                })

    if step_count == 0:
        step_count = len([m for m in msgs if getattr(m, "tool_calls", None)])

    return {
        "name": scenario["name"],
        "error": None,
        "steps": step_count,
        "tool_calls": tool_calls,
        "found_target": found_target,
        "truncated": "[TRUNCATION]" in str(msgs[-1].content) if msgs else False,
        "elapsed_ms": elapsed,
    }


# 6. 主程序
async def main():
    print("=" * 80)
    print("WorkerNode + 真实 LLM 批量测试")
    print(f"模型: google/gemma-4-e4b | 场景数: {len(SCENARIOS)}")
    print("=" * 80)

    results = []
    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"\n[{i}/{len(SCENARIOS)}] 场景: {scenario['name']}")
        print(f"     任务: {scenario['task'][:60]}...")
        r = await run_scenario(scenario)
        results.append(r)

        status = "OK" if r["found_target"] else ("TRUNC" if r["truncated"] else "FAIL")
        print(f"     结果: {status} | 步数: {r['steps']} | 耗时: {r['elapsed_ms']:.0f}ms")
        for tc in r["tool_calls"]:
            print(f"         -> {tc['tool']}({tc['path']})")

    print("\n" + "=" * 80)
    print("汇总")
    print("=" * 80)
    success = sum(1 for r in results if r["found_target"])
    print(f"成功率: {success}/{len(results)} ({success/len(results)*100:.0f}%)")
    print(f"总耗时: {sum(r['elapsed_ms'] for r in results):.0f}ms")
    print()
    print(f"{'场景':<20} {'步数':>4} {'成功':>4} {'截断':>4} {'耗时(ms)':>10}")
    print("-" * 50)
    for r in results:
        print(f"{r['name']:<20} {r['steps']:>4} {'Y' if r['found_target'] else 'N':>4} {'Y' if r['truncated'] else 'N':>4} {r['elapsed_ms']:>10.0f}")


if __name__ == "__main__":
    asyncio.run(main())
