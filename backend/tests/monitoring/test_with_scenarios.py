#!/usr/bin/env python3
"""
使用 test_dialogue_scenarios.py 话术集进行批量测试

支持全部 19 种场景，共 212 个测试用例：

基础场景 (14 种):
- code_generation (8): 代码生成
- code_optimization (8): 代码优化  
- debugging (8): 代码调试
- file_operation (12): 文件操作
- knowledge_query (10): 知识查询
- android_control (12): Android 控制
- browser_automation (8): 浏览器自动化
- desktop_control (8): 桌面控制
- ambiguous (8): 模糊/边缘情况
- complex_task (4): 复杂任务
- dangerous_operation (6): 危险操作确认
- multi_turn (66): 多轮对话（包含55轮超长对话）
- reference_previous (6): 引用之前内容
- edge_case (8): 特殊字符/边界情况

新工具场景 (5 种):
- code_exploration (15): 代码探索（find_symbol/search_code/ask_codebase）
- edit_validation (4): 编辑验证（edit_file + verify_types）
- memory_knowledge (5): 内存/知识管理
- task_management (4): 任务管理

特殊场景:
    - 超长对话: 电商系统构建（55轮对话，测试长期上下文保持）

用法:
    # 测试全部场景
    python test_with_scenarios.py
    
    # 限制每类用例数
    python test_with_scenarios.py --max 2
    
    # 测试指定类别
    python test_with_scenarios.py --category code_generation
    python test_with_scenarios.py --category code_exploration  # 测试代码探索
    
    # 测试超长对话场景
    python test_with_scenarios.py --category multi_turn --max 4
    
    # 从第50个用例开始（跳过前49个，用于恢复中断的测试）
    python test_with_scenarios.py --start 50
    
    # 从第10个开始，每类最多测5个
    python test_with_scenarios.py --start 10 --max 5
    
    # 测试新工具场景
    python test_with_scenarios.py --category code_exploration --max 5
"""

import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime
from typing import Any
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("scenario_test")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

MAX_EXECUTION_TIME = 3 * 60 * 60  # 3小时


# 导入话术集
from test_dialogue_scenarios import (
    CODE_GENERATION_SCENARIOS,
    CODE_OPTIMIZATION_SCENARIOS,
    DEBUGGING_SCENARIOS,
    FILE_OPERATION_SCENARIOS,
    KNOWLEDGE_QUERY_SCENARIOS,
    ALL_SCENARIOS,
)


class LoopDetector:
    """循环检测器"""
    MAX_SAME_NODE_SEQUENCE = 8
    MAX_ITERATIONS = 10
    MAX_TOTAL_STEPS = 150
    STALL_THRESHOLD_SECONDS = 180
    
    def __init__(self):
        self.node_history = []
        self.is_abnormal = False
        self.last_error = None
        self.check_count = 0
        
    def add_nodes(self, steps):
        """添加节点记录"""
        prev_len = len(self.node_history)
        for i, step in enumerate(steps[prev_len:], start=prev_len+1):
            name = step.get("name", "N/A")
            self.node_history.append(name)
            
    def count_iterations(self):
        """统计 Supervisor -> Worker 迭代次数"""
        iterations = 0
        for i in range(len(self.node_history) - 1):
            if "Supervisor" in self.node_history[i] and "Worker" in self.node_history[i+1]:
                iterations += 1
        return iterations
    
    def check_loop(self):
        """检测循环"""
        self.check_count += 1
        nodes = self.node_history
        
        if len(nodes) < 6:
            return False, None, None
            
        # 检查连续相同节点
        for n in range(self.MAX_SAME_NODE_SEQUENCE, 2, -1):
            if len(nodes) >= n and len(set(nodes[-n:])) == 1:
                return True, f"节点 '{nodes[-1]}' 连续 {n} 次", "HIGH"
        
        # 检查迭代次数
        iterations = self.count_iterations()
        if iterations > self.MAX_ITERATIONS:
            return True, f"迭代次数过多: {iterations}", "MEDIUM"
        
        return False, None, None


