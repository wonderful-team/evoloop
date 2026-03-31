#!/usr/bin/env python3
"""
Agent 循环检测测试 - 区分正常迭代 vs 异常循环
"""

import asyncio
import logging
import os
import sys
from collections import Counter, deque
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("test_agent")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

MAX_EXECUTION_TIME = 5 * 60 * 60  # 5小时


class LoopDetector:
    """
    智能循环检测器
    区分: 正常迭代 (有实质进展) vs 异常循环 (重复无意义操作)
    """
    
    # 检测配置
    MAX_SAME_NODE_SEQUENCE = 8  # 同一节点连续8次视为异常
    MAX_TOTAL_STEPS = 150  # 总步骤超过150视为可疑
    MAX_ITERATIONS = 10  # Supervisor->Worker 循环超过10次视为过多
    STALL_THRESHOLD_SECONDS = 180  # 180秒无步骤增加视为卡住（用户反馈正常60-120秒）
    
    def __init__(self):
        self.node_history = deque(maxlen=200)
        self.step_details = []  # 详细步骤记录
        self.is_abnormal = False
        self.last_error = None
        self.check_count = 0
        self.iteration_count = 0  # Supervisor->Worker 迭代次数
        self.last_progress_time = None
        
    def add_nodes(self, steps):
        """添加节点记录"""
        prev_len = len(self.node_history)
        for i, step in enumerate(steps[prev_len:], start=prev_len+1):
            name = step.get("name", "N/A")
            status = step.get("status", "?")
            self.node_history.append(name)
            self.step_details.append({
                "index": i,
                "name": name,
                "status": status,
                "time": datetime.now()
            })
            logger.info(f"[Step {i}] {name} ({status})")
            
        if len(steps) > prev_len:
            self.last_progress_time = datetime.now()
            
    def count_iterations(self):
        """统计 Supervisor -> Worker 的迭代次数"""
        nodes = list(self.node_history)
        iterations = 0
        i = 0
        while i < len(nodes) - 1:
            # 寻找 Supervisor -> Worker 的转换
            if "Supervisor" in nodes[i] and "Worker" in nodes[i+1]:
                iterations += 1
                i += 2
            else:
                i += 1
        return iterations
    
    def analyze_patterns(self):
        """分析节点模式"""
        nodes = list(self.node_history)
        if len(nodes) < 6:
            return None
            
        analysis = {
            "total_steps": len(nodes),
            "supervisor_count": sum(1 for n in nodes if "Supervisor" in n),
            "worker_count": sum(1 for n in nodes if "Worker" in n),
            "tool_usage": Counter(n for n in nodes if n.startswith("Using ")),
            "thinking_count": sum(1 for n in nodes if "Thinking" in n),
        }
        analysis["iterations"] = self.count_iterations()
        return analysis
    
    def check_loop(self):
        """检测循环，返回 (is_abnormal, reason, severity)"""
        self.check_count += 1
        nodes = list(self.node_history)
        
        if len(nodes) < 6:
            return False, None, None
            
        # 1. 检查连续相同节点
        for n in range(self.MAX_SAME_NODE_SEQUENCE, 2, -1):
            if len(nodes) >= n and len(set(nodes[-n:])) == 1:
                node = nodes[-1]
                return True, f"节点 '{node}' 连续执行 {n} 次", "HIGH"
        
        # 2. 检查迭代次数过多
        iterations = self.count_iterations()
        if iterations > self.MAX_ITERATIONS:
            return True, f"Supervisor->Worker 迭代次数过多: {iterations} 次", "MEDIUM"
        
        # 3. 检查短周期重复模式（如 A-B-A-B-A-B）
        if len(nodes) >= 12:
            for period in range(2, 6):  # 检查周期 2-5
                pattern = nodes[-period:]
                matches = 0
                for i in range(len(nodes) - period, -1, -period):
                    if nodes[i:i+period] == pattern:
                        matches += 1
                    else:
                        break
                if matches >= 4:  # 同一模式重复4次
                    return True, f"检测到周期为{period}的固定循环: {pattern}", "HIGH"
        
        # 4. 检查总步骤过多
        if len(nodes) > self.MAX_TOTAL_STEPS:
            return True, f"总步骤过多: {len(nodes)} 步", "LOW"
        
        # 5. 检查是否卡住（无新步骤产生）
        if self.last_progress_time:
            stall_duration = (datetime.now() - self.last_progress_time).total_seconds()
            if stall_duration > self.STALL_THRESHOLD_SECONDS:
                return True, f"Agent 已卡住 {stall_duration:.0f} 秒无进展", "HIGH"
        
        return False, None, None
    
    def get_report(self) -> str:
        """生成详细诊断报告"""
        if not self.node_history:
            return "无执行记录"
        
        nodes = list(self.node_history)
        analysis = self.analyze_patterns() or {}
        recent = nodes[-20:]
        
        report = f"""
╔════════════════════════════════════════════════════════════════╗
║                    📊 执行诊断报告                              ║
╠════════════════════════════════════════════════════════════════╣
  总步骤数: {analysis.get('total_steps', len(nodes))}
  Supervisor 调用: {analysis.get('supervisor_count', 0)} 次
  Worker 调用: {analysis.get('worker_count', 0)} 次
  Supervisor->Worker 迭代: {analysis.get('iterations', 0)} 次
  Thinking 节点: {analysis.get('thinking_count', 0)} 次
  检测次数: {self.check_count}
  状态: {'🔴 异常' if self.is_abnormal else '🟢 正常'}

最近20个节点:
  {' -> '.join(recent)}
"""
        if analysis["tool_usage"]:
            report += "\n工具使用统计:\n"
            for tool, count in analysis["tool_usage"].most_common():
                report += f"  • {tool}: {count} 次\n"
        
        # 检测是否有循环迹象
        if analysis["iterations"] > 5:
            report += f"\n⚠️ 警告: Supervisor->Worker 迭代已达 {analysis['iterations']} 次，可能进入循环\n"
            
        if analysis['thinking_count'] / len(nodes) > 0.5:
            report += f"\n⚠️ 警告: Thinking 节点占比过高 ({analysis['thinking_count']/len(nodes)*100:.1f}%)\n"
            
        report += "╚════════════════════════════════════════════════════════════════╝"
        return report


