#!/usr/bin/env python3
"""
直接调用 Agent 内部方法测试

绕过 HTTP 接口，直接调用:
- app.api.routes.agent._prepare_and_dispatch
- app.core.engine.background_agent.run_agent_background

使用：
    .venv/bin/python tests/monitoring/test_agent_direct.py --scenario code_generation
"""

import asyncio
import json
import os
import sys
import argparse
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# 添加项目路径
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

# 加载 .env
from pathlib import Path
def load_env():
    env_path = Path('/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env')
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"\''))

load_env()

from test_dialogue_scenarios import ALL_SCENARIOS


@dataclass
class TestResult:
    scenario: str
    user_input: str
    thread_id: str
    success: bool
    response_preview: str = ""
    steps_count: int = 0
    error: Optional[str] = None
    execution_time: float = 0.0


class AgentDirectTester:
    """直接测试 Agent 方法"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        
    async def test_with_prepare_dispatch(self, scenario: str, utterances: List[str], project_id: int = 1):
        """
        使用 _prepare_and_dispatch 方法测试
        这是 agent.py 中的内部方法，处理完整的对话流程
        """
        print(f"\n{'='*70}")
        print(f"🚀 测试场景: {scenario}")
        print(f"方法: _prepare_and_dispatch (完整 Agent 流程)")
        print(f"{'='*70}\n")
        
        # 导入必要的模块
        try:
            from fastapi import BackgroundTasks
            from app.api.routes.agent import _prepare_and_dispatch
            from app.infrastructure.database.sql.database import init_db
            
            # 初始化数据库
            await init_db()
            
        except Exception as e:
            print(f"❌ 导入失败: {e}")
            return []
        
        results = []
        thread_id = f"test-{scenario}-{datetime.now().strftime('%H%M%S')}"
        
        for i, utterance in enumerate(utterances, 1):
            print(f"\n📌 [第 {i} 轮] {utterance[:60]}...")
            print("-" * 70)
            
            start_time = asyncio.get_event_loop().time()
            
            try:
                # 创建 BackgroundTasks（模拟）
                bg_tasks = BackgroundTasks()
                
                # 调用 _prepare_and_dispatch
                result = await _prepare_and_dispatch(
                    thread_id=thread_id,
                    project_id=project_id,
                    bg_tasks=bg_tasks,
                    message_content=utterance,
                    attachments=None,
                    command_id=None,
                    checkpoint_id=None,
                    is_retry=False
                )
                
                elapsed = asyncio.get_event_loop().time() - start_time
                
                print(f"✅ 已调度 (耗时: {elapsed:.2f}s)")
                print(f"   状态: {result.get('status')}")
                print(f"   Thread: {result.get('thread_id')}")
                if 'message_id' in result:
                    print(f"   Message ID: {result.get('message_id')}")
                
                # 注意：_prepare_and_dispatch 是异步调度，实际执行在后台
                # 这里我们只验证调度成功
                results.append(TestResult(
                    scenario=scenario,
                    user_input=utterance,
                    thread_id=thread_id,
                    success=True,
                    response_preview="[Agent 已调度，后台执行中...]",
                    execution_time=elapsed
                ))
                
                # 等待一会儿让 Agent 开始执行
                await asyncio.sleep(2)
                
            except Exception as e:
                elapsed = asyncio.get_event_loop().time() - start_time
                print(f"❌ 失败: {e}")
                import traceback
                traceback.print_exc()
                
                results.append(TestResult(
                    scenario=scenario,
                    user_input=utterance,
                    thread_id=thread_id,
                    success=False,
                    error=str(e),
                    execution_time=elapsed
                ))
        
        return results
    
    async def test_run_agent_background_directly(self, scenario: str, utterances: List[str], project_id: int = 1):
        """
        直接调用 run_agent_background 方法
        这是 Agent 执行的核心方法
        """
        print(f"\n{'='*70}")
        print(f"🚀 测试场景: {scenario}")
        print(f"方法: run_agent_background (核心执行)")
        print(f"{'='*70}\n")
        
        try:
            from app.core.engine.background_agent import run_agent_background
            from app.infrastructure.database.sql.database import init_db
            from app.core.globals import initialize_graph
            
            # 初始化
            await init_db()
            await initialize_graph()
            
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return []
        
        results = []
        thread_id = f"test-{scenario}-{datetime.now().strftime('%H%M%S')}"
        
        for i, utterance in enumerate(utterances, 1):
            print(f"\n📌 [第 {i} 轮] {utterance[:60]}...")
            print("-" * 70)
            
            start_time = asyncio.get_event_loop().time()
            
            try:
                # 构建输入
                inputs = {
                    "messages": [{"type": "human", "content": utterance}],
                    "project_id": project_id,
                    "goal": utterance[:50],
                    "is_retry": False
                }
                
                # 直接调用 run_agent_background
                print("  ⏳ 执行 Agent...")
                await run_agent_background(thread_id, inputs)
                
                elapsed = asyncio.get_event_loop().time() - start_time
                
                print(f"✅ 执行完成 (耗时: {elapsed:.2f}s)")
                
                results.append(TestResult(
                    scenario=scenario,
                    user_input=utterance,
                    thread_id=thread_id,
                    success=True,
                    execution_time=elapsed
                ))
                
            except Exception as e:
                elapsed = asyncio.get_event_loop().time() - start_time
                print(f"❌ 执行失败: {e}")
                import traceback
                traceback.print_exc()
                
                results.append(TestResult(
                    scenario=scenario,
                    user_input=utterance,
                    thread_id=thread_id,
                    success=False,
                    error=str(e),
                    execution_time=elapsed
                ))
        
        return results
    
    def print_summary(self, results: List[TestResult]):
        """打印汇总"""
        print(f"\n{'='*70}")
        print("📊 测试汇总")
        print(f"{'='*70}")
        
        success = sum(1 for r in results if r.success)
        failed = len(results) - success
        total_time = sum(r.execution_time for r in results)
        
        print(f"总测试数: {len(results)}")
        print(f"  ✅ 成功: {success}")
        print(f"  ❌ 失败: {failed}")
        print(f"总耗时: {total_time:.2f}s")
        
        print(f"\n详细结果:")
        for r in results:
            icon = "✅" if r.success else "❌"
            print(f"  {icon} [{r.scenario}] {r.user_input[:40]}... ({r.execution_time:.1f}s)")
            if r.error:
                print(f"      错误: {r.error[:80]}")
        
        print(f"{'='*70}")


async def main():
    parser = argparse.ArgumentParser(description='直接测试 Agent 方法')
    parser.add_argument('--scenario', type=str, default='code_generation',
                       help='测试场景')
    parser.add_argument('--method', type=str, default='background',
                       choices=['background', 'dispatch'],
                       help='测试方法')
    parser.add_argument('--max-rounds', type=int, default=2,
                       help='最大轮数')
    parser.add_argument('--project-id', type=int, default=1,
                       help='项目 ID')
    
    args = parser.parse_args()
    
    print("="*70)
    print("🚀 EvoLoop Agent 直接测试")
    print("="*70)
    print(f"场景: {args.scenario}")
    print(f"方法: {args.method}")
    print(f"项目: {args.project_id}")
    print("="*70)
    
    # 获取话术
    scenarios = ALL_SCENARIOS.get(args.scenario, [])
    if not scenarios:
        print(f"❌ 未知场景: {args.scenario}")
        print(f"可用场景: {list(ALL_SCENARIOS.keys())}")
        return
    
    utterances = [s["cn"] for s in scenarios[:args.max_rounds]]
    
    # 运行测试
    tester = AgentDirectTester()
    
    if args.method == 'background':
        results = await tester.test_run_agent_background_directly(
            args.scenario, utterances, args.project_id
        )
    else:
        results = await tester.test_with_prepare_dispatch(
            args.scenario, utterances, args.project_id
        )
    
    # 汇总
    tester.print_summary(results)
    
    # 保存报告
    import os
    os.makedirs("tests/monitoring/reports", exist_ok=True)
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "type": "agent_direct_test",
        "method": args.method,
        "scenario": args.scenario,
        "results": [
            {
                "scenario": r.scenario,
                "user_input": r.user_input,
                "thread_id": r.thread_id,
                "success": r.success,
                "error": r.error,
                "execution_time": r.execution_time
            }
            for r in results
        ]
    }
    
    report_file = f"tests/monitoring/reports/agent_direct_{args.scenario}_{datetime.now().strftime('%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 报告已保存: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())
