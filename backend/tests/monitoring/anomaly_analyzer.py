"""
异常分析与根因定位工具

功能：
1. 分析测试报告中的异常
2. 自动分类和统计
3. 提供修复建议
4. 追踪异常趋势

使用：
    python anomaly_analyzer.py --report tests/monitoring/reports/xxx.json
    python anomaly_analyzer.py --trend --days 7
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any
import re

sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')
from tests.monitoring.test_executor import AnomalyType


class AnomalyAnalyzer:
    """异常分析器"""
    
    # 异常类型 -> 修复建议映射
    FIX_SUGGESTIONS = {
        "timeout": [
            "检查 LLM API 响应时间",
            "增加 timeout 配置",
            "考虑使用更快的模型",
            "检查网络连接稳定性"
        ],
        "error_response": [
            "查看后端错误日志",
            "检查数据库连接",
            "验证 API 参数格式",
            "检查模型调用配额"
        ],
        "empty_response": [
            "检查 Prompt 是否过短或模糊",
            "增加输入上下文",
            "检查模型输出过滤器",
            "验证消息格式是否正确"
        ],
        "repetition": [
            "增加 temperature 参数",
            "添加多样性提示",
            "检查是否陷入循环",
            "重置对话上下文"
        ],
        "infinite_loop": [
            "检查 ReAct 循环终止条件",
            "减少 max_steps 限制",
            "添加循环检测逻辑",
            "优化工具调用逻辑"
        ],
        "hallucination": [
            "增加事实检查步骤",
            "使用检索增强生成 (RAG)",
            "降低 temperature",
            "添加引用来源要求"
        ],
        "tool_failure": [
            "检查工具参数格式",
            "验证工具依赖是否安装",
            "添加工具调用重试逻辑",
            "检查权限和路径"
        ],
        "context_loss": [
            "检查对话历史是否完整",
            "增加上下文窗口大小",
            "使用摘要技术减少长度",
            "检查消息合并逻辑"
        ],
        "cost_anomaly": [
            "减少 max_tokens 限制",
            "使用更便宜的模型",
            "优化 Prompt 长度",
            "添加 Token 使用监控"
        ],
    }
    
    def __init__(self):
        self.anomaly_patterns = defaultdict(list)
        self.scenario_stats = defaultdict(lambda: defaultdict(int))
        
    def analyze_report(self, report_path: str) -> Dict:
        """分析单个测试报告"""
        print(f"\n{'='*70}")
        print(f"分析报告: {report_path}")
        print(f"{'='*70}\n")
        
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
        
        # 基本统计
        session_id = report.get('session_id', 'unknown')
        scenario = report.get('scenario_name', 'unknown')
        status = report.get('status', 'unknown')
        
        print(f"会话 ID: {session_id}")
        print(f"场景: {scenario}")
        print(f"状态: {status}")
        print(f"轮次: {len(report.get('rounds', []))}")
        print(f"异常数: {len(report.get('anomalies', []))}")
        
        # 分析每一轮
        rounds = report.get('rounds', [])
        anomalies = report.get('anomalies', [])
        
        print(f"\n详细分析:")
        print("-" * 70)
        
        for i, round_data in enumerate(rounds, 1):
            anomaly = round_data.get('anomaly', 'none')
            if anomaly != 'none':
                print(f"\n[第 {i} 轮] ⚠️  异常: {anomaly}")
                print(f"  用户: {round_data.get('user_input', '')[:60]}...")
                print(f"  AI: {round_data.get('response', '')[:100]}...")
                print(f"  详情: {round_data.get('anomaly_detail', 'N/A')}")
                
                # 提供修复建议
                suggestions = self.FIX_SUGGESTIONS.get(anomaly, ["检查日志获取更多信息"])
                print(f"  💡 建议:")
                for suggestion in suggestions:
                    print(f"      - {suggestion}")
        
        # 根因分析
        print(f"\n{'='*70}")
        print("根因分析")
        print(f"{'='*70}")
        
        root_causes = self._analyze_root_causes(report)
        for i, (cause, evidence) in enumerate(root_causes.items(), 1):
            print(f"\n{i}. {cause}")
            print(f"   证据: {evidence}")
        
        # 生成修复任务清单
        print(f"\n{'='*70}")
        print("修复任务清单")
        print(f"{'='*70}")
        
        tasks = self._generate_fix_tasks(report)
        for i, task in enumerate(tasks, 1):
            priority = "🔴" if task['priority'] == 'high' else "🟡" if task['priority'] == 'medium' else "🟢"
            print(f"\n{i}. {priority} [{task['priority'].upper()}] {task['description']}")
            print(f"   相关文件: {task.get('files', ['N/A'])}")
            print(f"   操作: {task['action']}")
        
        return {
            "session_id": session_id,
            "anomaly_count": len(anomalies),
            "root_causes": list(root_causes.keys()),
            "fix_tasks": tasks
        }
    
    def _analyze_root_causes(self, report: Dict) -> Dict[str, str]:
        """分析根因"""
        causes = {}
        
        anomalies = report.get('anomalies', [])
        rounds = report.get('rounds', [])
        
        # 统计异常类型
        anomaly_types = [a.get('type') for a in anomalies]
        type_counts = Counter(anomaly_types)
        
        # 模式 1: 连续超时
        if type_counts.get('timeout', 0) >= 2:
            causes["LLM 响应超时"] = f"连续 {type_counts['timeout']} 次超时，可能是网络或模型负载问题"
        
        # 模式 2: 重复响应
        if type_counts.get('repetition', 0) >= 1:
            causes["模型输出多样性不足"] = "检测到重复响应，temperature 可能过低或 prompt 需要优化"
        
        # 模式 3: 工具调用失败
        if type_counts.get('tool_failure', 0) >= 1:
            causes["工具系统不稳定"] = f"{type_counts['tool_failure']} 次工具调用失败"
        
        # 模式 4: 上下文丢失（多轮对话中）
        for round_data in rounds:
            if round_data.get('anomaly') == 'context_loss':
                causes["上下文管理机制缺陷"] = "多轮对话中上下文丢失"
                break
        
        # 模式 5: Token 过多
        if type_counts.get('cost_anomaly', 0) >= 1:
            causes["Prompt 过长或输出不受控"] = "Token 使用量异常"
        
        # 默认根因
        if not causes:
            causes["未知问题"] = "需要更多日志信息进行分析"
        
        return causes
    
    def _generate_fix_tasks(self, report: Dict) -> List[Dict]:
        """生成修复任务清单"""
        tasks = []
        anomalies = report.get('anomalies', [])
        
        # 按异常类型分组
        by_type = defaultdict(list)
        for a in anomalies:
            by_type[a.get('type')].append(a)
        
        # 高优先级任务
        if 'timeout' in by_type:
            tasks.append({
                'priority': 'high',
                'description': '增加 LLM 调用超时配置和重试机制',
                'files': ['backend/app/infrastructure/llm/factory.py'],
                'action': '添加 timeout 和 retry 参数'
            })
        
        if 'error_response' in by_type:
            tasks.append({
                'priority': 'high',
                'description': '修复后端 API 错误处理',
                'files': ['backend/app/api/routes/conversations.py'],
                'action': '添加异常捕获和日志记录'
            })
        
        if 'tool_failure' in by_type:
            tasks.append({
                'priority': 'high',
                'description': '增强工具调用错误处理',
                'files': ['backend/app/domain/tools/executor.py'],
                'action': '添加工具参数验证和失败重试'
            })
        
        # 中优先级任务
        if 'repetition' in by_type:
            tasks.append({
                'priority': 'medium',
                'description': '优化 Prompt 增加输出多样性',
                'files': ['backend/app/core/engine/prompts/'],
                'action': '调整 temperature 和添加多样性提示'
            })
        
        if 'cost_anomaly' in by_type:
            tasks.append({
                'priority': 'medium',
                'description': '添加 Token 使用限制',
                'files': ['backend/app/core/engine/__init__.py'],
                'action': '设置 max_tokens 限制和告警'
            })
        
        # 低优先级任务
        if 'context_loss' in by_type:
            tasks.append({
                'priority': 'low',
                'description': '优化上下文管理机制',
                'files': ['backend/app/core/engine/message_utils.py'],
                'action': '改进消息窗口和摘要逻辑'
            })
        
        return tasks
    
    def analyze_trend(self, days: int = 7) -> Dict:
        """分析异常趋势"""
        print(f"\n{'='*70}")
        print(f"异常趋势分析 (最近 {days} 天)")
        print(f"{'='*70}\n")
        
        reports_dir = Path("tests/monitoring/reports")
        if not reports_dir.exists():
            print("报告目录不存在")
            return {}
        
        # 收集最近 N 天的报告
        cutoff_date = datetime.now() - timedelta(days=days)
        reports = []
        
        for report_file in reports_dir.glob("*.json"):
            try:
                with open(report_file, 'r') as f:
                    report = json.load(f)
                    report_time = datetime.fromisoformat(report.get('timestamp', '2000-01-01'))
                    if report_time >= cutoff_date:
                        reports.append(report)
            except:
                continue
        
        if not reports:
            print("没有找到近期的测试报告")
            return {}
        
        # 统计趋势
        daily_stats = defaultdict(lambda: defaultdict(int))
        anomaly_trend = defaultdict(lambda: defaultdict(int))
        
        for report in reports:
            date = datetime.fromisoformat(report.get('timestamp')).strftime('%Y-%m-%d')
            daily_stats[date]['total'] += 1
            daily_stats[date]['anomalies'] += report.get('total_anomalies', 0)
            
            for anomaly_type, count in report.get('anomaly_breakdown', {}).items():
                anomaly_trend[anomaly_type][date] += count
        
        # 显示趋势
        print("每日测试统计:")
        print("-" * 70)
        for date in sorted(daily_stats.keys()):
            stats = daily_stats[date]
            print(f"{date}: {stats['total']} 次测试, {stats['anomalies']} 个异常")
        
        print(f"\n异常类型趋势:")
        print("-" * 70)
        for anomaly_type, daily_counts in sorted(anomaly_trend.items()):
            total = sum(daily_counts.values())
            print(f"\n{anomaly_type}: 共 {total} 次")
            for date, count in sorted(daily_counts.items())[-3:]:  # 最近3天
                print(f"  {date}: {count}")
        
        # 识别恶化趋势
        print(f"\n{'='*70}")
        print("趋势预警")
        print(f"{'='*70}")
        
        warnings = []
        for anomaly_type, daily_counts in anomaly_trend.items():
            dates = sorted(daily_counts.keys())
            if len(dates) >= 2:
                recent = daily_counts[dates[-1]]
                previous = daily_counts[dates[-2]]
                if recent > previous * 1.5:  # 增长超过 50%
                    warnings.append(f"⚠️  {anomaly_type} 异常数量增长 {((recent/previous-1)*100):.0f}%")
        
        if warnings:
            for warning in warnings:
                print(warning)
        else:
            print("✅ 未发现明显恶化趋势")
        
        return {
            "reports_analyzed": len(reports),
            "daily_stats": dict(daily_stats),
            "anomaly_trend": dict(anomaly_trend),
            "warnings": warnings
        }


def main():
    parser = argparse.ArgumentParser(description='异常分析工具')
    parser.add_argument('--report', type=str,
                       help='分析特定报告文件')
    parser.add_argument('--trend', action='store_true',
                       help='分析趋势')
    parser.add_argument('--days', type=int, default=7,
                       help='趋势分析天数')
    parser.add_argument('--latest', action='store_true',
                       help='分析最新的报告')
    
    args = parser.parse_args()
    
    analyzer = AnomalyAnalyzer()
    
    if args.report:
        analyzer.analyze_report(args.report)
    elif args.latest:
        # 查找最新报告
        reports_dir = Path("tests/monitoring/reports")
        reports = sorted(reports_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if reports:
            analyzer.analyze_report(str(reports[0]))
        else:
            print("没有找到报告文件")
    elif args.trend:
        analyzer.analyze_trend(args.days)
    else:
        # 默认：分析最新报告 + 趋势
        reports_dir = Path("tests/monitoring/reports")
        reports = sorted(reports_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if reports:
            analyzer.analyze_report(str(reports[0]))
            print("\n")
            analyzer.analyze_trend(7)


if __name__ == "__main__":
    main()
