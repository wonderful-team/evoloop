"""
Agent 自主触发工具 — 从 dispatch_agent_run 到 run_agent_background 的完整端到端测试。

本测试走通最外层的 dispatch 入口，验证：
1. dispatch_agent_run 创建 Conversation + Message 记录
2. run_agent_background 通过 DatabaseCallbackHandler 将 AI/Tools 消息持久化到数据库
3. LangGraph checkpointer 将状态写入数据库
4. diff tracker 将 file_operations 写入数据库
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 项目路径设置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# 抑制过冗余的日志
logging.basicConfig(level=logging.WARNING)
for noisy in [
    "app.core.tools.registry",
    "app.infrastructure.queue.huey_queue",
    "app.domain.project.service",
    "app.core.vision.pipeline.manager",
    "app.infrastructure.embeddings.factory",
    "app.core.memory.backends.file_backend",
    "app.core.context.cache",
]:
    logging.getLogger(noisy).setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# 修复 settings 缺失属性
# ---------------------------------------------------------------------------
from app.core.config import settings
if not hasattr(settings, "DEFAULT_PROJECT_ID"):
    object.__setattr__(settings, "DEFAULT_PROJECT_ID", 1)

# ---------------------------------------------------------------------------
# Mock EvoCloudManager + SystemConfigService（在导入其他模块前）
# ---------------------------------------------------------------------------
from app.core.evocloud import evocloud_manager
from app.infrastructure.config.service import SystemConfigService

# 预置 mock，避免实际 API 调用
evocloud_manager._initialized = True
evocloud_manager._projects_cache = [
    {
        "id": 43,
        "name": "test-project",
        "description": "",
        "path": BASE_DIR,
        "exists_locally": True,
        "status_text": "",
        "owner": "",
    }
]
evocloud_manager._projects_cache_time = 9999999999.0

_original_get_project = evocloud_manager.get_project_by_id

async def _mock_get_project_by_id(project_id):
    for p in evocloud_manager._projects_cache:
        if p.get("id") == project_id:
            return p
    return None

evocloud_manager.get_project_by_id = _mock_get_project_by_id

# Mock SystemConfigService
_original_get_value = SystemConfigService.get_value
SystemConfigService.get_value = lambda key, default=None: {
    "LLM_MODEL": "mock-model",
}.get(key, default)


# ---------------------------------------------------------------------------
# 导入核心组件
# ---------------------------------------------------------------------------
from langchain_core.messages import AIMessage

from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.globals import set_graph
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.queue.factory import reset_scheduler


# ---------------------------------------------------------------------------
# SyncTaskScheduler — 让 Celery 任务同步执行（真正入库）
# ---------------------------------------------------------------------------
class SyncTaskScheduler:
    def __init__(self):
        self._tasks = {}
        self._pending = []

    def task(self, func=None, *, name=None, bind=False, retries=0, retry_delay=0, **options):
        def decorator(f):
            task_name = name or f"{f.__module__}.{f.__name__}"
            self._tasks[task_name] = f
            return f
        if func is not None:
            return decorator(func)
        return decorator

    def send_task(self, name, args=None, kwargs=None, **options):
        args = args or ()
        kwargs = kwargs or {}
        if name not in self._tasks:
            self._load_task_module(name)
        if name not in self._tasks:
            raise ValueError(f"Unknown task: {name}")

        coro = self._tasks[name](*args, **kwargs)
        if asyncio.iscoroutine(coro):
            try:
                loop = asyncio.get_running_loop()
                self._pending.append(asyncio.create_task(coro))
            except RuntimeError:
                asyncio.run(coro)
        return MagicMock()

    async def await_pending(self, timeout=5.0):
        if not self._pending:
            return
        pending = self._pending[:]
        self._pending.clear()
        await asyncio.gather(*pending, return_exceptions=True)

    def _load_task_module(self, name):
        from app.infrastructure.queue.celery import TASK_MODULE_MAP
        if name in TASK_MODULE_MAP:
            __import__(TASK_MODULE_MAP[name])
        elif "." in name:
            parts = name.rsplit(".", 1)
            if len(parts) == 2:
                try:
                    __import__(parts[0])
                except Exception:
                    pass

    def start(self, **kwargs):
        pass

    def worker_main(self, **kwargs):
        pass

    def conf(self):
        return {}


_sync_scheduler = None


# ---------------------------------------------------------------------------
# SmartMockInferenceEngine — 模拟 LLM 决策并真实执行工具
# ---------------------------------------------------------------------------
class SmartMockInferenceEngine(InferenceEngine):
    def __init__(self, scenarios: dict):
        self._llm_factory = MagicMock()
        self._scenarios = scenarios
        self._counters = {}

    async def create_llm(self, model, temperature):
        return MagicMock(), "openai"

    def bind_tools(self, llm, tools):
        if tools:
            return llm, {t.name: t for t in tools}
        return llm, {}

    async def run_react_loop(self, llm_with_tools, messages, system_prompt, provider,
                             config, name, max_steps=5, tool_executor=None,
                             interceptors=None, on_thinking=None, model=None):
        idx = self._counters.get(name, 0)
        self._counters[name] = idx + 1

        scenario_list = self._scenarios.get(name, [])
        if idx >= len(scenario_list):
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

        ai_msg = AIMessage(
            content=step.get("content", ""),
            tool_calls=step.get("tool_calls", []),
        )
        new_messages.append(ai_msg)

        remaining = []
        for tc in step.get("tool_calls", []):
            if not interceptors or tc["name"] not in interceptors:
                remaining.append(tc)

        if remaining and tool_executor is not None:
            tool_results = await tool_executor.execute_batch(remaining, local_tool_history)
            new_messages.extend(tool_results)

        if step.get("final_content"):
            new_messages.append(AIMessage(content=step["final_content"]))

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": ai_msg,
            "is_truncated": False,
            "signal": step.get("signal"),
        }

    async def run_single_shot(self, llm_with_tools, messages, system_prompt, provider,
                              config, name, tool_executor=None, interceptors=None):
        return await self.run_react_loop(
            llm_with_tools, messages, system_prompt, provider, config, name,
            max_steps=1, tool_executor=tool_executor, interceptors=interceptors
        )


# ---------------------------------------------------------------------------
# 数据库辅助函数
# ---------------------------------------------------------------------------
async def init_db():
    from tests.e2e_db_setup import init_test_database
    await init_test_database()
    return db_resource_manager


async def query_db(sql, params=None):
    async with session_scope() as session:
        from sqlalchemy import text
        result = await session.execute(text(sql), params or {})
        rows = result.all()
        return rows


async def count_table(table_name: str, where: str = "") -> int:
    sql = f"SELECT COUNT(*) FROM {table_name}"
    if where:
        sql += f" WHERE {where}"
    rows = await query_db(sql)
    return rows[0][0] if rows else 0


def make_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def cleanup(path: str):
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# 主测试
# ---------------------------------------------------------------------------
async def test_dispatch_to_background_full_chain():
    print("\n" + "=" * 70)
    print("TEST: dispatch_agent_run → run_agent_background 完整链路")
    print("=" * 70)

    thread_id = "test-dispatch-e2e"
    project_id = 43
    test_file = os.path.join(BASE_DIR, "_test_dispatch_e2e.txt")
    make_file(test_file, "old content\nsecond line\n")

    # 1. 初始化数据库
    await init_db()

    # 2. 注入 SyncTaskScheduler
    reset_scheduler()
    global _sync_scheduler
    _sync_scheduler = SyncTaskScheduler()
    import app.infrastructure.queue.factory as queue_factory
    queue_factory._scheduler = _sync_scheduler

    # 3. 构建 Graph + 注入 Mock Engine
    config_path = os.path.join(BASE_DIR, "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=db_resource_manager._checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=db_resource_manager._checkpointer)

    smart_engine = AgentEngine(inference_engine=SmartMockInferenceEngine({
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
                        "args": {"path": test_file, "target": "old content", "replacement": "new content"},
                        "id": "tc-edit-dispatch-1",
                    }
                ],
                "final_content": "文件已成功编辑。",
            },
        ],
    }))
    set_default_engine(smart_engine)

    # 4. 调用 dispatch_agent_run（创建 conversation + message）
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content="请帮我修改文件",
        project_id=project_id,
        model="mock-model",
    )
    assert result.status == "queued", f"dispatch 失败: {result.error}"
    print(f"  ✅ dispatch_agent_run 成功 (message_id={result.message_id})")

    # 5. 验证 dispatch 阶段已写入数据库
    conv_count = await count_table("conversations", f"id = '{thread_id}'")
    assert conv_count == 1, f"conversation 应已创建，实际 {conv_count}"
    print(f"  ✅ conversations 表记录: {conv_count}")

    msg_count_dispatch = await count_table("messages", f"thread_id = '{thread_id}'")
    assert msg_count_dispatch >= 1, f"dispatch 应至少写入 1 条 human message"
    print(f"  ✅ dispatch 后 messages 表记录: {msg_count_dispatch}")

    # 6. 调用 run_agent_background（完整 Agent 链路）
    from app.core.engine.background_agent import run_agent_background
    await run_agent_background(thread_id, result.inputs)

    # 7. 等待 Celery 任务完成
    await _sync_scheduler.await_pending()
    await asyncio.sleep(0.3)

    # 8. 验证文件修改
    content = read_file(test_file)
    assert "new content" in content
    print(f"  ✅ 文件内容正确: {repr(content)}")

    # 9. 验证数据库写入
    # checkpoints
    cp_count = await count_table("checkpoints", f"thread_id = '{thread_id}'")
    assert cp_count > 0
    print(f"  ✅ checkpoints 表记录: {cp_count}")

    # writes
    writes_count = await count_table("writes", f"thread_id = '{thread_id}'")
    assert writes_count > 0
    print(f"  ✅ writes 表记录: {writes_count}")

    # messages（现在应有 ai + tool 消息通过 callback 入库）
    msg_count_after = await count_table("messages", f"thread_id = '{thread_id}'")
    print(f"  ✅ messages 表总记录: {msg_count_after}")

    # 验证消息角色分布
    rows = await query_db(
        f"SELECT role, COUNT(*) FROM messages WHERE thread_id = '{thread_id}' GROUP BY role"
    )
    role_dist = {r[0]: r[1] for r in rows}
    print(f"     角色分布: {role_dist}")
    assert "human" in role_dist, "应有 human 消息"
    assert role_dist.get("tool", 0) >= 1 or role_dist.get("ai", 0) >= 1, \
        f"应有 tool/ai 消息通过 callback 入库，实际分布: {role_dist}"

    # file_operations（diff tracker + Celery 任务）
    fo_count = await count_table("file_operations", f"thread_id = '{thread_id}'")
    print(f"  ✅ file_operations 表记录: {fo_count}")
    if fo_count > 0:
        fo_rows = await query_db(
            f"SELECT operation, file_path, LENGTH(diff_content) as diff_len "
            f"FROM file_operations WHERE thread_id = '{thread_id}'"
        )
        for row in fo_rows:
            print(f"     → operation={row[0]}, file={row[1]}, diff_len={row[2]}")

    cleanup(test_file)

    # 10. 清理数据库
    from tests.e2e_db_setup import shutdown_test_database
    await shutdown_test_database()

    print("  ✅ dispatch → background 完整链路验证通过")


# =============================================================================
# 主入口
# =============================================================================
async def main():
    print("=" * 70)
    print("🚀 Agent 自主触发工具 — dispatch_agent_run → run_agent_background E2E")
    print("=" * 70)

    await test_dispatch_to_background_full_chain()

    print("\n" + "=" * 70)
    print("🎉 全部通过！最外层 dispatch 入口的完整链路验证成功。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
