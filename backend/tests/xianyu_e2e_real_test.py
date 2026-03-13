"""
EvoLoop 闲鱼采集 E2E 完整实战演练脚本 v2
==========================================
按照 main.py lifespan 顺序复刻所有关键初始化步骤：

  [1] 数据库初始化 (schema ensure)
  [2] 记忆系统初始化
  [3] 环境唤醒 (awaken) — 关键：通过 ADB 扫描已连接 Android 设备
  [4] 初始化 handlers (register_default_handlers)
  [5] Graph 构建 (MemorySaver 代替 Postgres checkpointer)
  [6] Device Watcher 启动 (实时监听设备变化)
  [7] 发送用户指令并通过 run_agent_background 触发真实 Agent 循环
  [8] 实时轮询 Redis 并打印 Agent 执行步骤

Android 手机已连接，awaken() 会探测到它，Supervisor 将根据
ADB 设备列表正确推断 ecosystem = android，进而路由到 mobile_sop。
"""

import asyncio
import json
import logging
import os
import sys
import uuid

# ── 路径注入 ──────────────────────────────────────────────────────────────────
project_root = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend"
sys.path.insert(0, project_root)

# ── 日志配置 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s | %(levelname)s | %(message)s"
)
# 显示关键模块的 INFO 级日志
for module in [
    "app.core.environment",
    "app.core.engine.nodes.supervisor",
    "app.core.engine",
    "app.core.monitoring.activity",
]:
    logging.getLogger(module).setLevel(logging.INFO)


# ── 初始化步骤 ────────────────────────────────────────────────────────────────

async def step1_db_schema():
    """复刻 main.py Step 1: 确保数据库 schema 存在（非破坏性）。"""
    print("🗄️  [Step 1] 初始化数据库 schema...")
    try:
        from app.infrastructure.database.sql.database import Base, engine
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        print("     ✅ DB schema ready")
    except Exception as e:
        print(f"     ⚠️  DB schema init failed (non-critical): {e}")


async def step2_memory():
    """复刻 main.py Step 2: 初始化记忆系统。"""
    print("🧠 [Step 2] 初始化记忆系统...")
    try:
        from app.core.memory import memory_manager
        await memory_manager.initialize()
        print("     ✅ Memory initialized")
    except Exception as e:
        print(f"     ⚠️  Memory init failed (non-critical): {e}")


async def step3_awaken():
    """
    复刻 main.py Step 2.5: Agent 环境唤醒。

    这是让 Supervisor 正确感知 Android 设备的关键步骤。
    awaken() 内部并行调用：
      - EnvironmentProbe.probe_android_devices()  ← 通过 ADB 扫描实体设备
      - EnvironmentProbe.probe_macos()
      - replay_memory()
    结果存入全局 _awakened_state，Supervisor 通过 get_environment_telemetry 工具读取并决策。
    """
    print("🌅 [Step 3] 执行 Agent 环境唤醒 (含 ADB 设备探测)...")
    try:
        from app.core.environment import awaken
        from app.core.environment.handlers import register_default_handlers
        from app.core.events.bridge import register_event_bridge
        from app.core.learning.orchestrator import register_learning_handlers

        register_default_handlers()
        register_event_bridge()
        register_learning_handlers()

        state = await awaken()
        android_count = len(state.android_devices)
        platforms = state.available_platforms
        print(f"     ✅ Awakened. Platforms: {platforms} | Android Devices: {android_count}")
        if android_count == 0:
            print("     ⚠️  未检测到 Android 设备！请确认手机已通过 USB 连接并开启 ADB 调试。")
            print("         可以用 `adb devices` 命令验证。")
        else:
            for d in state.android_devices:
                print(f"        📱 发现设备: {d.serial} | 已安装 App: {len(d.installed_packages)} 个")
        return state
    except Exception as e:
        print(f"     ❌ Awaken failed: {e}")
        return None


async def step4_graph():
    """复刻 main.py Step 3: 构建 LangGraph（测试环境使用 MemorySaver）。"""
    print("🔧 [Step 4] 构建 LangGraph 引擎...")
    from langgraph.checkpoint.memory import MemorySaver
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph

    builder = GraphBuilder()
    config_path = os.path.join(project_root, "app/core/engine/config/agent_main.yaml")
    checkpointer = MemorySaver()
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    print("     ✅ LangGraph 引擎构建完成")


