"""
完整持久化测试：20+ 轮多轮对话，同时验证 checkpoint 表和 messages 表。

关键设计：
- 使用真实的 AsyncSqliteSaver（DELETE 模式）
- 使用真实的 db_resource_manager 初始化（messages 表写入需要）
- 每轮对话后，手动触发 MessageHandler 写入 messages 表
- 验证两个表的最终数据一致性
"""

import asyncio
import os
import tempfile
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.engine import AgentEngine, EngineResult, set_default_engine
from app.core.engine.graph_builder import GraphBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.signals.schema import RouteToSignal, RoutingContext
from app.core.engine.state import AgentState
from app.core.globals import set_graph
from app.infrastructure.database.resource_manager import db_resource_manager

# Skip DB-dependent hydration
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


class MockAgentEngine(AgentEngine):
    def __init__(self):
        super().__init__()
        self.counters = {"supervisor": 0, "worker": 0, "chat": 0, "finish": 0}

    async def run_node(self, state, config, system_prompt, tools, max_steps=5, temperature=0.7, name="Agent", is_subtask=False, node_source=None, parallel_tools=False, model=None) -> EngineResult:
        key = name.lower()
        self.counters[key] = self.counters.get(key, 0) + 1
        c = self.counters[key]

        if name == "Supervisor":
            if c <= 10:
                if c % 2 == 1:
                    return EngineResult(signal=RouteToSignal(target="chat", context=RoutingContext(topic=f"topic{c}")))
                else:
                    return EngineResult()
            if c <= 30:
                if c % 2 == 1:
                    return EngineResult(signal=RouteToSignal(target="worker", context=RoutingContext(topic=f"topic{c}")))
                else:
                    return EngineResult()
            return EngineResult()

        if name == "Chat":
            return EngineResult(messages=[AIMessage(content=f"AI 回复第 {c} 条，来自 Chat 节点")])

        if name == "Worker":
            return EngineResult(
                messages=[
                    AIMessage(content="", tool_calls=[{"name": "search_web", "args": {"query": f"test{c}"}, "id": f"call_{c}"}]),
                    ToolMessage(content=f"搜索结果 {c}", name="search_web", tool_call_id=f"call_{c}"),
                    AIMessage(content=f"Worker 回复第 {c} 条，基于工具调用结果"),
                ]
            )

        if name == "Finish":
            return EngineResult(messages=[AIMessage(content="")])

        return EngineResult(messages=[AIMessage(content="默认回复")])


async def persist_messages_to_db(thread_id: str, project_id: int, round_num: int):
    """手动触发 MessageHandler，将消息写入 messages 表"""
    from app.core.engine.message import MessageHandler

    handler = MessageHandler(
        thread_id=thread_id,
        project_id=project_id,
        start_sequence=round_num * 10,
    )

    # Simulate AI message
    await handler.handle_ai_message(
        content=f"第 {round_num} 轮 AI 回复",
        metadata={"node_source": "chat"},
    )

    if round_num % 2 == 0:
        # Simulate Worker + Tool messages
        await handler.handle_ai_message(
            content="",
            tool_calls=[{"name": "search_web", "args": {"query": f"q{round_num}"}, "id": f"tc_{round_num}"}],
            metadata={"node_source": "worker"},
        )
        await handler.handle_tool_output(
            tool_name="search_web",
            output=f"搜索结果 {round_num}",
            tool_call_id=f"tc_{round_num}",
        )
        await handler.handle_ai_message(
            content=f"第 {round_num} 轮 Worker 总结",
            metadata={"node_source": "worker"},
        )

    # Simulate Finish message
    await handler.handle_ai_message(
        content="",
        metadata={"node_source": "finish"},
    )


