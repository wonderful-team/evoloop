#!/usr/bin/env python3
"""
macOS 速度优化实时测试（简化版 - 使用现有框架）

测试场景：打开 Chrome 查 AI 新闻 -> 存剪贴板 -> 微信发送给"文件传输助手"

用法:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    uv run python tests/monitoring/test_macos_speed_live.py
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
logger = logging.getLogger("macos_speed_live")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

MAX_EXECUTION_TIME = 10 * 60  # 10分钟


def check_optimization_in_logs(logs: list) -> dict:
    """检查日志中的优化指标"""
    metrics = {
        "shortcut_conversions": 0,
        "batch_usage": 0,
        "partial_screenshot": 0,
        "shortcuts_used": [],
        "keyboard_vs_click": {"keyboard": 0, "click": 0}
    }
    
    for log in logs:
        if "Converting click" in log and "shortcut" in log:
            metrics["shortcut_conversions"] += 1
            # 提取快捷键
            if "'" in log:
                shortcut = log.split("'")[3] if len(log.split("'")) > 3 else ""
                if shortcut:
                    metrics["shortcuts_used"].append(shortcut)
        
        if "action=batch" in log.lower() or 'action": "batch"' in log:
            metrics["batch_usage"] += 1
        
        if "Auto-capturing" in log or "region=" in log:
            metrics["partial_screenshot"] += 1
        
        if "key_press" in log and "cmd+" in log:
            metrics["keyboard_vs_click"]["keyboard"] += 1
        
        if '"action": "click"' in log or "action=click" in log.lower():
            metrics["keyboard_vs_click"]["click"] += 1
    
    return metrics


async def run_speed_test():
    """
    运行速度优化测试
    
    场景: 打开 Chrome 查 AI 新闻 -> 存剪贴板 -> 微信发送
    """
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    # 测试场景
    user_input = '打开 Chrome 查一下最新的 AI 新闻，把摘要存到剪贴板，然后打开微信发给其中的"文件传输助手"'
    thread_id = f"macos-speed-{datetime.now().strftime('%H%M%S')}"
    
    logger.info("\n" + "="*80)
    logger.info("🧪 macOS 速度优化实时测试")
    logger.info("="*80)
    logger.info(f"场景: Chrome 查 AI 新闻 → 复制摘要 → 微信发送")
    logger.info(f"输入: {user_input}")
    logger.info(f"线程: {thread_id}")
    logger.info(f"超时: {MAX_EXECUTION_TIME}s")
    logger.info("="*80 + "\n")
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    # 收集执行数据
    step_logs = []
    tool_calls_log = []
    start_time = datetime.now()
    
    async def monitor():
        """监控 Agent 执行"""
        last_step = 0
        
        while True:
            try:
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            
            try:
                activity = await activity_monitor.get_activity(thread_id)
                if not activity:
                    continue
                
                steps = activity.get('steps', [])
                
                # 处理新步骤
                for step in steps[last_step:]:
                    step_name = step.get('name', 'unknown')
                    step_duration = step.get('duration_ms', 0)
                    tool_calls = step.get('tool_calls', [])
                    
                    logger.info(f"\n📍 Step {last_step + 1}: {step_name} ({step_duration:.0f}ms)")
                    
                    for call in tool_calls:
                        tool_name = call.get('name', '')
                        args = call.get('arguments', {})
                        
                        if tool_name == 'desktop_control':
                            action = args.get('action', '')
                            
                            if action == 'key_press':
                                key = args.get('key', '')
                                logger.info(f"   ⌨️  key_press: {key}")
                                tool_calls_log.append(f"key_press: {key}")
                                
                                # 检测快捷键
                                if 'cmd+' in key or 'ctrl+' in key:
                                    step_logs.append(f"Shortcut used: {key}")
                            
                            elif action == 'click':
                                element = args.get('element_name') or f"({args.get('x')}, {args.get('y')})"
                                logger.info(f"   🖱️  click: {element}")
                                tool_calls_log.append(f"click: {element}")
                            
                            elif action == 'batch':
                                actions = args.get('actions', [])
                                logger.info(f"   📦 batch: {len(actions)} actions")
                                for i, a in enumerate(actions, 1):
                                    act = a.get('action', '')
                                    if act == 'key_press':
                                        logger.info(f"      {i}. key_press: {a.get('key', '')}")
                                    elif act == 'type_text':
                                        text = a.get('text', '')[:30]
                                        logger.info(f"      {i}. type_text: {text}...")
                                    elif act == 'click':
                                        logger.info(f"      {i}. click: {a.get('element_name', 'coords')}")
                                tool_calls_log.append(f"batch: {len(actions)} actions")
                                step_logs.append(f"action=batch, actions={len(actions)}")
                            
                            elif action == 'screenshot':
                                region = args.get('region', 'full')
                                logger.info(f"   📸 screenshot: {region}")
                                tool_calls_log.append(f"screenshot: {region}")
                                if region and region != 'full':
                                    step_logs.append(f"partial screenshot: {region}")
                            
                            elif action == 'type_text':
                                text = args.get('text', '')[:30]
                                logger.info(f"   ⌨️  type_text: {text}...")
                                tool_calls_log.append(f"type_text: {text}")
                    
                    last_step += 1
                
            except Exception as e:
                logger.debug(f"监控错误: {e}")
    
    # 启动监控
    monitor_task = asyncio.create_task(monitor())
    
    # 运行 Agent
    test_error = None
    try:
        logger.info("🚀 启动 Agent...")
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        logger.info("\n✅ Agent 执行完成")
        
    except asyncio.TimeoutError:
        logger.error(f"\n❌ 执行超时 (>{MAX_EXECUTION_TIME}s)")
        test_error = "timeout"
        
    except Exception as e:
        logger.error(f"\n❌ 执行异常: {e}")
        test_error = str(e)
        traceback.print_exc()
    
    # 停止监控
    monitor_task.cancel()
    try:
        await monitor_task
    except:
        pass
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # 分析结果
    logger.info("\n" + "="*80)
    logger.info("📊 测试结果分析")
    logger.info("="*80)
    logger.info(f"总耗时: {elapsed:.1f}s")
    logger.info(f"状态: {'成功' if not test_error else '失败 - ' + test_error}")
    
    # 检查优化指标
    metrics = check_optimization_in_logs(step_logs + tool_calls_log)
    
    logger.info(f"\n🚀 优化指标:")
    logger.info(f"  快捷键转换: {metrics['shortcut_conversions']} 次")
    logger.info(f"  Batch 使用: {metrics['batch_usage']} 次")
    logger.info(f"  部分截图: {metrics['partial_screenshot']} 次")
    logger.info(f"  使用的快捷键: {list(set(metrics['shortcuts_used']))}")
    
    keyboard = metrics['keyboard_vs_click']['keyboard']
    clicks = metrics['keyboard_vs_click']['click']
    total = keyboard + clicks
    if total > 0:
        ratio = keyboard / total * 100
        logger.info(f"  键盘/点击比例: {keyboard}/{clicks} ({ratio:.0f}% 键盘)")
    
    # 评分
    logger.info(f"\n📈 优化评分:")
    score = 0
    if metrics['shortcut_conversions'] > 0:
        logger.info(f"  ✅ 快捷键转换: +30分")
        score += 30
    else:
        logger.info(f"  ❌ 无快捷键转换")
    
    if metrics['batch_usage'] > 0:
        logger.info(f"  ✅ Batch 使用: +30分")
        score += 30
    else:
        logger.info(f"  ❌ 无 Batch 使用")
    
    if total > 0 and keyboard / total >= 0.5:
        logger.info(f"  ✅ 键盘优先: +40分")
        score += 40
    else:
        logger.info(f"  ⚠️  键盘使用不足")
    
    logger.info(f"\n  总分: {score}/100")
    if score >= 80:
        logger.info(f"  🌟 优秀! 速度优化生效")
    elif score >= 60:
        logger.info(f"  ✅ 良好，还有提升空间")
    else:
        logger.info(f"  ⚠️  需要优化")
    
    logger.info("="*80)
    
    return {
        "thread_id": thread_id,
        "elapsed_s": elapsed,
        "error": test_error,
        "metrics": metrics,
        "score": score
    }


async def init_graph():
    """初始化 Graph"""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    from app.core.persistence import set_checkpointer
    from app.core.config import settings
    
    logger.info("🔧 初始化 Graph...")
    
    # 创建 checkpointer
    db_uri = settings.CHECKPOINTER_DATABASE_URI
    sqlite_path = db_uri.replace("sqlite+aiosqlite://", "").replace("sqlite://", "")
    conn = await aiosqlite.connect(sqlite_path)
    checkpointer = AsyncSqliteSaver(conn=conn)
    await checkpointer.setup()
    set_checkpointer(checkpointer)
    
    # 构建 graph
    config_path = "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/core/engine/config/agent_main.yaml"
    builder = GraphBuilder()
    graph = builder.build(config_path, checkpointer=checkpointer)
    
    # 设置全局 graph
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    logger.info("✅ Graph 初始化完成")


async def main():
    """主函数"""
    logger.info("🔧 初始化环境...")
    
    # 初始化 Graph
    try:
        await init_graph()
    except Exception as e:
        logger.error(f"❌ Graph 初始化失败: {e}")
        return 1
    
    # 初始化 Memory
    try:
        from app.core.memory import memory_manager
        await memory_manager.initialize()
        logger.info("✅ Memory 初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ Memory 初始化失败（继续测试）: {e}")
    
    # 运行测试
    result = await run_speed_test()
    
    return 0 if not result['error'] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
