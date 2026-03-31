"""
批量测试运行器 - 持续监控与自动重试

功能：
1. 批量运行多个场景的测试
2. 记录所有异常
3. 支持修正后自动重试
4. 生成汇总报告

使用：
    # 批量运行所有场景
    python batch_runner.py --all --max-rounds 3
    
    # 运行特定场景并自动重试失败的
    python batch_runner.py --scenario code_generation,debugging --retry
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop')
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from test_executor import DialogueTestExecutor, TestStatus, AnomalyType
from test_dialogue_scenarios import ALL_SCENARIOS


class BatchTestRunner:
    """批量测试运行器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[Dict] = []
        self.anomaly_summary: Dict[str, List] = {}
        
    async def run_batch(
        self,
        scenarios: List[str],
        max_rounds: int = 3,
        auto_retry: bool = False,
        max_retries: int = 2
    ) -> Dict:
        """
        批量运行测试
        
        Args:
            scenarios: 场景名称列表
            max_rounds: 每场景最大轮次
            auto_retry: 失败时自动重试
            max_retries: 最大重试次数
        """
        print(f"\n{'='*70}")
        print(f"批量测试开始")
        print(f"场景数: {len(scenarios)}")
        print(f"每场景轮次: {max_rounds}")
        print(f"自动重试: {auto_retry}")
        print(f"{'='*70}\n")
        
        start_time = datetime.now()
        
        for i, scenario_name in enumerate(scenarios, 1):
            print(f"\n[{i}/{len(scenarios)}] 正在测试场景: {scenario_name}")
            print("-" * 70)
            
            # 获取话术
            scenario_data = ALL_SCENARIOS.get(scenario_name, [])
            if not scenario_data:
                print(f"⚠️  场景 {scenario_name} 不存在，跳过")
                continue
            
            # 提取话术
            if scenario_name == 'multi_turn':
                utterances = [s["cn"] for s in scenario_data[0]]
            else:
                utterances = [s["cn"] for s in scenario_data]
            
            # 执行测试（带重试）
            session = await self._run_with_retry(
                scenario_name=scenario_name,
                utterances=utterances,
                max_rounds=max_rounds,
                auto_retry=auto_retry,
                max_retries=max_retries
            )
            
            # 记录结果
            result = {
                "scenario": scenario_name,
                "session_id": session.session_id,
                "status": session.status.value,
                "rounds": len(session.rounds),
                "anomalies": len(session.anomalies),
                "total_tokens": session.total_tokens,
                "total_cost": session.total_cost,
                "interrupted": session.interrupted_at is not None,
                "interrupt_reason": session.interrupt_reason,
            }
            self.results.append(result)
            
            # 汇总异常
            for anomaly in session.anomalies:
                anomaly_type = anomaly["type"]
                if anomaly_type not in self.anomaly_summary:
                    self.anomaly_summary[anomaly_type] = []
                self.anomaly_summary[anomaly_type].append({
                    "scenario": scenario_name,
                    "round": anomaly["round"],
                    "detail": anomaly["detail"]
                })
            
            # 显示简要结果
            status_icon = "✅" if session.status == TestStatus.SUCCESS else "❌"
            print(f"{status_icon} {scenario_name}: {session.status.value}, "
                  f"{len(session.anomalies)} 个异常, "
                  f"${session.total_cost:.4f}")
        
        # 生成汇总
        duration = (datetime.now() - start_time).total_seconds()
        summary = self._generate_summary(duration)
        
        return summary
    
    async def _run_with_retry(
        self,
        scenario_name: str,
        utterances: List[str],
        max_rounds: int,
        auto_retry: bool,
        max_retries: int
    ):
        """带重试的测试执行"""
        executor = DialogueTestExecutor(base_url=self.base_url)
        
        for attempt in range(max_retries + 1):
            try:
                session = await executor.execute_scenario(
                    scenario_name=scenario_name,
                    utterances=utterances,
                    max_rounds=max_rounds,
                    auto_continue=True  # 批量模式下自动继续
                )
                
                # 检查是否需要重试
                if session.status != TestStatus.SUCCESS and auto_retry and attempt < max_retries:
                    print(f"  ⚠️  测试未通过，第 {attempt + 1} 次重试...")
                    await asyncio.sleep(2)  # 等待后重试
                    continue
                
                return session
                
            except Exception as e:
                print(f"  ❌ 执行异常: {e}")
                if attempt < max_retries:
                    print(f"  等待后重试...")
                    await asyncio.sleep(5)
                else:
                    # 创建失败记录
                    from test_executor import TestSession
                    session = TestSession(
                        session_id=f"{scenario_name}_failed",
                        scenario_name=scenario_name,
                        scenario_desc="执行失败",
                        start_time=0
                    )
                    session.status = TestStatus.ERROR
                    return session
            finally:
                await executor.close()
        
        return session
    
    def _generate_summary(self, duration: float) -> Dict:
        """生成测试汇总"""
        total = len(self.results)
        success = sum(1 for r in self.results if r["status"] == "success")
        failed = total - success
        total_cost = sum(r["total_cost"] for r in self.results)
        total_anomalies = sum(r["anomalies"] for r in self.results)
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "total_scenarios": total,
            "success": success,
            "failed": failed,
            "success_rate": success / total if total > 0 else 0,
            "total_cost_usd": total_cost,
            "total_anomalies": total_anomalies,
            "anomaly_breakdown": {
                anomaly_type: len(items)
                for anomaly_type, items in self.anomaly_summary.items()
            },
            "results": self.results,
            "anomaly_details": self.anomaly_summary
        }
        
        # 保存汇总报告
        report_file = f"tests/monitoring/reports/batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 打印汇总
        print(f"\n{'='*70}")
        print("批量测试汇总")
        print(f"{'='*70}")
        print(f"总场景数: {total}")
        print(f"成功: {success} ({summary['success_rate']:.1%})")
        print(f"失败: {failed}")
        print(f"总耗时: {duration:.1f}s")
        print(f"总成本: ${total_cost:.4f}")
        print(f"总异常: {total_anomalies}")
        print(f"\n异常分布:")
        for anomaly_type, count in summary["anomaly_breakdown"].items():
            print(f"  - {anomaly_type}: {count}")
        print(f"\n📄 详细报告: {report_file}")
        print(f"{'='*70}\n")
        
        return summary