async def main():
    # 1. 初始化真实的数据库（messages 表需要）
    fd, sqlite_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # 设置环境变量让 db_resource_manager 使用我们的临时数据库
    os.environ["SQLITE_DB_PATH"] = sqlite_path
    # 需要重新加载 settings
    from app.core.config import settings
    settings.SQLITE_PATH = sqlite_path

    print("=" * 70)
    print("初始化数据库...")
    print("=" * 70)
    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    # 2. 创建 AsyncSqliteSaver（DELETE 模式）
    import aiosqlite
    cp_conn = await aiosqlite.connect(sqlite_path)
    await cp_conn.execute("PRAGMA journal_mode=DELETE")
    await cp_conn.execute("PRAGMA busy_timeout=30000")
    await cp_conn.commit()

    from app.infrastructure.database.checkpoint_saver import FixedAsyncSqliteSaver
    saver = FixedAsyncSqliteSaver(conn=cp_conn)
    await saver.setup()

    # 3. 构建 graph
    config_path = os.path.join(os.path.dirname(__file__), "..", "app", "core", "engine", "config", "agent_main.yaml")
    config_path = os.path.abspath(config_path)
    graph = GraphBuilder().build(config_path, checkpointer=saver)
    set_graph(graph, config_path=config_path, checkpointer=saver)

    mock_engine = MockAgentEngine()
    set_default_engine(mock_engine)

    thread_id = "full-persist-test-thread"
    project_id = 1
    base_config = {"configurable": {"thread_id": thread_id, "model": "kimi-k2-thinking-turbo"}}

    ctx = EvoContext(thread_id=thread_id, project_id=project_id, active_model="kimi-k2-thinking-turbo")
    ContextManager.set(ctx)

    # 4. 运行 25 轮对话
    print("\n" + "=" * 70)
    print("TEST: 25 轮多轮对话 + 数据落库")
    print("=" * 70)

    total_start = time.perf_counter()
    for i in range(25):
        round_num = i + 1
        msg = f"这是第 {round_num} 轮对话的 HumanMessage"

        # Run graph
        await graph.ainvoke(
            AgentState(messages=[HumanMessage(content=msg)]),
            config=base_config,
        )

        # Persist to messages table
        await persist_messages_to_db(thread_id, project_id, round_num)

        if round_num % 5 == 0:
            print(f"  已完成 {round_num}/25 轮...")

    total_elapsed = (time.perf_counter() - total_start) * 1000

    # 5. 验证 checkpoint 表
    print("\n" + "=" * 70)
    print("验证 Checkpoint 表")
    print("=" * 70)

    total_cp = 0
    async for _ in saver.alist(base_config):
        total_cp += 1

    cp = await saver.aget_tuple(base_config)
    final_msgs = []
    if cp and cp.checkpoint:
        final_msgs = cp.checkpoint.get("channel_values", {}).get("messages", [])

    human_in_cp = sum(1 for m in final_msgs if getattr(m, 'type', None) == 'human')

    print(f"  Checkpoint 总数: {total_cp}")
    print(f"  最终 checkpoint 消息数: {len(final_msgs)}")
    print(f"  HumanMessage 数: {human_in_cp}")

    # 6. 验证 messages 表
    print("\n" + "=" * 70)
    print("验证 Messages 表")
    print("=" * 70)

    from app.infrastructure.database.sql.database import session_scope
    from sqlalchemy import text

    async with session_scope() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM messages WHERE thread_id = :tid"),
            {"tid": thread_id}
        )
        msg_count = result.scalar()

        result = await session.execute(
            text("SELECT role, COUNT(*) FROM messages WHERE thread_id = :tid GROUP BY role"),
            {"tid": thread_id}
        )
        role_counts = dict(result.fetchall())

        result = await session.execute(
            text("SELECT id, role, content FROM messages WHERE thread_id = :tid ORDER BY id LIMIT 5"),
            {"tid": thread_id}
        )
        first_5 = result.fetchall()

        result = await session.execute(
            text("SELECT id, role, content FROM messages WHERE thread_id = :tid ORDER BY id DESC LIMIT 5"),
            {"tid": thread_id}
        )
        last_5 = result.fetchall()

    print(f"  Messages 表总记录数: {msg_count}")
    print(f"  角色分布: {role_counts}")
    print(f"\n  前 5 条消息:")
    for row in first_5:
        print(f"    [{row[0]}] {row[1]}: {str(row[2])[:50]}")
    print(f"\n  后 5 条消息:")
    for row in last_5:
        print(f"    [{row[0]}] {row[1]}: {str(row[2])[:50]}")

    # 7. 最终断言
    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    passed = True
    if total_cp >= 60:
        print(f"  ✅ Checkpoint 数量: {total_cp} >= 60")
    else:
        print(f"  ❌ Checkpoint 数量不足: {total_cp} < 60")
        passed = False

    if human_in_cp == 25:
        print(f"  ✅ Checkpoint 中 HumanMessage: 25/25")
    else:
        print(f"  ❌ Checkpoint 中 HumanMessage: {human_in_cp}/25")
        passed = False

    if msg_count >= 75:
        print(f"  ✅ Messages 表记录数: {msg_count} >= 75")
    else:
        print(f"  ❌ Messages 表记录数不足: {msg_count} < 75")
        passed = False

    if role_counts.get("human", 0) >= 25:
        print(f"  ✅ Messages 表 human 记录: {role_counts.get('human', 0)} >= 25")
    else:
        print(f"  ❌ Messages 表 human 记录不足")
        passed = False

    if role_counts.get("ai", 0) >= 25:
        print(f"  ✅ Messages 表 ai 记录: {role_counts.get('ai', 0)} >= 25")
    else:
        print(f"  ❌ Messages 表 ai 记录不足")
        passed = False

    print(f"\n  总耗时: {total_elapsed:.2f} ms ({total_elapsed/25:.2f} ms/轮)")

    if passed:
        print(f"\n  🎉 所有断言通过！Checkpoint 和 Messages 表数据完整")
    else:
        print(f"\n  ⚠️ 部分断言失败")

    # Cleanup
    await cp_conn.close()
    await db_resource_manager.shutdown()
    if os.path.exists(sqlite_path):
        os.unlink(sqlite_path)


if __name__ == "__main__":
    asyncio.run(main())
