#!/usr/bin/env python3
"""
真实场景测试：AI 新闻查询并发送到微信

场景描述：
1. 打开 Chrome 查一下最新的 AI 新闻
2. 把摘要存到剪贴板
3. 打开微信发给其中的"文件传输助手"

测试目的：观察 Agent 是否：
✅ 使用键盘快捷键（而非鼠标点击）
✅ 使用 Batch 模式批量执行
✅ 使用部分截图提高效率
✅ 正确处理跨应用切换

用法:
    python test_real_scenario_ai_news.py
    python test_real_scenario_ai_news.py --verbose  # 查看详细步骤
"""

import asyncio
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("real_scenario_test")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

MAX_EXECUTION_TIME = 8 * 60  # 8分钟超时（跨应用操作需要更长时间）


@dataclass
class StepRecord:
    """步骤执行记录"""
    step_number: int
    step_name: str
    tool_calls: List[Dict] = field(default_factory=list)
    duration_ms: float = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def has_tool(self, tool_name: str, action: str = None) -> bool:
        """检查是否调用了特定工具"""
        for call in self.tool_calls:
            if call.get('name') == tool_name:
                if action is None:
                    return True
                args = call.get('arguments', {})
                if args.get('action') == action:
                    return True
        return False
    
    def get_shortcuts_used(self) -> List[str]:
        """获取使用的快捷键"""
        shortcuts = []
        for call in self.tool_calls:
            if call.get('name') == 'desktop_control':
                args = call.get('arguments', {})
                if args.get('action') == 'key_press':
                    key = args.get('key', '')
                    if 'cmd+' in key or 'ctrl+' in key:
                        shortcuts.append(key)
        return shortcuts