def step5_device_watcher():
    """复刻 main.py Step 8: 启动 Device Watcher（监听设备热插拔）。"""
    print("📡 [Step 5] 启动 Device Watcher...")
    try:
        from app.core.environment.controllers.device_watcher import device_watcher
        device_watcher.start()
        print("     ✅ Device Watcher 已启动（后台监听）")
    except Exception as e:
        print(f"     ⚠️  Device Watcher 启动失败 (non-critical): {e}")


async def poll_status(thread_id: str, max_polls: int = 1000, interval: float = 3.0):
    """实时轮询 Redis 中 Agent 的执行状态。"""
    from app.infrastructure.database.redis import redis_client
    key = f"activity:{thread_id}"
    prev_steps = 0
    for i in range(max_polls):
        await asyncio.sleep(interval)
        try:
            status = await redis_client.hget(key, "status")
            steps_json = await redis_client.hget(key, "steps")
            steps = json.loads(steps_json) if steps_json else []

            for s in steps[prev_steps:]:
                icon = "🔹" if s.get("status") == "running" else "  ✔️"
                details = (s.get("details") or "")[:100]
                print(f"   {icon} [{s.get('name', '?')}] → {s.get('status')} | {details}")
            prev_steps = len(steps)

            print(f"\n📡 [{i+1}/{max_polls}] Status={status} | Steps={len(steps)}")

            if status in ("done", "failed", "cancelled"):
                print(f"\n🏁 Agent 结束，最终状态: {status}")
                return
        except Exception as e:
            print(f"   ⚠️ 轮询异常: {e}")

    print("\n⏱ 轮询超时，Agent 仍在运行中")