class ErrorCollector:
    """
    错误收集器 - 收集和汇总测试过程中的各种错误
    """
    def __init__(self):
        self.errors = []
        self.error_counts = defaultdict(int)
        self.severity_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        
    def add_error(self, step_type: str, error_msg: str, severity: str = 'MEDIUM', step_data: dict = None):
        """添加一个错误记录"""
        error_record = {
            'timestamp': datetime.now().isoformat(),
            'step_type': step_type,
            'message': str(error_msg)[:500],  # 限制长度
            'severity': severity,
            'step_data': step_data
        }
        self.errors.append(error_record)
        self.error_counts[step_type] += 1
        self.severity_counts[severity] += 1
        
    def has_errors(self) -> bool:
        """是否有错误记录"""
        return len(self.errors) > 0
    
    def get_summary(self) -> str:
        """获取错误汇总报告"""
        if not self.errors:
            return ""
        
        lines = [f"  错误统计: 总计 {len(self.errors)} 个"]
        lines.append(f"    - 严重 (HIGH): {self.severity_counts['HIGH']}")
        lines.append(f"    - 中等 (MEDIUM): {self.severity_counts['MEDIUM']}")
        lines.append(f"    - 轻微 (LOW): {self.severity_counts['LOW']}")
        
        if self.error_counts:
            lines.append("  按类型分布:")
            for step_type, count in sorted(self.error_counts.items(), key=lambda x: -x[1]):
                lines.append(f"    - {step_type}: {count} 次")
        
        # 显示最近的3个错误详情
        if self.errors:
            lines.append("  最近错误详情:")
            for err in self.errors[-3:]:
                lines.append(f"    [{err['severity']}] {err['step_type']}: {err['message'][:80]}...")
        
        return "\n".join(lines)
    
    def get_errors_by_type(self, step_type: str) -> list:
        """获取特定类型的所有错误"""
        return [e for e in self.errors if e['step_type'] == step_type]
    
    def get_high_severity_errors(self) -> list:
        """获取高严重级别错误"""
        return [e for e in self.errors if e['severity'] == 'HIGH']