@dataclass
class OptimizationReport:
    """优化效果报告"""
    scenario_name: str
    user_input: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    steps: List[StepRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    # 优化指标
    total_tool_calls: int = 0
    screenshot_count: int = 0
    key_press_count: int = 0
    click_count: int = 0
    batch_count: int = 0
    shortcut_count: int = 0
    
    def finalize(self):
        """完成记录，计算统计"""
        self.end_time = datetime.now()
        
        for step in self.steps:
            for call in step.tool_calls:
                self.total_tool_calls += 1
                if call.get('name') == 'desktop_control':
                    args = call.get('arguments', {})
                    action = args.get('action', '')
                    
                    if action == 'screenshot':
                        self.screenshot_count += 1
                    elif action == 'key_press':
                        self.key_press_count += 1
                        key = args.get('key', '')
                        if 'cmd+' in key or 'ctrl+' in key:
                            self.shortcut_count += 1
                    elif action == 'click':
                        self.click_count += 1
                    elif action == 'batch':
                        self.batch_count += 1
    
    @property
    def duration_seconds(self) -> float:
        """总执行时间"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0
    
    @property
    def shortcut_usage_rate(self) -> float:
        """快捷键使用率"""
        if self.key_press_count > 0:
            return self.shortcut_count / self.key_press_count
        return 0
    
    @property
    def keyboard_vs_mouse_ratio(self) -> float:
        """键盘 vs 鼠标比例（越高越好）"""
        total_interactions = self.key_press_count + self.click_count
        if total_interactions > 0:
            return self.key_press_count / total_interactions
        return 0
    
    def print_report(self):
        """打印详细报告"""
        print("\n" + "="*80)
        print("🎯 真实场景测试报告")
        print("="*80)
        print(f"\n场景: {self.scenario_name}")
        print(f"输入: {self.user_input}")
        print(f"开始时间: {self.start_time.strftime('%H:%M:%S')}")
        print(f"总耗时: {self.duration_seconds:.1f}s")
        
        print(f"\n📊 执行步骤详情 ({len(self.steps)} 个步骤):")
        print("-" * 80)
        
        for step in self.steps:
            shortcuts = step.get_shortcuts_used()
            shortcut_str = f" [快捷键: {', '.join(shortcuts)}]" if shortcuts else ""
            
            tool_names = []
            for call in step.tool_calls:
                name = call.get('name', '')
                args = call.get('arguments', {})
                action = args.get('action', '')
                if action:
                    tool_names.append(f"{name}({action})")
                else:
                    tool_names.append(name)
            
            tools_str = ' → '.join(tool_names) if tool_names else '(无工具调用)'
            
            print(f"  Step {step.step_number}: {step.step_name}")
            print(f"           耗时: {step.duration_ms:.0f}ms | 工具: {tools_str}{shortcut_str}")
        
        print(f"\n📈 优化效果指标:")
        print("-" * 80)
        print(f"  总工具调用: {self.total_tool_calls} 次")
        print(f"  截图次数: {self.screenshot_count} 次")
        print(f"  键盘按键: {self.key_press_count} 次")
        print(f"  鼠标点击: {self.click_count} 次")
        print(f"  Batch 执行: {self.batch_count} 次")
        print(f"  快捷键使用: {self.shortcut_count} 次")
        
        print(f"\n  ✅ 快捷键使用率: {self.shortcut_usage_rate*100:.0f}%")
        print(f"  ✅ 键盘/鼠标比例: {self.keyboard_vs_mouse_ratio*100:.0f}% (越高越好)")
        
        # 优化建议
        print(f"\n💡 优化分析:")
        print("-" * 80)
        
        if self.shortcut_usage_rate >= 0.5:
            print(f"  ✅ 快捷键使用良好 ({self.shortcut_usage_rate*100:.0f}%)")
        else:
            print(f"  ⚠️  快捷键使用率偏低，建议检查是否使用了 click 替代 key_press")
        
        if self.batch_count > 0:
            print(f"  ✅ 使用了 Batch 模式 ({self.batch_count} 次)")
        else:
            print(f"  ⚠️  未使用 Batch 模式，建议批量执行连续操作")
        
        if self.click_count > self.key_press_count:
            print(f"  ⚠️  鼠标点击 ({self.click_count}) 多于键盘 ({self.key_press_count})，建议优先使用快捷键")
        else:
            print(f"  ✅ 键盘优先 ({self.key_press_count} 键盘 vs {self.click_count} 点击)")
        
        if self.errors:
            print(f"\n❌ 错误 ({len(self.errors)} 个):")
            for err in self.errors:
                print(f"  - {err}")
        
        print("\n" + "="*80)


async def init_env():
    """初始化环境"""
    logger.info("🔧 初始化测试环境...")
    
    try:
        from app.core.engine.graph_builder import GraphBuilder
        from app.infrastructure.database.sql.database import init_db
        from app.core.memory import MemoryContainer, MemoryConfig
        
        await init_db()
        logger.info("✅ 数据库初始化完成")
        
        # Initialize Memory using MemoryContainer
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        # Store container for cleanup
        global _memory_container
        _memory_container = container
        logger.info("✅ Memory 初始化完成")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 环境初始化失败: {e}")
        traceback.print_exc()
        return False


async def run_real_scenario_test(verbose: bool = False) -> OptimizationReport:
    """
    运行真实场景测试
    
    场景: 打开 Chrome 查 AI 新闻 -> 存剪贴板 -> 打开微信发送
    """
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    scenario_name = "AI 新闻查询并发送到微信"
    user_input = "打开 Chrome 查一下最新的 AI 新闻，把摘要存到剪贴板，然后打开微信发给其中的'文件传输助手'"
    
    thread_id = f"real-scenario-{datetime.now().strftime('%H%M%S')}"
    
    logger.info(f"\n{'='*80}")
    logger.info(f"🎯 开始真实场景测试")
    logger.info(f"{'='*80}")
    logger.info(f"场景: {scenario_name}")
    logger.info(f"输入: {user_input}")
    logger.info(f"线程: {thread_id}")
    logger.info(f"{'='*80}\n")
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    report = OptimizationReport(
        scenario_name=scenario_name,
        user_input=user_input
    )
    
    # 后台监控
    async def monitor():
        """监控 Agent 执行过程"""
        last_step_count = 0
        
        while True:
            try:
                await asyncio.sleep(1.5)
            except asyncio.CancelledError:
                break
            
            try:
                activity = await activity_monitor.get_activity(thread_id)
                if not activity:
                    continue
                
                steps = activity.get('steps', [])
                
                # 处理新步骤
                for i, step_data in enumerate(steps[last_step_count:], start=last_step_count+1):
                    step = StepRecord(
                        step_number=i,
                        step_name=step_data.get('name', f'Step {i}'),
                        duration_ms=step_data.get('duration_ms', 0),
                        timestamp=datetime.now()
                    )
                    
                    # 记录工具调用
                    tool_calls = step_data.get('tool_calls', [])
                    for call in tool_calls:
                        tool_name = call.get('name', '')
                        args = call.get('arguments', {})
                        
                        step.tool_calls.append({
                            'name': tool_name,
                            'arguments': args
                        })
                        
                        # 实时日志
                        if verbose:
                            if tool_name == 'desktop_control':
                                action = args.get('action', '')
                                if action == 'key_press':
                                    key = args.get('key', '')
                                    logger.info(f"   ⌨️  按键: {key}")
                                elif action == 'click':
                                    element = args.get('element_name') or f"({args.get('x')}, {args.get('y')})"
                                    logger.info(f"   🖱️  点击: {element}")
                                elif action == 'batch':
                                    actions = args.get('actions', [])
                                    logger.info(f"   📦 Batch: {len(actions)} 个动作")
                                elif action == 'type_text':
                                    text = args.get('text', '')[:30]
                                    logger.info(f"   ⌨️  输入: {text}...")
                                elif action == 'screenshot':
                                    region = args.get('region', 'full')
                                    logger.info(f"   📸 截图: {region}")
                            elif tool_name in ['get_current_environment', 'get_active_application']:
                                logger.info(f"   🔍 {tool_name}")
                    
                    report.steps.append(step)
                    
                    if verbose and step.tool_calls:
                        logger.info(f"\n📍 Step {step.step_number}: {step.step_name} ({step.duration_ms:.0f}ms)")
                
                last_step_count = len(steps)
                
            except Exception as e:
                logger.debug(f"监控错误: {e}")
    
    monitor_task = asyncio.create_task(monitor())
    
    # 运行测试
    try:
        logger.info("🚀 启动 Agent...")
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        logger.info("✅ Agent 执行完成")
        
    except asyncio.TimeoutError:
        logger.error(f"❌ 执行超时 (>{MAX_EXECUTION_TIME}s)")
        report.errors.append(f"Timeout after {MAX_EXECUTION_TIME}s")
        
    except Exception as e:
        logger.error(f"❌ 执行异常: {e}")
        report.errors.append(str(e))
        traceback.print_exc()
    
    # 停止监控
    monitor_task.cancel()
    try:
        await monitor_task
    except:
        pass
    
    # 完成报告
    report.finalize()
    
    return report


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='真实场景测试')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    parser.add_argument('--save', '-s', type=str, help='保存报告到文件')
    
    args = parser.parse_args()
    
    # 初始化环境
    if not await init_env():
        logger.error("❌ 环境初始化失败")
        return
    
    # 运行测试
    report = await run_real_scenario_test(verbose=args.verbose)
    
    # 打印报告
    report.print_report()
    
    # 保存报告
    if args.save:
        report_data = {
            'scenario_name': report.scenario_name,
            'user_input': report.user_input,
            'start_time': report.start_time.isoformat(),
            'end_time': report.end_time.isoformat() if report.end_time else None,
            'duration_seconds': report.duration_seconds,
            'metrics': {
                'total_tool_calls': report.total_tool_calls,
                'screenshot_count': report.screenshot_count,
                'key_press_count': report.key_press_count,
                'click_count': report.click_count,
                'batch_count': report.batch_count,
                'shortcut_count': report.shortcut_count,
                'shortcut_usage_rate': report.shortcut_usage_rate,
                'keyboard_vs_mouse_ratio': report.keyboard_vs_mouse_ratio,
            },
            'steps': [
                {
                    'step_number': s.step_number,
                    'step_name': s.step_name,
                    'duration_ms': s.duration_ms,
                    'tool_calls': s.tool_calls,
                    'shortcuts': s.get_shortcuts_used(),
                }
                for s in report.steps
            ],
            'errors': report.errors,
        }
        
        with open(args.save, 'w') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        logger.info(f"📄 报告已保存: {args.save}")
    
    # Cleanup memory container
    global _memory_container
    if '_memory_container' in globals():
        try:
            await _memory_container.shutdown()
        except:
            pass
    
    # 返回退出码
    return 0 if not report.errors else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
