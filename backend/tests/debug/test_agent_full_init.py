#!/usr/bin/env python3
"""
完整初始化的 Agent 直接测试 - 带5小时超时和智能循环检测
检测到异常循环时自动中断执行
"""

import asyncio
import os
import sys
from datetime import datetime
from collections import Counter, deque
from typing import Optional
import signal

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

# 常量配置
MAX_EXECUTION_TIME = 5 * 60 * 60  # 5小时
FORCE_STOP_TIMEOUT = 10  # 强制停止等待秒数

print("="*70)
print("🚀 Agent 直接测试 - 智能循环检测版 (5小时超时)")
print("="*70)


class LoopDetector:
    """Agent 循环检测器 - 检测节点/工具调用异常"""
    
    # 检测配置
    CYCLE_WINDOW_SIZE = 8  # 检查最近N个调用
    CYCLE_REPEAT_THRESHOLD = 4  # 相同模式重复4次视为异常
    MAX_SAME_NODE_SEQUENCE = 6  # 同一节点连续调用6次视为异常
    MAX_TOTAL_STEPS = 100  # 总步骤超过100视为可疑
    STALL_THRESHOLD_SECONDS = 120  # 120秒无进展视为卡住
    
    def __init__(self, thread_id: str, cancel_event: asyncio.Event):
        self.thread_id = thread_id
        self.cancel_event = cancel_event
        self.node_history = deque(maxlen=100)
        self.step_history = deque(maxlen=100)  # (step_id, name, status, time)
        self.check_count = 0
        self.last_error = None
        self.is_abnormal = False
        self.last_step_count = 0
        self.no_change_start_time = None
        
    def add_step(self, step: dict):
        """记录步骤"""
        self.step_history.append({
            "id": step.get("id"),
            "name": step.get("name", "N/A"),
            "status": step.get("status", "unknown"),
            "type": step.get("type", "node"),
            "time": step.get("time", "0s")
        })
        self.node_history.append(step.get("name", "N/A"))
        
    async def check_loop(self) -> Optional[str]:
        """检查是否存在循环，返回错误原因或None"""
        self.check_count += 1
        
        if len(self.node_history) < 3:
            return None
            
        nodes = list(self.node_history)
        
        # 1. 检查连续相同节点调用
        for n in range(self.MAX_SAME_NODE_SEQUENCE, 2, -1):
            if len(nodes) >= n:
                last_n = nodes[-n:]
                if len(set(last_n)) == 1:
                    node_name = last_n[0]
                    return f"🔴 循环警报: 节点 '{node_name}' 连续执行 {n} 次"
        
        # 2. 检查重复模式 (如 supervisor -> worker -> supervisor -> worker)
        if len(nodes) >= self.CYCLE_WINDOW_SIZE:
            window = nodes[-self.CYCLE_WINDOW_SIZE:]
            
            for period in range(2, min(5, len(window)//2 + 1)):
                pattern = window[-period:]
                repeats = 0
                for i in range(len(window) - period, -1, -period):
                    if window[i:i+period] == pattern:
                        repeats += 1
                    else:
                        break
                
                if repeats >= self.CYCLE_REPEAT_THRESHOLD:
                    return f"🔴 循环警报: 检测到周期为{period}的重复模式 {pattern} (重复{repeats}次)"
        
        # 3. 检查步骤数过多
        if len(self.node_history) > self.MAX_TOTAL_STEPS:
            node_counts = Counter(nodes)
            top_nodes = node_counts.most_common(3)
            return f"🔴 循环警报: 总步骤过多 ({len(nodes)}步), 最频繁节点: {top_nodes}"
        
        # 4. 检查是否卡住（步骤数不变但时间流逝）
        if self.no_change_start_time:
            stall_duration = (datetime.now() - self.no_change_start_time).total_seconds()
            if stall_duration > self.STALL_THRESHOLD_SECONDS:
                return f"🔴 卡住警报: Agent 已 {stall_duration:.0f} 秒无进展"
        
        return None
    
    def update_progress(self, current_step_count: int):
        """更新进度检查"""
        if current_step_count == self.last_step_count:
            if self.no_change_start_time is None:
                self.no_change_start_time = datetime.now()
        else:
            self.no_change_start_time = None
            self.last_step_count = current_step_count
    
    def get_report(self) -> str:
        """生成诊断报告"""
        if not self.node_history:
            return "无执行记录"
        
        nodes = list(self.node_history)
        recent = nodes[-15:]
        node_counts = Counter(nodes)
        
        report = f"""
📊 执行诊断报告 (Thread: {self.thread_id})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总步骤数: {len(nodes)}
检测次数: {self.check_count}
状态: {'🔴 异常' if self.is_abnormal else '🟢 正常'}

最近15个节点:
  {' -> '.join(recent)}

节点频率统计 (Top 5):
"""
        for node, count in node_counts.most_common(5):
            pct = count / len(nodes) * 100
            bar = '█' * int(pct / 5)
            report += f"  • {node:20s}: {count:3d}次 ({pct:5.1f}%) {bar}\n"
        
        # 检测是否有明显的循环
        if len(nodes) >= 4:
            last_4 = nodes[-4:]
            if len(set(last_4)) <= 2:
                report += f"\n⚠️ 警告: 最近4步只涉及 {len(set(last_4))} 个节点，可能处于循环中\n"
            
        return report


async def monitor_and_control(thread_id: str, stop_event: asyncio.Event, 
                               cancel_event: asyncio.Event, detector: LoopDetector):
    """后台监控任务 - 检测循环并可取消执行"""
    from app.core.monitoring.activity import activity_monitor
    
    check_interval = 3  # 每3秒检查一次
    
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=check_interval)
            if cancel_event.is_set():
                break
        except asyncio.TimeoutError:
            pass  # 正常继续检查
        
        if stop_event.is_set() or cancel_event.is_set():
            break
        
        try:
            # 获取活动状态
            activity = await activity_monitor.get_activity(thread_id)
            if not activity:
                continue
            
            steps = activity.get('steps', [])
            
            # 更新步骤记录
            for step in steps[len(detector.step_history):]:
                detector.add_step(step)
            
            detector.update_progress(len(steps))
            
            # 检测循环
            loop_error = await detector.check_loop()
            if loop_error:
                detector.is_abnormal = True
                detector.last_error = loop_error
                print(f"\n{'!'*70}")
                print(f"{loop_error}")
                print(f"{'!'*70}")
                print(detector.get_report())
                print(f"\n🛑 正在尝试中断 Agent 执行...")
                
                # 触发取消
                cancel_event.set()
                
                # 调用停止信号
                try:
                    await activity_monitor.signal_stop(thread_id)
                    print("✅ 已发送停止信号")
                except Exception as e:
                    print(f"⚠️ 发送停止信号失败: {e}")
                
                break
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            pass


async def init_environment():
    """初始化环境"""
    
    from app.core.config import settings
    from app.infrastructure.database.sql.database import Base, engine
    from sqlmodel import SQLModel
    from sqlalchemy import text
    import logging
    
    logging.basicConfig(level=logging.WARNING)
    
    print("\n🔧 步骤 1: 初始化数据库...")
    try:
        if settings.EMBEDDED_MODE:
            from app import models
            # NOTE: project.requirements models removed in migration 1775161017
            
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.run_sync(SQLModel.metadata.create_all)
            print("   ✅ SQLite 表创建完成")
    except Exception as e:
        print(f"   ⚠️  数据库: {e}")
    
    print("\n🔧 步骤 2: 初始化系统配置...")
    try:
        from app.initial_data import init as init_data
        await asyncio.to_thread(init_data)
        print("   ✅ 系统配置初始化完成")
    except Exception as e:
        print(f"   ⚠️  配置: {e}")
    
    print("\n🔧 步骤 3: 初始化 Memory Manager...")
    try:
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        # Store container for cleanup
        global _memory_container
        _memory_container = container
        print("   ✅ Memory Manager 初始化完成")
    except Exception as e:
        print(f"   ⚠️  Memory: {e}")
    
    print("\n🔧 步骤 4: 初始化 Checkpointer...")
    checkpointer = None
    try:
        if settings.EMBEDDED_MODE:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as Checkpointer
            import aiosqlite
            
            db_uri = settings.CHECKPOINTER_DATABASE_URI
            sqlite_path = db_uri.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
            conn = await aiosqlite.connect(sqlite_path)
            checkpointer = Checkpointer(conn=conn)
            await checkpointer.setup()
            print("   ✅ SQLite Checkpointer 初始化完成")
    except Exception as e:
        print(f"   ❌ Checkpointer 失败: {e}")
        return None
    
    print("\n🔧 步骤 5: 构建 Agent Graph...")
    try:
        from app.core.engine.graph_builder import GraphBuilder
        from app.core.globals import set_graph
        from app.core.persistence import set_checkpointer
        
        set_checkpointer(checkpointer)
        builder = GraphBuilder()
        config_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/config/agent_main.yaml"
        
        if os.path.exists(config_path):
            graph = builder.build(config_path, checkpointer=checkpointer)
            set_graph(graph, config_path=config_path, checkpointer=checkpointer)
            print("   ✅ Agent Graph 构建完成")
        else:
            print(f"   ❌ 配置文件不存在")
            return None
    except Exception as e:
        print(f"   ❌ Graph 失败: {e}")
        return None
    
    return True


async def run_single_test(test_id: int, name: str, user_input: str) -> dict:
    """执行单个测试"""
    
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    thread_id = f"agent-test-{datetime.now().strftime('%H%M%S')}-{test_id}"
    
    # 创建取消控制事件
    stop_monitor = asyncio.Event()
    cancel_execution = asyncio.Event()
    detector = LoopDetector(thread_id, cancel_execution)
    
    print(f"\n{'='*70}")
    print(f"📌 [测试 {test_id}: {name}]")
    print(f"   输入: {user_input[:50]}...")
    print(f"{'='*70}")
    print(f"Thread ID: {thread_id}")
    print(f"超时: {MAX_EXECUTION_TIME/3600:.1f}小时 | 自动中断: 开启")
    print("⏳ 启动 Agent...\n")
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    result = {
        "name": name,
        "thread_id": thread_id,
        "status": "pending",
        "duration": 0,
        "error": None,
        "steps_count": 0,
        "loop_detected": False,
        "cancelled": False
    }
    
    # 启动监控任务
    monitor_task = asyncio.create_task(
        monitor_and_control(thread_id, stop_monitor, cancel_execution, detector)
    )
    
    start = datetime.now()
    agent_task = None
    
    try:
        # 启动 Agent 任务
        agent_task = asyncio.create_task(run_agent_background(thread_id, inputs))
        
        # 等待 Agent 完成或取消
        while not agent_task.done():
            # 检查是否被取消
            if cancel_execution.is_set():
                print(f"⚠️ 检测到取消信号，正在终止 Agent...")
                agent_task.cancel()
                result["cancelled"] = True
                try:
                    await asyncio.wait_for(agent_task, timeout=FORCE_STOP_TIMEOUT)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                break
            
            # 等待一小段时间
            try:
                await asyncio.wait_for(agent_task, timeout=1.0)
            except asyncio.TimeoutError:
                continue  # 继续循环检查
        
        # 获取结果
        if not agent_task.cancelled() and agent_task.done():
            try:
                await agent_task  # 获取可能的异常
            except Exception as e:
                raise e
        
        elapsed = (datetime.now() - start).total_seconds()
        result["duration"] = elapsed
        
        # 停止监控
        stop_monitor.set()
        try:
            await asyncio.wait_for(monitor_task, timeout=5)
        except:
            monitor_task.cancel()
        
        # 判断结果
        if detector.is_abnormal:
            result["status"] = "abnormal"
            result["loop_detected"] = True
            result["error"] = detector.last_error
            print(f"\n🔴 测试异常终止 - 检测到循环!")
            print(f"   运行时间: {elapsed:.2f}s")
        elif result["cancelled"]:
            result["status"] = "cancelled"
            print(f"\n🛑 测试被取消")
            print(f"   运行时间: {elapsed:.2f}s")
        else:
            result["status"] = "success"
            print(f"\n✅ 测试完成")
            print(f"   运行时间: {elapsed:.2f}s")
        
        # 获取最终状态
        activity = await activity_monitor.get_activity(thread_id)
        if activity:
            steps = activity.get('steps', [])
            result["steps_count"] = len(steps)
            print(f"   总步骤: {len(steps)}")
        
        print(f"{detector.get_report()}")
        
    except asyncio.TimeoutError:
        elapsed = (datetime.now() - start).total_seconds()
        result["status"] = "timeout"
        result["duration"] = elapsed
        result["error"] = f"Timeout after {MAX_EXECUTION_TIME}s"
        
        stop_monitor.set()
        if agent_task and not agent_task.done():
            agent_task.cancel()
        monitor_task.cancel()
        
        print(f"\n⏱️ 执行超时 ({elapsed/3600:.2f}小时)")
        print(f"{detector.get_report()}")
        
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        result["status"] = "error"
        result["duration"] = elapsed
        result["error"] = str(e)
        
        stop_monitor.set()
        if agent_task and not agent_task.done():
            agent_task.cancel()
        monitor_task.cancel()
        
        print(f"\n❌ 执行错误: {e}")
        print(f"{detector.get_report()}")
    
    return result


async def run_agent_test():
    """运行 Agent 测试"""
    
    # 初始化环境
    init_result = await init_environment()
    if not init_result:
        print("\n❌ 环境初始化失败")
        return
    
    print("\n" + "="*70)
    print("🚀 开始执行 Agent 测试")
    print("="*70)
    
    # 测试用例
    TEST_CASES = [
        ("快速问答", "你好"),
        ("代码生成", "帮我写一个 Python 函数，计算斐波那契数列"),
        ("概念解释", "解释一下什么是依赖注入"),
    ]
    
    results = []
    
    for i, (name, user_input) in enumerate(TEST_CASES, 1):
        result = await run_single_test(i, name, user_input)
        results.append(result)
        
        if i < len(TEST_CASES):
            print(f"\n⏳ 等待 3 秒后开始下一个测试...")
            await asyncio.sleep(3)
    
    # 汇总报告
    print(f"\n{'='*70}")
    print("📊 测试汇总报告")
    print(f"{'='*70}")
    
    for status, icon in [("success", "✅"), ("abnormal", "🔴"), ("cancelled", "🛑"), 
                         ("timeout", "⏱️"), ("error", "❌")]:
        count = sum(1 for r in results if r["status"] == status)
        if count > 0:
            print(f"\n{icon} {status.upper()}: {count} 个")
            for r in results:
                if r["status"] == status:
                    duration = r['duration']
                    duration_str = f"{duration/3600:.2f}h" if duration > 3600 else f"{duration:.1f}s"
                    print(f"   • [{r['name']}] {duration_str}, {r['steps_count']} 步")
                    if r.get('error'):
                        print(f"     问题: {r['error'][:60]}...")
    
    # 特别报告异常循环
    abnormal_results = [r for r in results if r["loop_detected"]]
    if abnormal_results:
        print(f"\n{'!'*70}")
        print("🚨 发现异常循环，需要排查!")
        print(f"{'!'*70}")
        print("\n排查建议:")
        print("  1. 检查 Supervisor 节点的路由逻辑")
        print("  2. 确认工具调用结果是否正确返回")
        print("  3. 查看是否有无限循环的 ReAct 推理")
        print("  4. 检查节点状态机转换逻辑")
    
    # Cleanup memory container
    global _memory_container
    if '_memory_container' in globals():
        try:
            await _memory_container.shutdown()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(run_agent_test())