async def clean_historical_burden():
    """
    清理历史负担，确保测试在干净的环境中运行。
    清理内容包括：
    1. LangGraph Checkpointer 数据（对话状态）
    2. 应用数据库中的对话和消息记录
    3. 文件检查点
    4. 内存系统（短期/长期记忆）
    5. 向量数据库（LanceDB）
    6. 全局状态缓存
    7. Brain 记忆文件系统（journal.md、focus.md 等）
    """
    import shutil
    from app.core.config import settings
    from app.infrastructure.database.sql.database import engine, get_db_session
    
    logger.info("\n" + "="*60)
    logger.info("🧹 开始清理历史负担...")
    logger.info("="*60)
    
    # 1. 清理 LangGraph Checkpointer 表
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            # 获取所有 checkpointer 相关表
            tables_to_clean = ['checkpoints', 'checkpoint_writes', 'checkpoint_blobs', 'checkpoint_migrations']
            for table in tables_to_clean:
                try:
                    await conn.execute(text(f"DELETE FROM {table}"))
                    logger.info(f"  ✅ 清理表: {table}")
                except Exception as e:
                    logger.debug(f"  ⚠️  清理表 {table} 跳过: {e}")
    except Exception as e:
        logger.warning(f"  ⚠️  清理 checkpointer 表失败: {e}")
    
    # 2. 清理应用数据库表（测试相关的）
    try:
        from sqlalchemy import text
        from app import models
        
        tables_to_clean = [
            'messages',
            'conversations', 
            'file_checkpoints',
            'file_checkpoint_snapshots',
            'plans',
            'plan_steps',
            'autonomous_tasks',
            'jobs',
        ]
        
        async with engine.begin() as conn:
            # 禁用外键约束（SQLite）
            try:
                await conn.execute(text("PRAGMA foreign_keys = OFF"))
            except:
                pass
                
            for table in tables_to_clean:
                try:
                    await conn.execute(text(f"DELETE FROM {table}"))
                    logger.info(f"  ✅ 清理表: {table}")
                except Exception as e:
                    logger.debug(f"  ⚠️  清理表 {table} 跳过: {e}")
            
            # 重新启用外键约束
            try:
                await conn.execute(text("PRAGMA foreign_keys = ON"))
            except:
                pass
    except Exception as e:
        logger.warning(f"  ⚠️  清理应用数据库表失败: {e}")
    
    # 3. 清理内存系统
    try:
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        try:
            await container.memory_manager.flush()
            logger.info("  ✅ 内存系统已清理")
        finally:
            await container.shutdown()
    except Exception as e:
        logger.debug(f"  ⚠️  清理内存系统跳过: {e}")
    
    # 4. 清理 LanceDB 向量数据库
    try:
        lancedb_path = settings.LANCEDB_PATH
        if os.path.exists(lancedb_path):
            # 只清理数据文件，保留目录结构
            for item in os.listdir(lancedb_path):
                item_path = os.path.join(lancedb_path, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                    logger.info(f"  ✅ 清理 LanceDB: {item}")
                except Exception as e:
                    logger.debug(f"  ⚠️  清理 LanceDB 项 {item} 跳过: {e}")
    except Exception as e:
        logger.warning(f"  ⚠️  清理 LanceDB 失败: {e}")
    
    # 5. 清理全局状态缓存
    try:
        import app.core.globals as globals_module
        import app.core.persistence as persistence_module
        
        globals_module._graph = None
        globals_module._config_path = None
        globals_module._last_load_time = 0
        globals_module._checkpointer = None
        persistence_module._checkpointer = None
        persistence_module._db_pool = None
        logger.info("  ✅ 全局状态缓存已清理")
    except Exception as e:
        logger.debug(f"  ⚠️  清理全局缓存跳过: {e}")
    
    # 6. 清理缓存数据（活动监控、上下文等）
    try:
        from app.infrastructure.cache import cache
        # 清理所有以 chat: 和 activity: 开头的缓存键
        if hasattr(cache, 'clear'):
            await cache.clear()
            logger.info("  ✅ 应用缓存已清理")
    except Exception as e:
        logger.debug(f"  ⚠️  清理应用缓存跳过: {e}")
    
    # 7. 清理 Brain 记忆文件系统
    try:
        brain_root = settings.BRAIN_MEMORY_ROOT
        if os.path.exists(brain_root):
            for item in os.listdir(brain_root):
                item_path = os.path.join(brain_root, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                    logger.info(f"  ✅ 清理 Brain 记忆: {item}")
                except Exception as e:
                    logger.debug(f"  ⚠️  清理 Brain 记忆项 {item} 跳过: {e}")
    except Exception as e:
        logger.warning(f"  ⚠️  清理 Brain 记忆文件系统失败: {e}")
    
    logger.info("="*60)
    logger.info("🧹 历史负担清理完成")
    logger.info("="*60 + "\n")


async def init_env():
    """初始化环境"""
    from app.infrastructure.database.sql.database import Base, engine
    from sqlmodel import SQLModel
    from app.core.config import settings
    
    # 首先清理历史负担
    await clean_historical_burden()
    
    if settings.EMBEDDED_MODE:
        from app import models
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(SQLModel.metadata.create_all)
    
    try:
        from app.initial_data import init as init_data
        await asyncio.to_thread(init_data)
    except:
        pass
    
    # Initialize Memory using MemoryContainer
    try:
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        # Store container for cleanup at the end
        global _memory_container
        _memory_container = container
        logger.info("✅ Memory Manager 初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ Memory 初始化失败: {e}")
        
    try:
        from app.core.environment import awaken
        await awaken(project_id=1)
    except Exception as e:
        logger.warning(f"Failed to awaken environment in test: {e}")
    
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    sqlite_path = db_uri.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
    conn = await aiosqlite.connect(sqlite_path)
    checkpointer = AsyncSqliteSaver(conn=conn)
    await checkpointer.setup()
    
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    from app.core.persistence import set_checkpointer
    
    set_checkpointer(checkpointer)
    builder = GraphBuilder()
    config_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/config/agent_main.yaml"
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    
    # 8. 自动批准 HITL 请求（测试模式）
    try:
        from app.core.hitl import create_request, complete_request
        from app.core.context.manager import ContextManager
        from app.core.tools.registry import get_tool_map, clear_registry_cache
        
        clear_registry_cache()
        tool_map = get_tool_map()
        
        async def _auto_ask_human(
            prompt: str,
            input_type="text",
            options=None,
            context=None,
            default_value=None,
        ):
            try:
                ctx = ContextManager.current()
                thread_id = ctx.thread_id or "unknown"
            except Exception:
                thread_id = "unknown"
            
            response = default_value if default_value is not None else "Auto-approved in test mode"
            request = await create_request(
                thread_id=thread_id,
                request_type=input_type,
                prompt=prompt,
                options=options,
                context=context,
                default_value=default_value,
            )
            await complete_request(request.id, response)
            logger.info(f"  🤖 自动批准 ask_human [{thread_id}]: {prompt[:40]}... -> {response[:40]}")
            return response
        
        async def _auto_ask_confirm(
            action_description: str,
            risk_level="medium",
            details=None,
            consequences=None,
        ):
            try:
                ctx = ContextManager.current()
                thread_id = ctx.thread_id or "unknown"
            except Exception:
                thread_id = "unknown"
            
            response = "APPROVED"
            approval_context = f"Risk: {risk_level}\nAction: {action_description}"
            if details:
                approval_context += f"\nDetails: {details}"
            if consequences:
                approval_context += f"\nConsequences: {consequences}"
            
            request = await create_request(
                thread_id=thread_id,
                request_type="approval",
                prompt=action_description,
                context=approval_context,
                default_value="REJECTED",
            )
            await complete_request(request.id, response)
            logger.info(f"  🤖 自动批准 ask_confirm [{thread_id}]: {action_description[:40]}... -> {response}")
            return response
        
        if "ask_human" in tool_map:
            tool_map["ask_human"].coroutine = _auto_ask_human
        if "ask_confirm" in tool_map:
            tool_map["ask_confirm"].coroutine = _auto_ask_confirm
            
        logger.info("  ✅ HITL 自动批准已启用（测试模式）")
    except Exception as e:
        logger.warning(f"  ⚠️  启用 HITL 自动批准失败: {e}")
    
    logger.info("✅ 环境初始化完成")
    return True


async def run_single_test(test_id: int, category: str, scenario: dict):
    """运行单个测试，增强错误监控"""
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    user_input = scenario["cn"]  # 使用中文话术
    thread_id = f"test-{datetime.now().strftime('%H%M%S')}-{test_id}"
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🧪 [{test_id}] [{category}] {user_input}")
    logger.info(f"{'='*60}")
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    detector = LoopDetector()
    error_collector = ErrorCollector()  # 错误收集器
    start_time = datetime.now()
    
    # 后台监控 - 增强版：监控循环和错误
    async def monitor():
        last_step_count = 0
        stall_counter = 0
        
        while True:
            try:
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                break
            
            activity = await activity_monitor.get_activity(thread_id)
            if not activity:
                continue
            
            steps = activity.get('steps', [])
            current_step_count = len(steps)
            
            # 检测是否卡死（步骤数长时间不变）
            if current_step_count == last_step_count:
                stall_counter += 1
                
                # 检查最后一个步骤是否还在运行
                last_step = steps[-1] if steps else {}
                is_running = last_step.get('status') == 'running'
                
                # 如果步骤正在运行（例如 Bash 正在执行大任务），给予更长的宽容度（如 120秒）
                # 如果步骤已结束但总数不增加（死循环），则保持 30秒报警
                threshold = 40 if is_running else 10  # 120s vs 30s
                
                if stall_counter >= threshold:
                    logger.error(f"🔴 [{thread_id}] 检测到卡死: {stall_counter * 3}秒无进展 (Step Status: {last_step.get('status')})")
            else:
                stall_counter = 0
                last_step_count = current_step_count
            
            # Monitoring heartbeat
            if stall_counter > 0 and stall_counter % 5 == 0:
                last_step = steps[-1] if steps else {}
                logger.debug(f"⏳ [{thread_id}] Monitoring... stall_count: {stall_counter}, last_step_status: {last_step.get('status')}")
            
            detector.add_nodes(steps)
            
            # 检查步骤中的错误
            for step in steps[-5:]:  # 只检查最近的5步
                if step.get('error') or step.get('status') == 'error':
                    error_collector.add_error(
                        step_type=step.get('name', 'unknown'),
                        error_msg=step.get('error', 'Unknown error'),
                        step_data=step
                    )
            
            # 循环检测
            is_abnormal, error, severity = detector.check_loop()
            if is_abnormal and not detector.is_abnormal:
                detector.is_abnormal = True
                detector.last_error = error
                logger.error(f"🔴 检测到异常: {error}")
                error_collector.add_error(
                    step_type='loop_detection',
                    error_msg=error,
                    severity=severity
                )
                if severity == "HIGH":
                    await activity_monitor.signal_stop(thread_id)
                    return
    
    monitor_task = asyncio.create_task(monitor())
    
    # 运行测试并捕获详细错误
    test_error = None
    test_error_traceback = None
    final_state = None
    
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        status = "✅ 成功"
    except asyncio.TimeoutError:
        status = "⏱️ 超时"
        test_error = "Execution timeout"
        error_collector.add_error(
            step_type='timeout',
            error_msg=f'Test exceeded {MAX_EXECUTION_TIME}s limit',
            severity='HIGH'
        )
    except Exception as e:
        status = f"❌ 错误: {type(e).__name__}"
        test_error = str(e)
        test_error_traceback = traceback.format_exc()
        error_collector.add_error(
            step_type='exception',
            error_msg=str(e),
            severity='HIGH'
        )
        logger.error(f"🔴 [{thread_id}] 测试异常:\n{test_error_traceback}")
    
    monitor_task.cancel()
    try:
        await monitor_task
    except:
        pass
    
    elapsed = (datetime.now() - start_time).total_seconds()
    iterations = detector.count_iterations()
    
    # 获取最终状态用于诊断
    try:
        final_activity = await activity_monitor.get_activity(thread_id)
        if final_activity:
            final_state = {
                'status': final_activity.get('status'),
                'steps_count': len(final_activity.get('steps', [])),
                'final_outcome': final_activity.get('final_outcome'),
            }
    except Exception as e:
        logger.debug(f"获取最终状态失败: {e}")
    
    # 输出详细结果
    logger.info(f"\n📊 结果: {status} | 耗时: {elapsed:.1f}s | 迭代: {iterations} | 步骤: {len(detector.node_history)}")
    
    # 输出错误汇总
    error_summary = error_collector.get_summary()
    if error_summary:
        logger.warning(f"⚠️  [{thread_id}] 错误汇总:\n{error_summary}")
    
    return {
        "test_id": test_id,
        "category": category,
        "input": user_input[:50],
        "status": status,
        "elapsed": elapsed,
        "iterations": iterations,
        "steps": len(detector.node_history),
        "is_abnormal": detector.is_abnormal,
        "error_count": len(error_collector.errors),
        "high_severity_errors": error_collector.severity_counts['HIGH'],
        "error_details": error_collector.errors if error_collector.has_errors() else None,
        "final_state": final_state,
        "test_error": test_error,
    }


async def run_batch_tests(category_name: str = None, max_tests: int = None, start_from: int = 1):
    """
    批量运行测试
    
    Args:
        category_name: 指定测试类别，如 "code_generation"，None 表示全部
        max_tests: 每个类别最大测试数，None 表示全部
        start_from: 从第几个用例开始（1-based），默认从第1个开始
    """
    await init_env()
    
    # 准备测试用例
    test_cases = []
    
    if category_name and category_name in ALL_SCENARIOS:
        # 只测试指定类别
        scenarios = ALL_SCENARIOS[category_name]
        # 处理多轮对话的特殊结构（列表的列表）
        if category_name == "multi_turn":
            for scenario_list in scenarios[:max_tests] if max_tests else scenarios:
                for s in scenario_list:
                    test_cases.append((category_name, s))
        else:
            for s in scenarios[:max_tests] if max_tests else scenarios:
                test_cases.append((category_name, s))
    else:
        # 测试所有类别（19种场景）
        categories_to_test = [
            # 基础场景
            "code_generation",      # 代码生成
            "code_optimization",    # 代码优化
            "debugging",            # 代码调试
            "file_operation",       # 文件操作
            "knowledge_query",      # 知识查询
            "android_control",      # Android 控制
            "browser_automation",   # 浏览器自动化
            "desktop_control",      # 桌面控制
            "ambiguous",            # 模糊/边缘情况
            "complex_task",         # 复杂任务
            "dangerous_operation",  # 危险操作确认
            "multi_turn",           # 多轮对话
            "reference_previous",   # 引用之前内容
            "edge_case",            # 特殊字符/边界情况
            # 新工具场景
            "code_exploration",     # 代码探索（新）
            "edit_validation",      # 编辑验证（新）
            "memory_knowledge",     # 内存/知识（新）
            "task_management",      # 任务管理（新）
            "checkpoint",           # 检查点（新）
        ]
        
        for cat in categories_to_test:
            if cat not in ALL_SCENARIOS:
                continue
            scenarios = ALL_SCENARIOS[cat]
            # 处理多轮对话的特殊结构（列表的列表）
            if cat == "multi_turn":
                for scenario_list in scenarios[:max_tests] if max_tests else scenarios:
                    for s in scenario_list:
                        test_cases.append((cat, s))
            else:
                for s in scenarios[:max_tests] if max_tests else scenarios:
                    test_cases.append((cat, s))
    
    # 应用 start_from 参数（跳过前面的用例）
    total_cases = len(test_cases)
    if start_from > 1:
        if start_from > total_cases:
            logger.warning(f"⚠️  start_from ({start_from}) 超过总用例数 ({total_cases})，没有可运行的测试")
            return []
        skipped = start_from - 1
        test_cases = test_cases[start_from - 1:]
        logger.info(f"⏭️  跳过前 {skipped} 个用例，从第 {start_from} 个开始")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 批量测试开始 - 共 {len(test_cases)}/{total_cases} 个用例")
    logger.info(f"{'='*60}")
    
    results = []
    for i, (category, scenario) in enumerate(test_cases, start_from):
        result = await run_single_test(i, category, scenario)
        results.append(result)
        
        # 测试间隔
        if i < len(test_cases):
            logger.info(f"\n⏳ 等待 3 秒...")
            await asyncio.sleep(3)
    
    # 汇总报告
    logger.info(f"\n{'='*60}")
    logger.info("📊 测试汇总报告")
    logger.info(f"{'='*60}")
    
    success_count = sum(1 for r in results if "成功" in r["status"])
    abnormal_count = sum(1 for r in results if r["is_abnormal"])
    error_count = sum(r.get('error_count', 0) for r in results)
    high_severity_count = sum(r.get('high_severity_errors', 0) for r in results)
    
    # 按类别汇总错误
    category_errors = defaultdict(lambda: {'errors': 0, 'high': 0, 'abnormal': 0})
    for r in results:
        cat = r['category']
        category_errors[cat]['errors'] += r.get('error_count', 0)
        category_errors[cat]['high'] += r.get('high_severity_errors', 0)
        if r['is_abnormal']:
            category_errors[cat]['abnormal'] += 1
    
    # 显示每个测试的详细结果
    for r in results:
        icon = "🔴" if r["is_abnormal"] else ("❌" if r.get("error_count", 0) > 0 else "✅")
        error_info = ""
        if r.get("error_count", 0) > 0:
            error_info = f" | 错误:{r['error_count']}"
        logger.info(f"{icon} [{r['category']:20s}] {r['input']:30s} | {r['elapsed']:5.1f}s | 迭代:{r['iterations']}{error_info}")
    
    logger.info(f"\n{'='*60}")
    logger.info("📈 总体统计")
    logger.info(f"{'='*60}")
    logger.info(f"总计测试: {len(results)}")
    logger.info(f"成功: {success_count} | 失败: {len(results) - success_count}")
    logger.info(f"异常循环: {abnormal_count}")
    logger.info(f"错误总数: {error_count} (严重: {high_severity_count})")
    
    # 显示有问题的类别
    problematic = {k: v for k, v in category_errors.items() if v['errors'] > 0 or v['abnormal'] > 0}
    if problematic:
        logger.info(f"\n⚠️  问题类别统计:")
        for cat, stats in sorted(problematic.items(), key=lambda x: -(x[1]['errors'] + x[1]['abnormal'] * 10)):
            logger.info(f"  - {cat}: 错误 {stats['errors']} 个, 严重 {stats['high']} 个, 异常 {stats['abnormal']} 次")
    
    # 显示失败的测试详情
    failed_tests = [r for r in results if r.get('test_error') or r.get('error_count', 0) > 0]
    if failed_tests:
        logger.info(f"\n🔴 失败测试详情 (前5个):")
        for r in failed_tests[:5]:
            logger.info(f"  [{r['category']}] {r['input'][:40]}...")
            if r.get('test_error'):
                logger.info(f"    主错误: {r['test_error'][:80]}")
            if r.get('error_details'):
                for err in r['error_details'][:2]:  # 只显示前2个错误
                    logger.info(f"    - [{err['severity']}] {err['step_type']}: {err['message'][:60]}...")
    
    logger.info(f"\n{'='*60}")
    
    # 保存详细报告到 JSON 文件
    await save_test_report(results)
    
    # Cleanup memory container
    global _memory_container
    if '_memory_container' in globals():
        try:
            await _memory_container.shutdown()
        except:
            pass
    
    return results


async def save_test_report(results: list):
    """保存测试报告到 JSON 文件"""
    import json
    import os
    
    # 确保报告目录存在
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    os.makedirs(report_dir, exist_ok=True)
    
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = os.path.join(report_dir, f'test_report_{timestamp}.json')
    
    # 准备报告数据
    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total': len(results),
            'success': sum(1 for r in results if "成功" in r["status"]),
            'failed': sum(1 for r in results if "成功" not in r["status"]),
            'abnormal': sum(1 for r in results if r["is_abnormal"]),
            'total_errors': sum(r.get('error_count', 0) for r in results),
            'high_severity_errors': sum(r.get('high_severity_errors', 0) for r in results),
        },
        'results': results
    }
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"\n📄 详细报告已保存: {report_file}")
    except Exception as e:
        logger.warning(f"保存报告失败: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="批量测试 Agent 对话场景")
    parser.add_argument("--category", type=str, help="指定测试类别，如 code_generation")
    parser.add_argument("--max", type=int, help="每个类别最大测试数")
    parser.add_argument("--start", type=int, default=1, help="从第几个用例开始（1-based，默认从第1个开始）")
    args = parser.parse_args()
    
    asyncio.run(run_batch_tests(args.category, args.max, args.start))
