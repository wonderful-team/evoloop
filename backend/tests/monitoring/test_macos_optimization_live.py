#!/usr/bin/env python3
"""
macOS 速度优化实时测试（与真实 Agent 集成）

参考 test_with_scenarios.py 的架构，使用真实 Agent 执行测试

用法:
    # 基础测试
    python test_macos_optimization_live.py
    
    # 测试指定场景
    python test_macos_optimization_live.py --scenario wechat_message
    
    # 生成对比报告
    python test_macos_optimization_live.py --report
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("macos_optimization_live")

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
env_path = '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

MAX_EXECUTION_TIME = 5 * 60  # 5分钟超时

# 测试场景话术
TEST_SCENARIOS = {
    "wechat_message": {
        "cn": "给文件传输助手发送消息'测试消息'",
        "en": "Send message 'test message' to file transfer assistant",
        "description": "微信发送消息 - 验证快捷键和 batch 优化",
        "expected_shortcuts": ["cmd+return"],
        "expected_batch": True,
    },
    "chrome_search": {
        "cn": "在 Chrome 中搜索 'Python tutorial'",
        "en": "Search for 'Python tutorial' in Chrome",
        "description": "Chrome 搜索 - 验证快捷键链优化",
        "expected_shortcuts": ["cmd+l", "cmd+a"],
        "expected_batch": True,
    },
    "copy_paste": {
        "cn": "复制当前选中的文本并粘贴",
        "en": "Copy selected text and paste",
        "description": "复制粘贴 - 验证快捷键优先",
        "expected_shortcuts": ["cmd+c", "cmd+v"],
        "expected_batch": False,
    },
    "close_window": {
        "cn": "关闭当前窗口",
        "en": "Close current window",
        "description": "关闭窗口 - 验证 cmd+w 快捷键",
        "expected_shortcuts": ["cmd+w"],
        "expected_batch": False,
    },
}


class OptimizationMetrics:
    """优化指标收集器"""
    
    def __init__(self):
        self.metrics = {
            "desktop_control_calls": 0,
            "screenshot_calls": 0,
            "shortcut_calls": 0,
            "batch_calls": 0,
            "key_press_calls": 0,
            "click_calls": 0,
            "tool_durations": [],
            "shortcut_types": [],
        }
    
    def record_tool_call(self, tool_name: str, params: Dict, duration_ms: float):
        """记录工具调用"""
        self.metrics["desktop_control_calls"] += 1
        self.metrics["tool_durations"].append(duration_ms)
        
        if tool_name == "desktop_control":
            action = params.get("action", "")
            
            if action == "screenshot":
                self.metrics["screenshot_calls"] += 1
            
            elif action == "key_press":
                self.metrics["key_press_calls"] += 1
                key = params.get("key", "")
                if "cmd+" in key or "ctrl+" in key:
                    self.metrics["shortcut_calls"] += 1
                    self.metrics["shortcut_types"].append(key)
            
            elif action == "click":
                self.metrics["click_calls"] += 1
            
            elif action == "batch":
                self.metrics["batch_calls"] += 1
    
    def get_summary(self) -> Dict:
        """获取指标摘要"""
        import statistics
        
        durations = self.metrics["tool_durations"]
        return {
            "total_calls": self.metrics["desktop_control_calls"],
            "screenshot_calls": self.metrics["screenshot_calls"],
            "shortcut_calls": self.metrics["shortcut_calls"],
            "batch_calls": self.metrics["batch_calls"],
            "key_press_calls": self.metrics["key_press_calls"],
            "click_calls": self.metrics["click_calls"],
            "avg_tool_duration_ms": statistics.mean(durations) if durations else 0,
            "unique_shortcuts": list(set(self.metrics["shortcut_types"])),
            "optimization_indicators": {
                "shortcut_usage_rate": self.metrics["shortcut_calls"] / max(self.metrics["key_press_calls"], 1),
                "screenshot_reduction": "N/A (need baseline)",
            }
        }


async def init_env():
    """初始化环境（参考 test_with_scenarios.py）"""
    logger.info("🔧 初始化测试环境...")
    
    try:
        # 导入必要的模块
        from app.core.engine.graph.builder import GraphBuilder
        from app.infrastructure.database.sql.database import init_db
        from app.core.memory import MemoryContainer, MemoryConfig
        
        # 初始化数据库
        await init_db()
        logger.info("✅ 数据库初始化完成")
        
        # 初始化 Memory using MemoryContainer
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        # Store container for cleanup
        global _memory_container
        _memory_container = container
        logger.info("✅ Memory 初始化完成")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 环境初始化失败: {e}")
        return False


async def run_optimization_test(scenario_id: str, scenario: Dict, test_id: int) -> Dict:
    """
    运行单个优化测试
    
    参考 test_with_scenarios.py 的 run_single_test 结构
    """
    from app.core.engine.background_agent import run_agent_background
    from app.core.monitoring.activity import activity_monitor
    
    user_input = scenario["cn"]
    thread_id = f"macos-opt-{datetime.now().strftime('%H%M%S')}-{test_id}"
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🧪 [{test_id}] {scenario['description']}")
    logger.info(f"   输入: {user_input}")
    logger.info(f"   期望快捷键: {scenario['expected_shortcuts']}")
    logger.info(f"   期望 Batch: {scenario['expected_batch']}")
    logger.info(f"{'='*60}")
    
    inputs = {
        "messages": [{"type": "human", "content": user_input}],
        "project_id": 1,
        "goal": user_input[:50],
        "is_retry": False
    }
    
    metrics = OptimizationMetrics()
    start_time = datetime.now()
    
    # 后台监控 - 分析工具调用
    async def monitor():
        """监控工具调用，收集优化指标"""
        last_step_count = 0
        
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
                
                # 只分析新步骤
                for step in steps[last_step_count:]:
                    step_name = step.get('name', '')
                    step_duration = step.get('duration_ms', 0)
                    
                    # 分析 tool_calls
                    tool_calls = step.get('tool_calls', [])
                    for call in tool_calls:
                        tool_name = call.get('name', '')
                        tool_params = call.get('arguments', {})
                        
                        # 记录到 metrics
                        metrics.record_tool_call(tool_name, tool_params, step_duration)
                        
                        # 检测快捷键使用
                        if tool_name == "desktop_control" and tool_params.get("action") == "key_press":
                            key = tool_params.get("key", "")
                            if "cmd+" in key:
                                logger.info(f"   🚀 检测到快捷键使用: {key}")
                        
                        # 检测 batch 使用
                        if tool_name == "desktop_control" and tool_params.get("action") == "batch":
                            actions = tool_params.get("actions", [])
                            logger.info(f"   📦 检测到 Batch 模式: {len(actions)} 个动作")
                
                last_step_count = len(steps)
                
            except Exception as e:
                logger.debug(f"监控错误: {e}")
    
    monitor_task = asyncio.create_task(monitor())
    
    # 运行测试
    test_error = None
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=MAX_EXECUTION_TIME
        )
        status = "success"
        
    except asyncio.TimeoutError:
        status = "timeout"
        test_error = f"Timeout after {MAX_EXECUTION_TIME}s"
        
    except Exception as e:
        status = f"error: {type(e).__name__}"
        test_error = str(e)
        logger.error(f"❌ 测试异常:\n{traceback.format_exc()}")
    
    # 停止监控
    monitor_task.cancel()
    try:
        await monitor_task
    except:
        pass
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # 获取指标摘要
    metrics_summary = metrics.get_summary()
    
    # 验证优化是否生效
    optimization_checks = {
        "shortcut_used": metrics_summary["shortcut_calls"] > 0,
        "batch_used": metrics_summary["batch_calls"] > 0,
        "expected_shortcuts_found": all(
            s in metrics_summary["unique_shortcuts"]
            for s in scenario["expected_shortcuts"]
        ),
    }
    
    logger.info(f"\n📊 测试结果: {status} | 耗时: {elapsed:.1f}s")
    logger.info(f"   工具调用: {metrics_summary['total_calls']} 次")
    logger.info(f"   截图: {metrics_summary['screenshot_calls']} 次")
    logger.info(f"   快捷键: {metrics_summary['shortcut_calls']} 次")
    logger.info(f"   Batch: {metrics_summary['batch_calls']} 次")
    logger.info(f"   优化检查: {optimization_checks}")
    
    return {
        "test_id": test_id,
        "scenario": scenario_id,
        "input": user_input,
        "status": status,
        "elapsed_s": elapsed,
        "metrics": metrics_summary,
        "optimization_checks": optimization_checks,
        "error": test_error,
    }


async def run_all_tests(max_tests: int = None, scenario_filter: str = None) -> List[Dict]:
    """运行所有测试"""
    # 初始化环境
    if not await init_env():
        logger.error("❌ 环境初始化失败，测试中止")
        return []
    
    results = []
    test_id = 1
    
    scenarios = TEST_SCENARIOS
    if scenario_filter and scenario_filter in scenarios:
        scenarios = {scenario_filter: scenarios[scenario_filter]}
    
    for scenario_id, scenario in list(scenarios.items())[:max_tests]:
        result = await run_optimization_test(scenario_id, scenario, test_id)
        results.append(result)
        test_id += 1
        
        # 测试间间隔
        await asyncio.sleep(2)
    
    return results


def generate_report(results: List[Dict]) -> Dict:
    """生成测试报告"""
    if not results:
        return {"error": "No results"}
    
    import statistics
    
    # 按场景分组
    by_scenario = defaultdict(list)
    for r in results:
        by_scenario[r["scenario"]].append(r)
    
    # 场景统计
    scenario_stats = []
    for scenario_id, scenario_results in by_scenario.items():
        times = [r["elapsed_s"] for r in scenario_results]
        shortcut_rate = sum(1 for r in scenario_results if r["optimization_checks"]["shortcut_used"]) / len(scenario_results)
        batch_rate = sum(1 for r in scenario_results if r["optimization_checks"]["batch_used"]) / len(scenario_results)
        
        scenario_stats.append({
            "scenario": scenario_id,
            "count": len(scenario_results),
            "avg_time_s": statistics.mean(times),
            "success_rate": sum(1 for r in scenario_results if r["status"] == "success") / len(scenario_results),
            "shortcut_usage_rate": shortcut_rate,
            "batch_usage_rate": batch_rate,
        })
    
    # 总体统计
    all_times = [r["elapsed_s"] for r in results]
    success_count = sum(1 for r in results if r["status"] == "success")
    
    return {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(results),
        "success_rate": success_count / len(results),
        "overall_avg_time_s": statistics.mean(all_times),
        "scenario_stats": scenario_stats,
        "detailed_results": results,
    }


def print_report(report: Dict):
    """打印报告"""
    print("\n" + "="*70)
    print("📊 macOS 速度优化测试报告")
    print("="*70)
    
    print(f"\n总体统计:")
    print(f"  测试数: {report['total_tests']}")
    print(f"  成功率: {report['success_rate']*100:.0f}%")
    print(f"  平均耗时: {report['overall_avg_time_s']:.1f}s")
    
    print(f"\n场景统计:")
    for s in report['scenario_stats']:
        print(f"\n  {s['scenario']}:")
        print(f"    测试数: {s['count']}")
        print(f"    平均耗时: {s['avg_time_s']:.1f}s")
        print(f"    成功率: {s['success_rate']*100:.0f}%")
        print(f"    快捷键使用率: {s['shortcut_usage_rate']*100:.0f}%")
        print(f"    Batch 使用率: {s['batch_usage_rate']*100:.0f}%")
    
    # 优化效果评估
    print(f"\n优化效果评估:")
    import statistics
    avg_shortcut_rate = statistics.mean([s['shortcut_usage_rate'] for s in report['scenario_stats']])
    avg_batch_rate = statistics.mean([s['batch_usage_rate'] for s in report['scenario_stats']])
    
    if avg_shortcut_rate > 0.5:
        print(f"  ✅ 快捷键优化生效: {avg_shortcut_rate*100:.0f}% 的场景使用了快捷键")
    else:
        print(f"  ⚠️  快捷键使用率偏低: {avg_shortcut_rate*100:.0f}%")
    
    if avg_batch_rate > 0.3:
        print(f"  ✅ Batch 优化生效: {avg_batch_rate*100:.0f}% 的场景使用了 Batch")
    else:
        print(f"  ⚠️  Batch 使用率偏低: {avg_batch_rate*100:.0f}%")
    
    print("\n" + "="*70)
    
    # 保存报告
    report_file = f"/tmp/macos_optimization_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"📄 详细报告: {report_file}")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='macOS 优化实时测试')
    parser.add_argument('--max', type=int, default=None, help='最大测试数')
    parser.add_argument('--scenario', type=str, default=None, help='指定场景')
    parser.add_argument('--report', action='store_true', help='生成详细报告')
    
    args = parser.parse_args()
    
    # 运行测试
    results = await run_all_tests(
        max_tests=args.max,
        scenario_filter=args.scenario
    )
    
    if results:
        # 生成并打印报告
        report = generate_report(results)
        print_report(report)
    else:
        logger.error("❌ 没有测试结果")
    
    # Cleanup memory container
    global _memory_container
    if '_memory_container' in globals():
        try:
            await _memory_container.shutdown()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