async def run_e2e():
    """完整 E2E 主流程。"""
    print("\n" + "=" * 65)
    print("  🚀 EvoLoop 闲鱼 E2E 实战演练 v2（完整环境感知）")
    print("=" * 65 + "\n")

    # ── 启动链 ──
    await step1_db_schema()
    await step2_memory()
    awakened = await step3_awaken()
    await step4_graph()
    step5_device_watcher()

    # ── 构造用户指令（与 chat_endpoint 保持一致）──
    thread_id = f"xianyu-e2e-{uuid.uuid4().hex[:8]}"
    user_message = "采集闲鱼最新上架的 iPhone 15 商品详细数据，包括图片信息"

    print(f"\n{'='*65}")
    print(f"📌 Thread ID : {thread_id}")
    print(f"💬 用户指令 : {user_message}")
    print(f"{'='*65}\n")

    # 显示 ecosystem 感知结果（说明 Supervisor 将如何路由）
    if awakened:
        # LLM-First: Supervisor 通过 get_environment_telemetry 工具自主感知环境
        android_devices = [d for d in awakened.android_devices if d.is_reachable]
        if android_devices:
            print(f"   ✅ Android 设备已连接: {[d.model for d in android_devices]}")
            print("   Supervisor 将通过 get_environment_telemetry 感知并路由\n")
        else:
            print("   ⚠️ 未检测到 Android 设备，Supervisor 将通过其他方式处理\n")

    # ── 启动 ActivityMonitor ──
    from app.core.monitoring.activity import activity_monitor
    await activity_monitor.start_run(thread_id, user_message)

    # ── 构造 LangGraph inputs ──
    inputs = {
        "messages": [{"type": "human", "content": user_message}],
        "project_id": 1,
    }

    # ── 并行运行 Agent + 状态轮询 ──
    print("--- 调用 run_agent_background，Agent 开始推理... ---\n")
    from app.core.engine.background_agent import run_agent_background
    agent_task = asyncio.create_task(run_agent_background(thread_id, inputs))
    poll_task  = asyncio.create_task(poll_status(thread_id, max_polls=10000, interval=3.0))

    done, pending = await asyncio.wait(
        [agent_task, poll_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()
    for t in done:
        exc = t.exception()
        if exc:
            print(f"\n❌ 异常: {exc}")

    print("\n" + "=" * 65)
    print("  📊 事后验证（TraceRecorder + 数据导出）")
    print("=" * 65)

    # ── 验证 1：TraceRecorder 是否录制了操作 ──────────────────────────────
    try:
        from app.infrastructure.database.sql.database import session_scope
        from app.models.learning import TraceEvent
        from sqlalchemy import select, func

        async with session_scope() as session:
            stmt = select(func.count()).where(TraceEvent.thread_id == thread_id)
            result = await session.execute(stmt)
            event_count = result.scalar()

        if event_count and event_count > 0:
            print(f"\n✅ [TraceRecorder] 录制了 {event_count} 条 TraceEvent")
            # 查看事件类型分布
            async with session_scope() as session:
                type_stmt = (
                    select(TraceEvent.action_type, func.count())
                    .where(TraceEvent.thread_id == thread_id)
                    .group_by(TraceEvent.action_type)
                )
                rows = (await session.execute(type_stmt)).all()
            for action_type, cnt in rows:
                print(f"   - {action_type}: {cnt} 条")
        else:
            print(f"\n⚠️  [TraceRecorder] 未找到 TraceEvent（thread_id={thread_id}）")
            print("   可能原因：Agent 在轮询超时前尚未到达录制节点，或 TraceCallbackHandler 未激活")
    except Exception as e:
        print(f"\n❌ [TraceRecorder] 查询失败: {e}")

    # ── 验证 2：是否导出了数据文件 ────────────────────────────────────────
    import glob, os, time
    print("\n🗂  [数据导出] 扫描近期写入的数据文件...")

    # 常见输出路径
    search_dirs = [
        os.path.expanduser("~/.evoloop/output"),
        os.path.expanduser("~/.evoloop/data"),
        "/tmp",
        os.path.join(project_root, "output"),
        os.path.join(project_root, "data"),
    ]
    data_extensions = ["*.json", "*.csv", "*.txt"]
    found_files = []

    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for ext in data_extensions:
            for f in glob.glob(os.path.join(d, "**", ext), recursive=True):
                # 只看最近 10 分钟的文件
                if os.path.getmtime(f) > (time.time() - 600):
                    found_files.append(f)

    if found_files:
        print(f"✅ 发现 {len(found_files)} 个近期数据文件：")
        for f in found_files[:5]:
            size = os.path.getsize(f)
            print(f"   📄 {f}  ({size} bytes)")
    else:
        print("⚠️  未发现近期导出的数据文件")
        print("   Agent 可能将数据内联在最终报告中（而非写文件）")

    # ── 验证 3：验证自动化学习闭环（是否自动生成了技能） ──────────────────
    print("\n🧠 [自动化学习] 验证技能是否自动生成（轮询 DB）...")
    try:
        from app.models.learning import LearnedSkill
        from sqlalchemy import select
        
        found_skill = None
        for attempt in range(20): # 等待最多 60s
            await asyncio.sleep(3)
            async with session_scope() as session:
                # 查找最近 1 分钟创建的、且包含 thread_id 信息的技能（由于合成器目前可能没回填 thread_id，我们按时间排序找最新的）
                stmt = select(LearnedSkill).order_by(LearnedSkill.created_at.desc()).limit(1)
                res = await session.execute(stmt)
                latest_skill = res.scalar()
                
                if latest_skill:
                    # 检查是否是最近产生的技能
                    from datetime import datetime, timezone
                    now = datetime.now()
                    diff = (now - latest_skill.created_at.replace(tzinfo=None)).total_seconds()
                    if diff < 120: # 2 分钟内
                        found_skill = latest_skill
                        break
            print(f"   ⏳ 正在等待后台合成... (尝试 {attempt+1}/20)")

        if found_skill:
            print(f"✅ [Learning] 成功检测到自动化生成的技能！")
            print(f"   - 技能名称: {found_skill.name}")
            print(f"   - 命名空间: {found_skill.namespace}")
            print(f"   - 生成时间: {found_skill.created_at}")
            if found_skill.macro_script:
                print(f"   - 宏脚本长度: {len(found_skill.macro_script)} 字符")
        else:
            print(f"❌ [Learning] 未能在预期时间内检测到新技能生成。")
            print("   请检查 Celery 日志或 record_episode_task 的执行状态。")
            
    except Exception as e:
        print(f"❌ [Learning] 技能验证过程出错: {e}")

    print("\n" + "=" * 65)
    print("  ✅ 完整 E2E 实战演练结束")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(run_e2e())