async def init_env():
    """快速初始化"""
    logger.info("=" * 60)
    logger.info("🚀 开始初始化测试环境")
    logger.info("=" * 60)
    
    from app.infrastructure.database.sql.database import Base, engine
    from sqlmodel import SQLModel
    from app.core.config import settings
    
    # DB
    logger.info("[1/5] 初始化数据库...")
    try:
        if settings.EMBEDDED_MODE:
            from app import models
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.run_sync(SQLModel.metadata.create_all)
            logger.info("   ✅ SQLite 表创建完成")
    except Exception as e:
        logger.warning(f"   ⚠️ {e}")
    
    # Config
    logger.info("[2/5] 初始化系统配置...")
    try:
        from app.initial_data import init as init_data
        await asyncio.to_thread(init_data)
        logger.info("   ✅ 系统配置初始化完成")
    except Exception as e:
        logger.warning(f"   ⚠️ {e}")
    
    # Memory
    logger.info("[3/5] 初始化 Memory Manager...")
    try:
        from app.core.memory import memory_manager
        await memory_manager.initialize()
        logger.info("   ✅ Memory Manager 初始化完成")
    except Exception as e:
        logger.warning(f"   ⚠️ {e}")
    
    # Checkpointer
    logger.info("[4/5] 初始化 Checkpointer...")
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    sqlite_path = db_uri.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
    conn = await aiosqlite.connect(sqlite_path)
    checkpointer = AsyncSqliteSaver(conn=conn)
    await checkpointer.setup()
    logger.info("   ✅ Checkpointer 初始化完成")
    
    # Graph
    logger.info("[5/5] 构建 Agent Graph...")
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    from app.core.persistence import set_checkpointer
    
    set_checkpointer(checkpointer)
    builder = GraphBuilder()
    config_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/config/agent_main.yaml"
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    logger.info("   ✅ Agent Graph 构建完成")
    
    logger.info("=" * 60)
    logger.info("✅ 环境初始化完成")
    logger.info("=" * 60)
    return True


# 测试用例列表
TEST_CASES = [
    ("简单问候", "你好"),
    ("代码生成-斐波那契", "帮我写一个 Python 函数，计算斐波那契数列"),
    ("代码生成-排序", "写一个快速排序算法"),
    ("概念解释", "解释一下什么是依赖注入"),
    ("文件操作", "创建一个 Python 脚本，读取当前目录下的所有文件并打印文件名"),
    ("调试问题", "我的 Python 代码报错了：NameError: name 'x' is not defined，怎么解决？"),
]


