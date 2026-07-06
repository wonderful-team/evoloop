#!/usr/bin/env python3
"""
多轮对话测试脚本 - 在线PTE模拟考试系统开发

project_id: 43
场景: 开发在线PTE模拟考试系统
架构: 支持 ARM64 (Apple Silicon) / x86_64

这是一个多轮对话测试，模拟用户与AI助手逐步讨论和开发PTE考试系统的完整流程。
涵盖需求分析、技术架构设计、数据库设计、核心功能实现等多个方面。

用法:
    # 运行完整的多轮对话测试
    python test_pte_multi_turn.py
    
    # ARM64 架构明确指定运行（Mac Apple Silicon）
    arch -arm64 python3 test_pte_multi_turn.py
    
    # 限制对话轮数
    python test_pte_multi_turn.py --max-turns 5
    
    # 从第3个场景开始
    python test_pte_multi_turn.py --start-scenario 3

ARM64 测试报告: PHASE3_ARM64_TEST_REPORT.md
"""

import asyncio
import logging
import os
import sys
import traceback
import json
from datetime import datetime
from typing import Any, List, Dict
from collections import defaultdict

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("pte_multi_turn_test")

# 第三方库日志级别设为 INFO，避免过多干扰
logging.getLogger("httpcore").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

MAX_EXECUTION_TIME = 10 * 60  # 10分钟每轮
PROJECT_ID = 43  # 指定项目ID

# 详细日志开关
VERBOSE_LOGGING = True  # 设置为 False 可减少日志输出


# ============================================
# 多轮对话场景定义 - PTE模拟考试系统开发
# ============================================

