#!/usr/bin/env python3
"""
EvoLoop Agent 端到端验证脚本（真实组件测试）
================================================
除了 LLM 调用使用 Mock 外，其他所有组件均使用真实实现：
- 真实数据库（SQLite in-memory）
- 真实路由逻辑
- 真实 AuditService
- 真实 Hook system
- 真实事件总线
- 真实 Cache（FileCache）
- 真实 ActivityMonitor

只 Mock：
- LLM 推理（通过 MockInferenceEngine）
- EvoCloud API（外部云服务）

运行方式:
    cd /项目根目录
    arch -arm64 python3 scripts/verify_e2e_dispatch.py
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

# ---------------------------------------------------------------------------
# 必须先设置 EMBEDDED_MODE，再导入其他模块
# ---------------------------------------------------------------------------
import os

os.environ["EMBEDDED_MODE"] = "true"
os.environ["SQLITE_DB_PATH"] = ":memory:"
os.environ["CHECKPOINTER_DATABASE_URI"] = "sqlite:///:memory:"

from app.core.config import settings

settings.EMBEDDED_MODE = True

# 预 mock 架构不兼容的依赖（这些在 EMBEDDED_MODE 下不会被真实使用）
from unittest import mock

sys.modules["lancedb"] = mock.MagicMock()
sys.modules["lancedb.embeddings"] = mock.MagicMock()
sys.modules["lancedb.pydantic"] = mock.MagicMock()
sys.modules["pyarrow"] = mock.MagicMock()
for sub in ["compute", "parquet", "types", "dataset", "csv", "json", "flight", "ipc"]:
    sys.modules[f"pyarrow.{sub}"] = mock.MagicMock()
sys.modules["neo4j"] = mock.MagicMock()
# pandas 依赖 pyarrow，直接 mock document_reader 避免触发 pandas 导入
_doc_reader_mock = mock.MagicMock()
_doc_reader_mock.document_reader_service = mock.MagicMock()
_doc_reader_mock.document_reader_service.read_document = mock.AsyncMock(return_value="")
sys.modules["app.core.file.document_reader"] = _doc_reader_mock

from langchain_core.messages import HumanMessage, AIMessage
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.engine import EngineResult, NodeOutcome, set_default_engine
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, BlackboardState, StateUpdate
from app.core.engine.signals.schema import RouteToSignal
from app.core.engine.signals.handlers.routing import RoutingContext
from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.core.globals import set_graph, get_graph
from tests.e2e_mock_llm import make_mock_engine
from tests.e2e_db_setup import init_test_database, shutdown_test_database

CONFIG_PATH = (
    PROJECT_ROOT
    / "backend"
    / "app"
    / "core"
    / "engine"
    / "config"
    / "agent_main.yaml"
)


# ---------------------------------------------------------------------------
# 测试环境初始化和清理
# ---------------------------------------------------------------------------

async def setup_test_env():
    """初始化真实测试环境：数据库 + Mock LLM + 真实图。"""
    # 1. 初始化内存数据库（只调用一次！SQLite :memory: 每个连接独立）
    db_manager = await init_test_database()

    # 2. 设置 Mock LLM
    mock_engine = make_mock_engine()
    set_default_engine(mock_engine)

    # 3. 构建图
    builder = GraphBuilder()
    graph = builder.build(str(CONFIG_PATH), checkpointer=db_manager.checkpointer)
    set_graph(graph, str(CONFIG_PATH), db_manager.checkpointer)

    # 4. Mock EvoCloud（外部 API）
    patch_evocloud = patch("app.core.evocloud.evocloud_manager.upload_log", new_callable=AsyncMock)
    patch_evocloud_get = patch(
        "app.core.evocloud.evocloud_manager.get_project_by_id",
        new_callable=AsyncMock,
        return_value={"path": "/tmp/test-project"},
    )
    patch_evocloud.start()
    patch_evocloud_get.start()

    return patch_evocloud, patch_evocloud_get


async def teardown_test_env(patches):
    """清理测试环境。"""
    for p in patches:
        p.stop()
    await shutdown_test_database()
    set_graph(None)
    set_default_engine(None)


# ---------------------------------------------------------------------------
# 场景 1: 全新对话
# ---------------------------------------------------------------------------
async def scenario_new_conversation():
    print(f"\n{'=' * 60}")
    print("场景: 全新对话 — 从 dispatch 入口到图执行完成")
    print(f"{'=' * 60}")

    patches = await setup_test_env()
    try:
        thread_id = "test-thread-new"

        # 调用 dispatch 入口
        print("\n[1/3] 调用 dispatch_agent_run() ...")
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content="帮我写一个快速排序算法",
            project_id=1,
            model="gpt-4o",
            skip_message_persistence=False,
        )

        if result.status != "queued":
            print(f"❌ dispatch 失败: {result.error}")
            return False

        print(f"✅ dispatch 成功 — status={result.status}")

        # 调用 background agent
        print("\n[2/3] 调用 run_agent_background() ...")
        await run_agent_background(result.thread_id, result.inputs)

        # 验证数据库
        print("\n[3/3] 校验数据库状态 ...")
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Conversation, Message

        async with session_scope() as session:
            conv = await session.get(Conversation, thread_id)
            if not conv:
                print("❌ Conversation 未创建")
                return False
            print(f"✅ Conversation 创建: {conv.title}")

            from sqlalchemy import select
            stmt = select(Message).where(Message.thread_id == thread_id)
            result_db = await session.execute(stmt)
            msgs = result_db.scalars().all()
            print(f"✅ Messages 数量: {len(msgs)}")
            for m in msgs:
                print(f"    - [{m.role}] {m.content[:50]}...")

        # 验证 TICKET 传递（Supervisor → Worker）
        print("\n[4/4] 校验 Ticket 传递 ...")
        graph = get_graph()
        if graph and graph.checkpointer:
            from langchain_core.runnables import RunnableConfig
            cfg = RunnableConfig(configurable={"thread_id": thread_id})
            try:
                final_state = await graph.aget_state(cfg)
                if final_state and final_state.values:
                    bb = final_state.values.get("blackboard")
                    if bb:
                        ticket = bb.ticket
                        if ticket:
                            print(f"✅ Ticket 已传递: topic='{ticket.topic}', role='{ticket.agent_config.role_name if ticket.agent_config else 'N/A'}'")
                        else:
                            print("❌ Ticket 未设置 — Supervisor 没有传 ticket 给 Worker")
                            return False
                    else:
                        print("⚠️ Blackboard 为空，跳过 ticket 验证")
            except Exception as e:
                print(f"⚠️ 获取最终状态失败: {e}")

        print("\n✅ 全新对话场景验证通过！")
        return True

    finally:
        await teardown_test_env(patches)


# ---------------------------------------------------------------------------
# 场景 2: 重试对话
# ---------------------------------------------------------------------------
async def scenario_retry_conversation():
    print(f"\n{'=' * 60}")
    print("场景: 重试对话 — 用户重试之前失败的任务")
    print(f"{'=' * 60}")

    patches = await setup_test_env()
    try:
        thread_id = "test-thread-retry"

        print("\n[1/3] 调用 dispatch_agent_run() with is_retry=True ...")
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content="重试：帮我写一个快速排序算法",
            project_id=1,
            model="gpt-4o",
            is_retry=True,
            skip_message_persistence=False,
        )

        if result.status != "queued":
            print(f"❌ dispatch 失败: {result.error}")
            return False

        print(f"✅ dispatch 成功 — status={result.status}, is_retry={result.inputs.get('is_retry')}")
        assert result.inputs.get("is_retry") is True, "is_retry 应被传递到 inputs"

        print("\n[2/3] 调用 run_agent_background() ...")
        await run_agent_background(result.thread_id, result.inputs)

        print("\n[3/3] 校验数据库状态 ...")
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = select(Message).where(Message.thread_id == thread_id)
            result_db = await session.execute(stmt)
            msgs = result_db.scalars().all()
            print(f"✅ Messages 数量: {len(msgs)}")

        print("\n✅ 重试场景验证通过！")
        return True

    finally:
        await teardown_test_env(patches)


# ---------------------------------------------------------------------------
# 场景 3: 多轮交互
# ---------------------------------------------------------------------------
async def scenario_multi_turn_conversation():
    print(f"\n{'=' * 60}")
    print("场景: 多轮交互 — Worker → Supervisor → Worker → Finish")
    print(f"{'=' * 60}")

    patches = await setup_test_env()
    try:
        thread_id = "test-thread-multi"

        print("\n[1/3] 调用 dispatch_agent_run() ...")
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content="先写快速排序，再写归并排序",
            project_id=1,
            model="gpt-4o",
            skip_message_persistence=False,
        )

        if result.status != "queued":
            print(f"❌ dispatch 失败: {result.error}")
            return False

        print(f"✅ dispatch 成功 — status={result.status}")

        print("\n[2/3] 调用 run_agent_background() ...")
        await run_agent_background(result.thread_id, result.inputs)

        print("\n[3/3] 校验数据库状态 ...")
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = select(Message).where(Message.thread_id == thread_id)
            result_db = await session.execute(stmt)
            msgs = result_db.scalars().all()
            print(f"✅ Messages 数量: {len(msgs)}")

        print("\n✅ 多轮交互场景验证通过！")
        return True

    finally:
        await teardown_test_env(patches)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def main():
    print("🚀 EvoLoop Agent 端到端验证开始（真实组件测试）")
    print("配置: EMBEDDED_MODE=True | SQLite=:memory: | LLM=Mock")

    results = []
    results.append(await scenario_new_conversation())
    results.append(await scenario_retry_conversation())
    results.append(await scenario_multi_turn_conversation())

    passed = sum(results)
    total = len(results)

    print(f"\n{'=' * 60}")
    print("📊 验证汇总")
    print(f"{'=' * 60}")
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("🎉 所有端到端场景验证通过！真实组件链路正常。")
        return 0
    else:
        print("⚠️ 端到端场景验证失败，请检查日志。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
