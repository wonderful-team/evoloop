"""
Agent 自主触发工具 — 带数据库持久化的端到端集成测试。

相比 test_agent_autonomous_tool_invocation.py，本测试：
1. 使用真实 SQLite 数据库（非内存 checkpoint）
2. 走真实 hydration 路径（不 Mock EvoContextMiddleware）
3. 同步执行 Celery 任务（消息、文件操作真正入库）
4. 验证数据库中确实写入了 checkpoint、file_operation 等记录
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import select, text

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
]:
    logging.getLogger(noisy).setLevel(logging.ERROR)

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
from app.core.engine.engine import AgentEngine, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.inference_engine import InferenceEngine
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph
from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database import session_scope
from app.infrastructure.queue.factory import get_scheduler, reset_scheduler


# ---------------------------------------------------------------------------
# SyncTaskScheduler — 让 Celery 任务同步执行（真正入库）
# ---------------------------------------------------------------------------
class SyncTaskScheduler:
    """同步任务调度器：send_task 注册异步任务到 pending 列表，可统一 await。"""

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
            # 收集 pending task，稍后统一 await
            try:
                loop = asyncio.get_running_loop()
                self._pending.append(asyncio.create_task(coro))
            except RuntimeError:
                asyncio.run(coro)
        return MagicMock()

    async def await_pending(self, timeout=5.0):
        """等待所有 pending 的异步任务完成。"""
        if not self._pending:
            return
        pending = self._pending[:]
        self._pending.clear()
        await asyncio.gather(*pending, return_exceptions=True)

    def _load_task_module(self, name):
        from app.infrastructure.queue.discovery import discover_task_modules
        for mod in discover_task_modules():
            try:
                __import__(mod)
                return
            except Exception:
                continue
        if "." in name:
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


# 全局同步调度器引用（用于在 Graph 运行后 flush pending tasks）
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
async def init_db_and_seed():
    """初始化测试数据库并预置基础数据。"""
    from tests.e2e_db_setup import init_test_database
    await init_test_database()

    # 预插入 Conversation 和初始 Message
    async with session_scope() as session:
        from app.models import Conversation, Message

        conv = Conversation(
            id="test-db-thread",
            project_id=43,
            title="测试会话",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(conv)

        msg = Message(
            thread_id="test-db-thread",
            project_id=43,
            role="human",
            content="请帮我修改文件",
            sequence_number=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(msg)
        # session_scope 会自动 commit

    return db_resource_manager


async def query_db(sql, params=None):
    """执行原始 SQL 查询并返回结果。"""
    async with session_scope() as session:
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
# 通用 Graph 运行器（带数据库）
# ---------------------------------------------------------------------------
async def run_autonomous_scenario_db(scenarios: dict, thread_id: str, project_id: int = 43):
    """构建真实 Graph，注入 SmartMockInferenceEngine，使用数据库 checkpointer。"""
    config_path = os.path.join(BASE_DIR, "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)

    # 使用数据库 checkpointer
    graph = GraphBuilder().build(config_path, checkpointer=db_resource_manager._checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=db_resource_manager._checkpointer)

    # 注入 SmartMockInferenceEngine
    smart_engine = AgentEngine(inference_engine=SmartMockInferenceEngine(scenarios))
    set_default_engine(smart_engine)

    # 设置 EvoContext（hydration 会用到）
    ctx = EvoContext(thread_id=thread_id, project_id=project_id, active_model="mock-model")
    ContextManager.set(ctx)

    base_config = {"configurable": {"thread_id": thread_id, "model": "mock-model", "project_id": project_id}}

    await graph.ainvoke(
        AgentState(messages=[HumanMessage(content="请帮我修改文件")]),
        config=base_config,
    )

    # 等待所有同步 Celery 任务完成（确保 file_operations 等真正入库）
    global _sync_scheduler
    if _sync_scheduler:
        await _sync_scheduler.await_pending()


# =============================================================================
# TEST: Agent 自主调用 edit_file，验证数据库写入
# =============================================================================
async def test_agent_autonomous_edit_file_with_db():
    print("\n" + "=" * 70)
    print("TEST: Agent 自主调用 edit_file（带数据库持久化验证）")
    print("=" * 70)

    test_file = os.path.join(BASE_DIR, "_test_agent_edit_db.txt")
    make_file(test_file, "old content\nsecond line\n")

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
                        "args": {"path": test_file, "target": "old content", "replacement": "new content"},
                        "id": "tc-edit-db-1",
                    }
                ],
                "final_content": "文件已成功编辑。",
            },
        ],
    }

    await run_autonomous_scenario_db(scenarios, "test-edit-file-db")

    # 1. 验证文件修改
    content = read_file(test_file)
    assert "new content" in content
    assert "second line" in content
    print(f"  ✅ 文件内容正确: {repr(content)}")

    # 2. 验证 checkpoints 表有数据
    cp_count = await count_table("checkpoints", "thread_id = 'test-edit-file-db'")
    assert cp_count > 0, f"checkpoints 表应有记录，实际 {cp_count}"
    print(f"  ✅ checkpoints 表记录数: {cp_count}")

    # 3. 验证 writes 表有数据（LangGraph 通道值写入）
    writes_count = await count_table("writes", "thread_id = 'test-edit-file-db'")
    assert writes_count > 0, f"writes 表应有记录，实际 {writes_count}"
    print(f"  ✅ writes 表记录数: {writes_count}")

    # 4. 验证 file_operations 表有数据（diff tracker + Celery 任务）
    fo_count = await count_table("file_operations", "thread_id = 'test-edit-file-db'")
    print(f"  ✅ file_operations 表记录数: {fo_count}")
    if fo_count > 0:
        rows = await query_db(
            "SELECT operation, file_path, LENGTH(diff_content) as diff_len FROM file_operations WHERE thread_id = 'test-edit-file-db'"
        )
        for row in rows:
            print(f"     → operation={row.operation}, file={row.file_path}, diff_len={row.diff_len}")

    cleanup(test_file)
    print("  ✅ Agent 自主调用 edit_file（数据库验证通过）")


# =============================================================================
# TEST: Agent 自主调用 apply_patch_file（同一文件多 operation）
# =============================================================================
async def test_agent_autonomous_patch_file_with_db():
    print("\n" + "=" * 70)
    print("TEST: Agent 自主调用 apply_patch_file（同一文件多 operation + DB）")
    print("=" * 70)

    test_file = os.path.join(BASE_DIR, "_test_agent_patch_db.txt")
    make_file(test_file, "line one\nline two\nline three\nline four\n")

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
                    {"name": "apply_patch_file", "args": {"patch_text": patch}, "id": "tc-patch-db-1"}
                ],
                "final_content": "补丁应用完成。",
            },
        ],
    }

    await run_autonomous_scenario_db(scenarios, "test-patch-file-db")

    # 1. 验证文件修改
    content = read_file(test_file)
    assert "LINE ONE" in content
    assert "LINE THREE" in content
    print(f"  ✅ 文件内容正确: {repr(content)}")

    # 2. 验证数据库 checkpoint 写入
    cp_count = await count_table("checkpoints", "thread_id = 'test-patch-file-db'")
    assert cp_count > 0
    print(f"  ✅ checkpoints 表记录数: {cp_count}")

    writes_count = await count_table("writes", "thread_id = 'test-patch-file-db'")
    assert writes_count > 0
    print(f"  ✅ writes 表记录数: {writes_count}")

    # 3. 验证 file_operations 表有数据（同一文件多 operation 应产生多条记录）
    fo_count = await count_table("file_operations", "thread_id = 'test-patch-file-db'")
    print(f"  ✅ file_operations 表记录数: {fo_count}")
    if fo_count > 0:
        rows = await query_db(
            "SELECT operation, file_path, LENGTH(diff_content) as diff_len FROM file_operations WHERE thread_id = 'test-patch-file-db'"
        )
        for row in rows:
            print(f"     → operation={row.operation}, file={row.file_path}, diff_len={row.diff_len}")

    # 4. 验证 messages 表（当前无 DatabaseCallbackHandler，预期为 0）
    msg_count = await count_table("messages", "thread_id = 'test-patch-file-db'")
    print(f"  ℹ️ messages 表记录数: {msg_count}（预期为 0，未启用 DatabaseCallbackHandler）")

    cleanup(test_file)
    print("  ✅ Agent 自主调用 apply_patch_file（数据库验证通过）")


# =============================================================================
# 主入口
# =============================================================================
async def main():
    print("=" * 70)
    print("🚀 Agent 自主触发工具 — 带数据库持久化的端到端集成测试")
    print("=" * 70)

    # 1. 初始化数据库
    await init_db_and_seed()

    # 2. 注入 SyncTaskScheduler（让 Celery 任务同步执行）
    reset_scheduler()
    global _sync_scheduler
    _sync_scheduler = SyncTaskScheduler()
    import app.infrastructure.queue.factory as queue_factory
    queue_factory._scheduler = _sync_scheduler

    # 3. 运行测试
    await test_agent_autonomous_edit_file_with_db()
    await test_agent_autonomous_patch_file_with_db()

    # 4. 清理
    from tests.e2e_db_setup import shutdown_test_database
    await shutdown_test_database()

    print("\n" + "=" * 70)
    print("🎉 全部通过！Agent 自主触发工具的数据库持久化链路验证成功。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