PTE_MULTI_TURN_SCENARIOS: List[List[Dict[str, Any]]] = [
    # 场景1: 项目初始化和需求分析
    [
        {
            "turn": 1,
            "cn": "你好，我想开发一个在线PTE模拟考试系统，你能帮我规划一下吗？",
            "context": "用户开始新项目，需要整体规划",
            "expected_topics": ["需求分析", "功能模块", "技术选型"]
        },
        {
            "turn": 2,
            "cn": "PTE考试包含口语、写作、阅读、听力四个部分，我需要为每个部分设计独立的练习模块。请帮我设计数据库表结构。",
            "context": "用户补充具体需求，需要数据库设计",
            "expected_topics": ["数据库设计", "表结构", "关系模型"]
        },
        {
            "turn": 3,
            "cn": "对了，口语部分需要录音功能，这个怎么实现？还有自动评分系统怎么设计？",
            "context": "用户询问具体功能实现",
            "expected_topics": ["音频录制", "语音识别", "自动评分"]
        },
        {
            "turn": 4,
            "cn": "请帮我生成项目的初始目录结构和基础配置文件。",
            "context": "用户需要代码实现",
            "expected_topics": ["项目结构", "配置文件", "初始化代码"]
        }
    ],
    
    # 场景2: 口语模块详细设计
    [
        {
            "turn": 1,
            "cn": "我需要详细设计PTE口语模块。PTE口语有Read Aloud、Repeat Sentence、Describe Image等题型，每种题型都需要不同的前端界面和评分逻辑。",
            "context": "深入口语模块设计",
            "expected_topics": ["题型设计", "UI界面", "评分逻辑"]
        },
        {
            "turn": 2,
            "cn": "Read Aloud题型需要文本展示、倒计时、录音按钮和波形图显示。请帮我设计这个组件的React代码。",
            "context": "具体题型UI实现",
            "expected_topics": ["React组件", "录音UI", "波形图"]
        },
        {
            "turn": 3,
            "cn": "录音完成后需要实时转文字，然后与原文对比计算流利度和发音准确度。这个算法怎么实现？",
            "context": "评分算法设计",
            "expected_topics": ["语音转文字", "文本对比", "评分算法"]
        },
        {
            "turn": 4,
            "cn": "请帮我生成口语模块的后端API接口设计，包括开始练习、提交录音、获取评分等接口。",
            "context": "后端API设计",
            "expected_topics": ["API设计", "接口文档", "后端实现"]
        }
    ],
    
    # 场景3: 写作模块设计
    [
        {
            "turn": 1,
            "cn": "现在来设计写作模块。PTE写作有Summarize Written Text和Write Essay两种题型，需要富文本编辑器和字数统计功能。",
            "context": "写作模块需求",
            "expected_topics": ["富文本编辑器", "字数统计", "写作题型"]
        },
        {
            "turn": 2,
            "cn": "我需要集成一个语法检查功能，可以检查拼写错误、语法错误和词汇使用建议。有什么好的方案？",
            "context": "语法检查功能",
            "expected_topics": ["语法检查", "拼写检查", "API集成"]
        },
        {
            "turn": 3,
            "cn": "请帮我设计写作评分的数据库表，需要存储用户作文内容、评分结果、语法错误等信息。",
            "context": "写作模块数据库",
            "expected_topics": ["数据库表", "评分存储", "错误记录"]
        }
    ],
    
    # 场景4: 阅读和听力模块
    [
        {
            "turn": 1,
            "cn": "阅读模块需要支持Multiple Choice、Reorder Paragraphs、Fill in the Blanks等题型。请帮我设计一个通用的题目渲染组件。",
            "context": "阅读模块设计",
            "expected_topics": ["题目组件", "拖拽排序", "填空题"]
        },
        {
            "turn": 2,
            "cn": "听力模块比较特殊，需要音频播放器，支持播放、暂停、进度拖动，还要能调整播放速度。请设计这个播放器组件。",
            "context": "听力播放器设计",
            "expected_topics": ["音频播放器", "播放控制", "速度调节"]
        },
        {
            "turn": 3,
            "cn": "听力材料需要从后端动态加载，请帮我设计听力资源的存储方案和API接口。",
            "context": "听力资源管理",
            "expected_topics": ["资源存储", "音频文件", "CDN加速"]
        }
    ],
    
    # 场景5: 用户系统和进度追踪
    [
        {
            "turn": 1,
            "cn": "我需要设计用户系统，包括注册登录、个人资料、学习计划等功能。请帮我设计用户相关的数据库表。",
            "context": "用户系统设计",
            "expected_topics": ["用户认证", "个人资料", "学习计划"]
        },
        {
            "turn": 2,
            "cn": "用户的学习进度需要实时追踪，包括各模块的练习次数、平均分、弱项分析。请设计进度追踪的数据结构和API。",
            "context": "学习进度追踪",
            "expected_topics": ["进度统计", "数据分析", "弱项识别"]
        },
        {
            "turn": 3,
            "cn": "我想添加一个智能推荐功能，根据用户的弱项自动推荐练习题目。这个推荐算法怎么设计？",
            "context": "智能推荐系统",
            "expected_topics": ["推荐算法", "个性化", "机器学习"]
        }
    ],
    
    # 场景6: 模拟考试和成绩报告
    [
        {
            "turn": 1,
            "cn": "模拟考试功能需要按照真实PTE考试的时间和流程来设计，总共3小时，各部分有严格的时间限制。请帮我设计考试流程控制。",
            "context": "模拟考试设计",
            "expected_topics": ["考试流程", "计时器", "时间控制"]
        },
        {
            "turn": 2,
            "cn": "考试结束后需要生成详细的成绩报告，包括各部分得分、与目标分数的对比、改进建议。请设计成绩报告的UI和数据结构。",
            "context": "成绩报告设计",
            "expected_topics": ["成绩报告", "数据可视化", "图表展示"]
        },
        {
            "turn": 3,
            "cn": "请帮我生成一个完整的模拟考试系统的部署方案，包括前端、后端、数据库、音频存储等。",
            "context": "系统部署",
            "expected_topics": ["部署方案", "架构设计", "运维配置"]
        }
    ]
]


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
    """错误收集器"""
    def __init__(self):
        self.errors = []
        self.error_counts = defaultdict(int)
        self.severity_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        
    def add_error(self, step_type: str, error_msg: str, severity: str = 'MEDIUM', step_data: dict = None):
        """添加一个错误记录"""
        error_record = {
            'timestamp': datetime.now().isoformat(),
            'step_type': step_type,
            'message': str(error_msg)[:500],
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
        
        if self.errors:
            lines.append("  最近错误详情:")
            for err in self.errors[-3:]:
                lines.append(f"    [{err['severity']}] {err['step_type']}: {err['message'][:80]}...")
        
        return "\n".join(lines)


async def clean_historical_burden():
    """清理历史负担"""
    import shutil
    from app.core.config import settings
    from app.infrastructure.database import session_scope
from app.infrastructure.database.sql.database import engine
    
    logger.info("\n" + "="*60)
    logger.info("🧹 开始清理历史负担...")
    logger.info("="*60)
    
    # 1. 清理 LangGraph Checkpointer 表
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            tables_to_clean = ['checkpoints', 'checkpoint_writes', 'checkpoint_blobs', 'checkpoint_migrations']
            for table in tables_to_clean:
                try:
                    await conn.execute(text(f"DELETE FROM {table}"))
                    logger.info(f"  ✅ 清理表: {table}")
                except Exception as e:
                    logger.debug(f"  ⚠️  清理表 {table} 跳过: {e}")
    except Exception as e:
        logger.warning(f"  ⚠️  清理 checkpointer 表失败: {e}")
    
    # 2. 清理应用数据库表
    try:
        from sqlalchemy import text
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
    
    # 4. 清理 LanceDB
    try:
        lancedb_path = settings.LANCEDB_PATH
        if os.path.exists(lancedb_path):
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
    
    # 6. 清理 Brain 记忆文件系统
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
    
    # Initialize Memory
    try:
        from app.core.memory import MemoryContainer, MemoryConfig
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        global _memory_container
        _memory_container = container
        logger.info("✅ Memory Manager 初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ Memory 初始化失败: {e}")
        
    try:
        from app.core.environment import awaken
        await awaken(project_id=PROJECT_ID)
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
    
    # 自动批准 HITL 请求
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
    
    logger.info(f"✅ 环境初始化完成 (Project ID: {PROJECT_ID})")
    return True


async def run_single_turn(
    scenario_idx: int, 
    turn_idx: int, 
    scenario: dict, 
    thread_id: str,
    conversation_history: List[dict] = None
):
    """运行单轮对话"""
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    user_input = scenario["cn"]
    context = scenario.get("context", "")
    expected_topics = scenario.get("expected_topics", [])
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🎬 场景 {scenario_idx + 1} - 第 {turn_idx + 1} 轮")
    logger.info(f"📋 上下文: {context}")
    logger.info(f"🎯 期望主题: {', '.join(expected_topics)}")
    logger.info(f"{'='*60}")
    logger.info(f"👤 用户: {user_input}")
    logger.info(f"{'='*60}")
    
    # DEBUG 级别详细信息
    logger.debug(f"[TURN DETAIL] Thread ID: {thread_id}")
    logger.debug(f"[TURN DETAIL] Project ID: {PROJECT_ID}")
    logger.debug(f"[TURN DETAIL] Input length: {len(user_input)} chars")
    logger.debug(f"[TURN DETAIL] Conversation history length: {len(conversation_history) if conversation_history else 0}")
    
    # 构建消息历史
    messages = []
    if conversation_history:
        for i, msg in enumerate(conversation_history):
            messages.append(msg)
            logger.debug(f"[HISTORY] Msg {i+1}: type={msg.get('type')}, content_len={len(msg.get('content', ''))}")
    messages.append({"type": "human", "content": user_input})
    
    inputs = {
        "messages": messages,
        "project_id": PROJECT_ID,
        "goal": f"开发在线PTE模拟考试系统 - {context}",
        "is_retry": False
    }
    
    logger.debug(f"[INPUT] Total messages: {len(messages)}")
    logger.debug(f"[INPUT] Goal: {inputs['goal']}")
    logger.debug(f"[INPUT] Project ID: {inputs['project_id']}")
    
    detector = LoopDetector()
    error_collector = ErrorCollector()
    start_time = datetime.now()
    
    # 后台监控
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
            
            if current_step_count == last_step_count:
                stall_counter += 1
                last_step = steps[-1] if steps else {}
                is_running = last_step.get('status') == 'running'
                threshold = 40 if is_running else 10
                
                if stall_counter >= threshold:
                    logger.error(f"🔴 [{thread_id}] 检测到卡死: {stall_counter * 3}秒无进展")
            else:
                stall_counter = 0
                last_step_count = current_step_count
            
            detector.add_nodes(steps)
            
            for step in steps[-5:]:
                if step.get('error') or step.get('status') == 'error':
                    error_collector.add_error(
                        step_type=step.get('name', 'unknown'),
                        error_msg=step.get('error', 'Unknown error'),
                        step_data=step
                    )
            
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
    
    test_error = None
    test_error_traceback = None
    final_state = None
    response_content = None
    
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        status = "✅ 成功"
        
        # 获取最终响应
        try:
            final_activity = await activity_monitor.get_activity(thread_id)
            if final_activity and final_activity.get('steps'):
                last_step = final_activity['steps'][-1]
                response_content = last_step.get('output', '')
        except Exception as e:
            logger.debug(f"获取响应内容失败: {e}")
            
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
    
    # 获取最终状态
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
    
    # 输出结果
    logger.info(f"\n📊 结果: {status} | 耗时: {elapsed:.1f}s | 迭代: {iterations} | 步骤: {len(detector.node_history)}")
    
    if response_content:
        # 截断显示
        display_content = response_content[:300] + "..." if len(response_content) > 300 else response_content
        logger.info(f"🤖 AI回复:\n{display_content}")
    
    error_summary = error_collector.get_summary()
    if error_summary:
        logger.warning(f"⚠️  [{thread_id}] 错误汇总:\n{error_summary}")
    
    return {
        "scenario_idx": scenario_idx,
        "turn_idx": turn_idx,
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
        "response": response_content,
        "expected_topics": expected_topics,
    }


async def run_multi_turn_scenario(
    scenario_idx: int, 
    scenario_turns: List[dict],
    max_turns: int = None
):
    """运行一个完整的多轮对话场景"""
    thread_id = f"pte-test-{datetime.now().strftime('%H%M%S')}-s{scenario_idx + 1}"
    
    logger.info(f"\n{'#'*60}")
    logger.info(f"# 🎯 开始场景 {scenario_idx + 1}/{len(PTE_MULTI_TURN_SCENARIOS)}")
    logger.info(f"# 📌 Thread ID: {thread_id}")
    logger.info(f"# 🔢 对话轮数: {len(scenario_turns)}")
    logger.info(f"{'#'*60}")
    
    results = []
    conversation_history = []
    
    turns_to_run = scenario_turns[:max_turns] if max_turns else scenario_turns
    
    for turn_idx, scenario in enumerate(turns_to_run):
        result = await run_single_turn(
            scenario_idx=scenario_idx,
            turn_idx=turn_idx,
            scenario=scenario,
            thread_id=thread_id,
            conversation_history=conversation_history
        )
        results.append(result)
        
        # 更新对话历史
        conversation_history.append({"type": "human", "content": scenario["cn"]})
        if result.get("response"):
            conversation_history.append({"type": "ai", "content": result["response"]})
        
        # 轮间等待
        if turn_idx < len(turns_to_run) - 1:
            logger.info(f"\n⏳ 等待 2 秒进入下一轮...")
            await asyncio.sleep(2)
    
    # 场景汇总
    success_count = sum(1 for r in results if "成功" in r["status"])
    abnormal_count = sum(1 for r in results if r["is_abnormal"])
    total_errors = sum(r.get('error_count', 0) for r in results)
    
    logger.info(f"\n{'#'*60}")
    logger.info(f"# 📊 场景 {scenario_idx + 1} 完成")
    logger.info(f"# ✅ 成功: {success_count}/{len(results)}")
    logger.info(f"# ⚠️ 异常: {abnormal_count}")
    logger.info(f"# ❌ 错误: {total_errors}")
    logger.info(f"{'#'*60}")
    
    return {
        "scenario_idx": scenario_idx,
        "thread_id": thread_id,
        "total_turns": len(turns_to_run),
        "success_count": success_count,
        "abnormal_count": abnormal_count,
        "total_errors": total_errors,
        "turn_results": results
    }


async def run_all_tests(max_turns: int = None, start_scenario: int = 1):
    """运行所有多轮对话测试"""
    await init_env()
    
    logger.info(f"\n{'='*60}")
    logger.info("🚀 PTE多轮对话测试开始")
    logger.info(f"📍 Project ID: {PROJECT_ID}")
    logger.info(f"📝 场景: 开发在线PTE模拟考试系统")
    logger.info(f"🔢 场景数量: {len(PTE_MULTI_TURN_SCENARIOS)}")
    if max_turns:
        logger.info(f"⚡ 每场景最大轮数: {max_turns}")
    logger.info(f"{'='*60}")
    
    all_results = []
    scenarios_to_run = PTE_MULTI_TURN_SCENARIOS[start_scenario - 1:]
    
    for i, scenario_turns in enumerate(scenarios_to_run, start_scenario):
        scenario_result = await run_multi_turn_scenario(
            scenario_idx=i - 1,
            scenario_turns=scenario_turns,
            max_turns=max_turns
        )
        all_results.append(scenario_result)
        
        # 场景间等待
        if i < len(PTE_MULTI_TURN_SCENARIOS):
            logger.info(f"\n⏳ 等待 5 秒进入下一场景...")
            await asyncio.sleep(5)
    
    # 最终汇总报告
    logger.info(f"\n{'='*60}")
    logger.info("📊 最终测试汇总报告")
    logger.info(f"{'='*60}")
    
    total_scenarios = len(all_results)
    total_turns = sum(r["total_turns"] for r in all_results)
    total_success = sum(r["success_count"] for r in all_results)
    total_abnormal = sum(r["abnormal_count"] for r in all_results)
    total_errors = sum(r["total_errors"] for r in all_results)
    
    logger.info(f"\n📈 总体统计:")
    logger.info(f"  - 场景总数: {total_scenarios}")
    logger.info(f"  - 对话轮数: {total_turns}")
    logger.info(f"  - 成功轮数: {total_success}/{total_turns}")
    logger.info(f"  - 异常场景: {total_abnormal}")
    logger.info(f"  - 总错误数: {total_errors}")
    
    # 每个场景的详细结果
    logger.info(f"\n📋 各场景详情:")
    for r in all_results:
        status_icon = "✅" if r["success_count"] == r["total_turns"] else ("⚠️" if r["abnormal_count"] > 0 else "❌")
        logger.info(f"  {status_icon} 场景 {r['scenario_idx'] + 1}: {r['success_count']}/{r['total_turns']} 成功, "
                   f"异常: {r['abnormal_count']}, 错误: {r['total_errors']}")
    
    # 保存详细报告
    await save_test_report(all_results)
    
    # Cleanup
    global _memory_container
    if '_memory_container' in globals():
        try:
            await _memory_container.shutdown()
        except:
            pass
    
    logger.info(f"\n{'='*60}")
    
    return all_results


async def save_test_report(results: list):
    """保存测试报告到 JSON 文件"""
    report_dir = os.path.join(os.path.dirname(__file__), 'reports')
    os.makedirs(report_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = os.path.join(report_dir, f'pte_multi_turn_report_{timestamp}.json')
    
    total_turns = sum(r["total_turns"] for r in results)
    total_success = sum(r["success_count"] for r in results)
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'project_id': PROJECT_ID,
        'scenario': '开发在线PTE模拟考试系统',
        'summary': {
            'total_scenarios': len(results),
            'total_turns': total_turns,
            'success_count': total_success,
            'failed_count': total_turns - total_success,
            'abnormal_count': sum(r["abnormal_count"] for r in results),
            'total_errors': sum(r["total_errors"] for r in results),
        },
        'scenarios': results
    }
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"\n📄 详细报告已保存: {report_file}")
    except Exception as e:
        logger.warning(f"保存报告失败: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PTE多轮对话测试")
    parser.add_argument("--max-turns", type=int, help="每个场景最大对话轮数")
    parser.add_argument("--start-scenario", type=int, default=1, help="从第几个场景开始（1-based）")
    args = parser.parse_args()
    
    asyncio.run(run_all_tests(args.max_turns, args.start_scenario))