def interactive_fix_and_retry():
    """
    交互式修正与重试工具
    
    当测试发现异常时，可以：
    1. 查看异常详情
    2. 修正问题（如修改代码、调整配置）
    3. 重新运行失败的测试
    """
    print("\n" + "="*70)
    print("交互式修正与重试")
    print("="*70)
    
    # 查找最近的报告
    reports_dir = Path("tests/monitoring/reports")
    reports = sorted(reports_dir.glob("batch_summary_*.json"), reverse=True)
    
    if not reports:
        print("没有找到测试报告")
        return
    
    # 加载最近的报告
    latest_report = reports[0]
    print(f"加载报告: {latest_report}")
    
    with open(latest_report, 'r') as f:
        summary = json.load(f)
    
    # 显示失败的场景
    failed_scenarios = [r for r in summary["results"] if r["status"] != "success"]
    
    if not failed_scenarios:
        print("✅ 所有测试都已通过，无需修正")
        return
    
    print(f"\n发现 {len(failed_scenarios)} 个失败的场景:")
    for i, scenario in enumerate(failed_scenarios, 1):
        print(f"  {i}. {scenario['scenario']}: {scenario['interrupt_reason']}")
    
    print("\n选项:")
    print("  [1-n] 查看特定场景的详细异常")
    print("  [r]   重新运行所有失败的场景")
    print("  [q]   退出")
    
    choice = input("\n选择: ").strip()
    
    if choice == 'r':
        # 重新运行失败的场景
        scenarios_to_retry = [s["scenario"] for s in failed_scenarios]
        print(f"\n重新运行: {', '.join(scenarios_to_retry)}")
        
        # 这里可以添加自动修正逻辑
        input("请修正问题后按 Enter 继续...")
        
        return scenarios_to_retry
        
    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(failed_scenarios):
            scenario = failed_scenarios[idx]
            print(f"\n场景: {scenario['scenario']}")
            print(f"状态: {scenario['status']}")
            print(f"中断原因: {scenario['interrupt_reason']}")
            
            # 查找详细异常
            anomaly_details = summary.get("anomaly_details", {})
            for anomaly_type, items in anomaly_details.items():
                for item in items:
                    if item["scenario"] == scenario["scenario"]:
                        print(f"\n异常 [{anomaly_type}]:")
                        print(f"  轮次: {item['round']}")
                        print(f"  详情: {item['detail']}")
    
    return None


async def main():
    parser = argparse.ArgumentParser(description='批量测试运行器')
    parser.add_argument('--all', action='store_true',
                       help='运行所有场景')
    parser.add_argument('--scenarios', type=str,
                       help='指定场景，逗号分隔，如: code_generation,debugging')
    parser.add_argument('--max-rounds', type=int, default=3,
                       help='每场景最大轮次')
    parser.add_argument('--retry', action='store_true',
                       help='自动重试失败的测试')
    parser.add_argument('--max-retries', type=int, default=2,
                       help='最大重试次数')
    parser.add_argument('--base-url', type=str, default='http://localhost:8000')
    parser.add_argument('--interactive', action='store_true',
                       help='交互式修正与重试模式')
    
    args = parser.parse_args()
    
    # 交互模式
    if args.interactive:
        scenarios_to_retry = interactive_fix_and_retry()
        if scenarios_to_retry:
            runner = BatchTestRunner(base_url=args.base_url)
            await runner.run_batch(
                scenarios=scenarios_to_retry,
                max_rounds=args.max_rounds,
                auto_retry=args.retry,
                max_retries=args.max_retries
            )
        return
    
    # 确定要运行的场景
    if args.all:
        # 排除一些不适合自动测试的场景
        exclude = ['dangerous_operation', 'edge_case']
        scenarios = [s for s in ALL_SCENARIOS.keys() if s not in exclude]
    elif args.scenarios:
        scenarios = [s.strip() for s in args.scenarios.split(',')]
    else:
        # 默认运行核心场景
        scenarios = ['code_generation', 'code_optimization', 'knowledge_query']
    
    # 运行批量测试
    runner = BatchTestRunner(base_url=args.base_url)
    summary = await runner.run_batch(
        scenarios=scenarios,
        max_rounds=args.max_rounds,
        auto_retry=args.retry,
        max_retries=args.max_retries
    )
    
    # 如果有失败，提示可以使用交互模式
    if summary['failed'] > 0:
        print(f"\n💡 提示: 使用 --interactive 模式可以查看详情并重新测试")
        print(f"   python batch_runner.py --interactive")


if __name__ == "__main__":
    asyncio.run(main())