async def run_single_test(test_id: int, name: str, user_input: str):
    """运行单个测试"""
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    thread_id = f"loop-test-{datetime.now().strftime('%H%M%S')}-{test_id}"
    
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"🧪 [测试 {test_id}/{len(TEST_CASES)}] {name}")
    logger.info(f"输入: {user_input}")
    logger.info(f"Thread ID: {thread_id}")
    logger.info("=" * 60)
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    detector = LoopDetector()
    start_time = datetime.now()
    last_logged_iteration = 0
    
    # 后台监控
    async def monitor():
        nonlocal last_logged_iteration
        check_interval = 3
        
        while True:
            try:
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            
            elapsed = (datetime.now() - start_time).total_seconds()
            activity = await activity_monitor.get_activity(thread_id)
            
            if not activity:
                continue
            
            steps = activity.get('steps', [])
            status = activity.get('status', 'unknown')
            
            # 添加节点
            detector.add_nodes(steps)
            
            # 检测循环
            is_abnormal, error, severity = detector.check_loop()
            
            # 迭代进展日志
            current_iterations = detector.count_iterations()
            if current_iterations > last_logged_iteration:
                logger.info(f"[迭代 {current_iterations}] Supervisor->Worker 路由发生")
                last_logged_iteration = current_iterations
            
            # 异常检测
            if is_abnormal and not detector.is_abnormal:
                detector.is_abnormal = True
                detector.last_error = error
                logger.error("")
                logger.error("╔" + "="*58 + "╗")
                logger.error(f"║ 🔴 检测到异常循环! [{severity}]" + " "*(32-len(severity)) + "║")
                logger.error("╠" + "="*58 + "╣")
                logger.error(f"║ 问题: {error[:50]:50s} ║")
                logger.error(f"║ 时间: {elapsed:5.1f}s{' '*46} ║")
                logger.error(f"║ 步骤: {len(steps)} 步 | 迭代: {current_iterations} 次{' '*27} ║")
                logger.error("╚" + "="*58 + "╝")
                logger.error("")
                
                if severity == "HIGH":
                    logger.error("🛑 高严重性问题，正在停止 Agent...")
                    await activity_monitor.signal_stop(thread_id)
                    return True
                else:
                    logger.warning("⚠️  中/低严重性问题，继续监控...")
            
            # 正常进度日志 (每 30 秒或每 10 次检查)
            if detector.check_count % 10 == 0:
                analysis = detector.analyze_patterns() or {}
                logger.info(f"[进度] {elapsed:5.1f}s | 状态: {status:10s} | "
                          f"步骤: {analysis.get('total_steps', len(steps)):3d} | "
                          f"迭代: {analysis.get('iterations', 0):2d} | "
                          f"检查: #{detector.check_count}")
    
    # 同时运行 Agent 和监控
    monitor_task = asyncio.create_task(monitor())
    
    try:
        logger.info("🚀 启动 Agent...")
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        logger.info("✅ Agent 正常完成")
    except asyncio.CancelledError:
        logger.info("🛑 Agent 被取消")
    except asyncio.TimeoutError:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"⏱️ 超时! 运行时间: {elapsed/3600:.2f}小时")
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"❌ 错误 ({elapsed:.1f}s): {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 取消监控
    if not monitor_task.done():
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    
    # 最终报告
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("")
    logger.info(detector.get_report())
    
    logger.info("╔" + "="*58 + "╗")
    logger.info(f"║ 📊 [{test_id}] {name}" + " "*(50-len(name)-len(str(test_id))) + "║")
    logger.info("╠" + "="*58 + "╣")
    logger.info(f"║ 运行时间: {elapsed:6.1f}s ({elapsed/60:.1f}分钟){' '*22} ║")
    logger.info(f"║ 最终状态: {'🔴 异常' if detector.is_abnormal else '🟢 正常'}{' '*44} ║")
    logger.info(f"║ 检查次数: {detector.check_count}{' '*43} ║")
    logger.info("╚" + "="*58 + "╝")
    
    return {
        "test_id": test_id,
        "name": name,
        "input": user_input,
        "elapsed": elapsed,
        "is_abnormal": detector.is_abnormal,
        "steps": len(detector.node_history),
        "iterations": detector.count_iterations(),
    }


async def run_test():
    """运行所有测试用例"""
    await init_env()
    
    logger.info("")
    logger.info("╔" + "="*58 + "╗")
    logger.info(f"║ 🧪 批量测试 - 共 {len(TEST_CASES)} 个用例" + " "*(35-len(str(TEST_CASES))))
    logger.info("╚" + "="*58 + "╝")
    
    results = []
    for i, (name, user_input) in enumerate(TEST_CASES, 1):
        result = await run_single_test(i, name, user_input)
        results.append(result)
        
        # 测试间等待
        if i < len(TEST_CASES):
            logger.info("\n⏳ 等待 5 秒后开始下一个测试...")
            await asyncio.sleep(5)
    
    # 总汇总
    logger.info("")
    logger.info("╔" + "="*58 + "╗")
    logger.info("║                    📊 总 汇 总" + " "*26 + "║")
    logger.info("╠" + "="*58 + "╣")
    
    abnormal_count = sum(1 for r in results if r["is_abnormal"])
    
    for r in results:
        status = "🔴 异常" if r["is_abnormal"] else "✅ 正常"
        logger.info(f"║ [{r['test_id']}] {r['name']:20s} | {r['elapsed']:5.1f}s | {status} ║")
    
    logger.info("╠" + "="*58 + "╣")
    logger.info(f"║ 总计: {len(results)} 个 | 异常: {abnormal_count} 个 | 正常: {len(results)-abnormal_count} 个{' '*12} ║")
    logger.info("╚" + "="*58 + "╝")


if __name__ == "__main__":
    asyncio.run(run_test())
