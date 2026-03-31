#!/usr/bin/env python3
"""
Agent 执行过程分析工具

用于分析真实场景下 Agent 的执行过程，验证优化效果：
1. 键盘快捷键使用
2. Batch 模式使用
3. 部分截图使用
4. 跨应用切换效率

用法:
    # 分析正在运行的 Agent
    python analyze_agent_execution.py --thread-id <thread_id>
    
    # 分析历史执行记录
    python analyze_agent_execution.py --file /path/to/execution_log.json
    
    # 实时监控
    python analyze_agent_execution.py --watch --thread-id <thread_id>
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict


@dataclass
class ToolCall:
    """工具调用记录"""
    name: str
    arguments: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def action(self) -> str:
        """获取 action 参数"""
        return self.arguments.get('action', '')
    
    @property
    def is_shortcut(self) -> bool:
        """是否是快捷键调用"""
        if self.name == 'desktop_control' and self.action == 'key_press':
            key = self.arguments.get('key', '')
            return 'cmd+' in key or 'ctrl+' in key or 'alt+' in key
        return False
    
    @property
    def shortcut_key(self) -> str:
        """获取快捷键值"""
        if self.action == 'key_press':
            return self.arguments.get('key', '')
        return ''


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_number: int
    name: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    duration_ms: float = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def get_shortcuts(self) -> List[str]:
        """获取步骤中使用的快捷键"""
        return [call.shortcut_key for call in self.tool_calls if call.is_shortcut]
    
    def get_actions(self) -> List[str]:
        """获取步骤中的 actions"""
        actions = []
        for call in self.tool_calls:
            if call.name == 'desktop_control' and call.action:
                actions.append(call.action)
        return actions


@dataclass 
class ExecutionAnalysis:
    """执行分析结果"""
    thread_id: str
    scenario: str
    steps: List[ExecutionStep] = field(default_factory=list)
    
    # 统计
    total_tool_calls: int = 0
    desktop_control_calls: int = 0
    screenshot_count: int = 0
    key_press_count: int = 0
    click_count: int = 0
    batch_count: int = 0
    type_text_count: int = 0
    shortcut_count: int = 0
    
    # 优化指标
    shortcuts_used: List[str] = field(default_factory=list)
    apps_switched: List[str] = field(default_factory=list)
    
    def analyze(self):
        """分析执行数据"""
        for step in self.steps:
            for call in step.tool_calls:
                self.total_tool_calls += 1
                
                if call.name == 'desktop_control':
                    self.desktop_control_calls += 1
                    action = call.action
                    
                    if action == 'screenshot':
                        self.screenshot_count += 1
                    elif action == 'key_press':
                        self.key_press_count += 1
                        if call.is_shortcut:
                            self.shortcut_count += 1
                            self.shortcuts_used.append(call.shortcut_key)
                    elif action == 'click':
                        self.click_count += 1
                    elif action == 'batch':
                        self.batch_count += 1
                    elif action == 'type_text':
                        self.type_text_count += 1
    
    @property
    def shortcut_usage_rate(self) -> float:
        """快捷键使用率"""
        if self.key_press_count > 0:
            return self.shortcut_count / self.key_press_count
        return 0
    
    @property
    def keyboard_ratio(self) -> float:
        """键盘操作比例"""
        total = self.key_press_count + self.click_count
        if total > 0:
            return self.key_press_count / total
        return 0
    
    @property
    def total_duration_seconds(self) -> float:
        """总执行时间"""
        if not self.steps:
            return 0
        return sum(s.duration_ms for s in self.steps) / 1000
    
    def print_analysis(self):
        """打印分析报告"""
        print("\n" + "="*80)
        print("🎯 Agent 执行过程分析报告")
        print("="*80)
        print(f"\n线程 ID: {self.thread_id}")
        print(f"场景: {self.scenario}")
        print(f"总步骤数: {len(self.steps)}")
        print(f"总耗时: {self.total_duration_seconds:.1f}s")
        
        print(f"\n📊 工具调用统计:")
        print(f"  总工具调用: {self.total_tool_calls} 次")
        print(f"  Desktop Control: {self.desktop_control_calls} 次")
        print(f"  ├─ 截图: {self.screenshot_count} 次")
        print(f"  ├─ 键盘按键: {self.key_press_count} 次")
        print(f"  ├─ 鼠标点击: {self.click_count} 次")
        print(f"  ├─ Batch: {self.batch_count} 次")
        print(f"  └─ 文本输入: {self.type_text_count} 次")
        
        print(f"\n🚀 优化效果分析:")
        print(f"  快捷键使用: {self.shortcut_count} 次 ({len(set(self.shortcuts_used))} 种)")
        print(f"  快捷键列表: {list(set(self.shortcuts_used))}")
        print(f"  快捷键使用率: {self.shortcut_usage_rate*100:.1f}%")
        print(f"  键盘/鼠标比例: {self.keyboard_ratio*100:.1f}% (键盘占比)")
        
        # 评分
        print(f"\n📈 优化评分:")
        score = 0
        max_score = 100
        
        # 快捷键使用 (40分)
        if self.shortcut_usage_rate >= 0.8:
            print(f"  ✅ 快捷键使用优秀: +40分")
            score += 40
        elif self.shortcut_usage_rate >= 0.5:
            print(f"  ⚠️  快捷键使用良好: +25分")
            score += 25
        elif self.shortcut_usage_rate > 0:
            print(f"  ⚠️  快捷键使用较少: +10分")
            score += 10
        else:
            print(f"  ❌ 未使用快捷键: +0分")
        
        # Batch 使用 (30分)
        if self.batch_count >= 2:
            print(f"  ✅ Batch 使用优秀: +30分")
            score += 30
        elif self.batch_count == 1:
            print(f"  ⚠️  Batch 使用一次: +15分")
            score += 15
        else:
            print(f"  ❌ 未使用 Batch: +0分")
        
        # 键盘优先 (30分)
        if self.keyboard_ratio >= 0.7:
            print(f"  ✅ 键盘优先: +30分")
            score += 30
        elif self.keyboard_ratio >= 0.5:
            print(f"  ⚠️  键盘使用较多: +20分")
            score += 20
        elif self.keyboard_ratio >= 0.3:
            print(f"  ⚠️  键盘使用一般: +10分")
            score += 10
        else:
            print(f"  ❌ 鼠标使用过多: +0分")
        
        print(f"\n  总分: {score}/{max_score}")
        
        if score >= 80:
            print(f"  🌟 优秀! Agent 很好地使用了速度优化")
        elif score >= 60:
            print(f"  ✅ 良好，仍有改进空间")
        else:
            print(f"  ⚠️  需要优化，建议检查提示词和工具定义")
        
        # 详细步骤
        print(f"\n📍 详细执行步骤:")
        print("-" * 80)
        for step in self.steps:
            shortcuts = step.get_shortcuts()
            actions = step.get_actions()
            
            shortcut_info = f" [快捷键: {', '.join(shortcuts)}]" if shortcuts else ""
            actions_str = ' → '.join(actions) if actions else "(无工具调用)"
            
            print(f"  Step {step.step_number}: {step.name}")
            print(f"    耗时: {step.duration_ms:.0f}ms | 动作: {actions_str}{shortcut_info}")
        
        print("\n" + "="*80)


def analyze_from_activity(activity_data: Dict) -> ExecutionAnalysis:
    """从 activity_monitor 数据创建分析"""
    thread_id = activity_data.get('thread_id', 'unknown')
    
    # 尝试从消息中提取场景
    scenario = "未知场景"
    messages = activity_data.get('messages', [])
    for msg in messages:
        if msg.get('type') == 'human':
            scenario = msg.get('content', '')[:50]
            break
    
    analysis = ExecutionAnalysis(thread_id=thread_id, scenario=scenario)
    
    steps_data = activity_data.get('steps', [])
    for i, step_data in enumerate(steps_data, 1):
        step = ExecutionStep(
            step_number=i,
            name=step_data.get('name', f'Step {i}'),
            duration_ms=step_data.get('duration_ms', 0)
        )
        
        tool_calls = step_data.get('tool_calls', [])
        for call_data in tool_calls:
            tool_call = ToolCall(
                name=call_data.get('name', ''),
                arguments=call_data.get('arguments', {})
            )
            step.tool_calls.append(tool_call)
        
        analysis.steps.append(step)
    
    analysis.analyze()
    return analysis


def analyze_from_log(log_file: str) -> List[ExecutionAnalysis]:
    """从日志文件分析"""
    analyses = []
    
    with open(log_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                if 'steps' in data or 'tool_calls' in data:
                    analysis = analyze_from_activity(data)
                    analyses.append(analysis)
            except json.JSONDecodeError:
                continue
    
    return analyses


async def watch_thread(thread_id: str, interval: int = 2):
    """实时监控线程"""
    import sys
    sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')
    
    try:
        from app.core.monitoring.activity import activity_monitor
        
        print(f"🔍 开始监控线程: {thread_id}")
        print(f"   刷新间隔: {interval}s (按 Ctrl+C 停止)")
        print("-" * 80)
        
        last_step_count = 0
        
        while True:
            try:
                activity = await activity_monitor.get_activity(thread_id)
                if activity:
                    analysis = analyze_from_activity(activity)
                    
                    if len(analysis.steps) > last_step_count:
                        # 有新步骤
                        for step in analysis.steps[last_step_count:]:
                            shortcuts = step.get_shortcuts()
                            actions = step.get_actions()
                            
                            shortcut_info = f" [快捷键: {', '.join(shortcuts)}]" if shortcuts else ""
                            actions_str = ' → '.join(actions) if actions else "(无工具调用)"
                            
                            print(f"  Step {step.step_number}: {step.name}")
                            print(f"    动作: {actions_str}{shortcut_info}")
                        
                        last_step_count = len(analysis.steps)
                
                await asyncio.sleep(interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"监控错误: {e}")
                await asyncio.sleep(interval)
        
        print("\n" + "="*80)
        print("监控结束")
        
        # 打印最终分析
        activity = await activity_monitor.get_activity(thread_id)
        if activity:
            analysis = analyze_from_activity(activity)
            analysis.print_analysis()
        
    except ImportError:
        print("❌ 无法导入 activity_monitor，请确保在 backend 目录下运行")


def main():
    parser = argparse.ArgumentParser(description='Agent 执行过程分析')
    parser.add_argument('--thread-id', '-t', type=str, help='线程 ID')
    parser.add_argument('--file', '-f', type=str, help='日志文件路径')
    parser.add_argument('--watch', '-w', action='store_true', help='实时监控模式')
    parser.add_argument('--interval', '-i', type=int, default=2, help='监控刷新间隔(秒)')
    
    args = parser.parse_args()
    
    if args.watch and args.thread_id:
        import asyncio
        asyncio.run(watch_thread(args.thread_id, args.interval))
    
    elif args.thread_id:
        # 单次分析
        import asyncio
        import sys
        sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')
        
        try:
            from app.core.monitoring.activity import activity_monitor
            
            async def analyze_once():
                activity = await activity_monitor.get_activity(args.thread_id)
                if activity:
                    analysis = analyze_from_activity(activity)
                    analysis.print_analysis()
                else:
                    print(f"❌ 未找到线程 {args.thread_id} 的数据")
            
            asyncio.run(analyze_once())
            
        except ImportError:
            print("❌ 无法导入 activity_monitor")
    
    elif args.file:
        # 从文件分析
        analyses = analyze_from_log(args.file)
        for analysis in analyses:
            analysis.print_analysis()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
