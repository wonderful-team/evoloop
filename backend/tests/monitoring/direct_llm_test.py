#!/usr/bin/env python3
"""
直接调用 LLM 的测试脚本 - 无需启动后端服务

特点：
- 直接调用 OpenAI / LM Studio / Ollama 等 LLM API
- 不依赖 HTTP 后端服务
- 完整的监控、切断、重试机制
- 成本控制和 Token 统计

使用：
    # 方式1: 使用 OpenAI
    export OPENAI_API_KEY=sk-xxx
    python direct_llm_test.py --scenario code_generation

    # 方式2: 使用本地模型 (LM Studio / Ollama)
    export OPENAI_BASE_URL=http://localhost:1234/v1
    export OPENAI_API_KEY=lm-studio
    python direct_llm_test.py --scenario code_generation

    # 方式3: 批量测试
    python direct_llm_test.py --all --max-rounds 3
"""

import asyncio
import json
import os
import sys
import argparse
import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

# 添加项目路径
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop')
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from test_dialogue_scenarios import ALL_SCENARIOS


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    INTERRUPTED = "interrupted"


class AnomalyType(Enum):
    NONE = "none"
    TIMEOUT = "timeout"
    EMPTY_RESPONSE = "empty_response"
    REPETITION = "repetition"
    HALLUCINATION = "hallucination"
    COST_ANOMALY = "cost_anomaly"
    EXECUTION_ERROR = "execution_error"
    QUALITY_ISSUE = "quality_issue"


@dataclass
class TestRound:
    """单轮测试记录"""
    round_num: int
    user_input: str
    timestamp: float
    
    # LLM 响应
    ai_response: str = ""
    response_time_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    # 验证结果
    extracted_code: Optional[str] = None
    execution_result: Optional[str] = None
    execution_success: bool = False
    
    # 异常
    anomaly: AnomalyType = AnomalyType.NONE
    anomaly_detail: str = ""
    
    # 原始数据
    raw_response: Dict = field(default_factory=dict)


@dataclass
class TestSession:
    """测试会话"""
    session_id: str
    scenario_name: str
    start_time: float
    
    status: TestStatus = TestStatus.PENDING
    rounds: List[TestRound] = field(default_factory=list)
    
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    
    interrupted_at: Optional[int] = None
    interrupt_reason: str = ""


class LLMClient:
    """LLM 客户端 - 直接调用 API"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        
        # 延迟导入，避免启动时出错
        self._client = None
        
    @property
    def client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
            except ImportError:
                raise ImportError("请安装 openai: pip install openai")
        return self._client
    
    async def chat(self, user_message: str, system_prompt: Optional[str] = None, max_tokens: int = 800) -> Dict:
        """发送消息到 LLM"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            return {
                "success": True,
                "content": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "raw": response
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": "",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self):
        self.response_history = []
        
    def check(self, round_record: TestRound) -> Optional[Tuple[AnomalyType, str]]:
        """检测异常"""
        content = round_record.ai_response
        
        # 1. 空响应
        if not content or len(content.strip()) < 20:
            return AnomalyType.EMPTY_RESPONSE, f"响应内容过短: {len(content) if content else 0} 字符"
        
        # 2. 超时（这里指 LLM 响应时间异常）
        if round_record.response_time_ms > 30000:
            return AnomalyType.TIMEOUT, f"LLM 响应时间过长: {round_record.response_time_ms/1000:.1f}s"
        
        # 3. Token 异常
        if round_record.total_tokens > 2000:
            return AnomalyType.COST_ANOMALY, f"Token 使用量异常: {round_record.total_tokens}"
        
        # 4. 重复检测
        for i, hist in enumerate(self.response_history[-3:]):
            similarity = self._similarity(content, hist)
            if similarity > 0.85:
                return AnomalyType.REPETITION, f"与历史响应相似度 {similarity:.1%}"
        
        # 5. 幻觉检测（简单版：回答太短可能是敷衍）
        if len(content) < 100 and "?" not in content:
            return AnomalyType.QUALITY_ISSUE, "响应过短，可能质量不高"
        
        self.response_history.append(content)
        if len(self.response_history) > 10:
            self.response_history.pop(0)
        
        return None
    
    def _similarity(self, text1: str, text2: str) -> float:
        """计算相似度"""
        if not text1 or not text2:
            return 0.0
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())
        if not set1 or not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)


class DirectLLMTester:
    """直接 LLM 测试器"""
    
    def __init__(self):
        self.llm = LLMClient()
        self.detector = AnomalyDetector()
        self.should_stop = False
        
        # 成本统计
        self.total_cost = 0.0
        
    async def test_scenario(
        self,
        scenario_name: str,
        utterances: List[str],
        max_rounds: int = 5,
        system_prompt: Optional[str] = None
    ) -> TestSession:
        """
        测试一个场景
        
        Args:
            scenario_name: 场景名称
            utterances: 用户话术列表
            max_rounds: 最大轮数
            system_prompt: 系统提示词
        """
        session_id = f"{scenario_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        session = TestSession(
            session_id=session_id,
            scenario_name=scenario_name,
            start_time=asyncio.get_event_loop().time()
        )
        
        print(f"\n{'='*70}")
        print(f"🚀 开始测试: {scenario_name}")
        print(f"会话 ID: {session_id}")
        print(f"模型: {self.llm.model}")
        print(f"话术数: {len(utterances)}")
        print(f"{'='*70}")
        
        # 检查 LLM 可用性
        print("\n🔍 检查 LLM 连接...", end=" ")
        test_resp = await self.llm.chat("Hello", max_tokens=10)
        if not test_resp["success"]:
            print(f"❌ 失败")
            print(f"错误: {test_resp.get('error', 'Unknown')}")
            session.status = TestStatus.ERROR
            session.interrupt_reason = f"LLM 连接失败: {test_resp.get('error')}"
            return session
        print("✅ 连接正常")
        
        session.status = TestStatus.RUNNING
        
        # 逐轮测试
        for i, utterance in enumerate(utterances[:max_rounds], 1):
            if self.should_stop:
                session.status = TestStatus.INTERRUPTED
                session.interrupted_at = i
                session.interrupt_reason = "人工停止"
                break
            
            print(f"\n📌 [第 {i} 轮] 用户: {utterance[:60]}...")
            
            # 执行一轮
            round_record = await self._execute_round(
                i, utterance, system_prompt
            )
            session.rounds.append(round_record)
            
            # 统计
            session.total_prompt_tokens += round_record.prompt_tokens
            session.total_completion_tokens += round_record.completion_tokens
            session.total_tokens += round_record.total_tokens
            
            # 异常检测
            anomaly = self.detector.check(round_record)
            if anomaly:
                anomaly_type, detail = anomaly
                round_record.anomaly = anomaly_type
                round_record.anomaly_detail = detail
                
                print(f"⚠️  检测到异常 [{anomaly_type.value}]: {detail}")
                
                # 关键异常：询问是否切断
                if anomaly_type in [AnomalyType.REPETITION, AnomalyType.COST_ANOMALY]:
                    print(f"🛑 关键异常，建议切断测试")
                    
                    # 自动模式或交互式
                    choice = input("选项: [c]继续 [r]重试 [s]跳过 [q]退出: ").strip().lower()
                    
                    if choice == 'r':
                        # 重试当前轮
                        print("重试中...")
                        session.rounds.pop()
                        round_record = await self._execute_round(i, utterance, system_prompt)
                        session.rounds.append(round_record)
                        
                    elif choice == 's':
                        print("跳过剩余测试")
                        break
                    elif choice == 'q':
                        session.status = TestStatus.INTERRUPTED
                        session.interrupted_at = i
                        session.interrupt_reason = "用户退出"
                        break
            else:
                print(f"✅ 正常")
            
            # 显示结果
            print(f"   AI ({round_record.response_time_ms/1000:.1f}s, {round_record.total_tokens}tokens): {round_record.ai_response[:80]}...")
            
            if round_record.execution_success:
                print(f"   ✓ 代码执行: {round_record.execution_result}")
            elif round_record.execution_result:
                print(f"   ✗ 代码执行失败: {round_record.execution_result}")
        
        else:
            # 正常完成
            session.status = TestStatus.SUCCESS
        
        # 计算成本
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        prompt_cost = session.total_prompt_tokens * 0.00000015
        completion_cost = session.total_completion_tokens * 0.00000060
        session.estimated_cost = prompt_cost + completion_cost
        
        # 完成
        self._print_summary(session)
        await self._save_report(session)
        
        return session
    
    async def _execute_round(
        self,
        round_num: int,
        user_input: str,
        system_prompt: Optional[str]
    ) -> TestRound:
        """执行单轮对话"""
        record = TestRound(
            round_num=round_num,
            user_input=user_input,
            timestamp=asyncio.get_event_loop().time()
        )
        
        # 调用 LLM
        start = asyncio.get_event_loop().time()
        
        # 根据场景调整 system_prompt
        if not system_prompt:
            if "代码" in user_input or "写" in user_input:
                system_prompt = "你是一个专业的程序员，帮助用户编写高质量代码。"
            else:
                system_prompt = "你是一个有用的 AI 助手。"
        
        response = await self.llm.chat(user_input, system_prompt)
        
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        
        record.response_time_ms = elapsed_ms
        record.prompt_tokens = response.get("prompt_tokens", 0)
        record.completion_tokens = response.get("completion_tokens", 0)
        record.total_tokens = response.get("total_tokens", 0)
        record.raw_response = response
        
        if response["success"]:
            record.ai_response = response["content"]
            
            # 如果是代码生成，尝试提取和执行
            if any(kw in user_input for kw in ["写", "生成", "代码", "函数"]):
                code = self._extract_code(record.ai_response)
                if code:
                    record.extracted_code = code
                    success, result = self._execute_code(code)
                    record.execution_success = success
                    record.execution_result = result
        else:
            record.ai_response = f"[ERROR: {response.get('error', 'Unknown')}]"
            record.anomaly = AnomalyType.EMPTY_RESPONSE
            record.anomaly_detail = f"LLM 调用失败: {response.get('error')}"
        
        return record
    
    def _extract_code(self, content: str) -> Optional[str]:
        """提取代码块"""
        patterns = [
            r'```python\n(.*?)\n```',
            r'```\n(.*?)\n```',
        ]
        for p in patterns:
            m = re.search(p, content, re.DOTALL)
            if m:
                return m.group(1)
        return None
    
    def _execute_code(self, code: str) -> Tuple[bool, str]:
        """安全执行 Python 代码"""
        try:
            # 限制执行环境
            safe_globals = {
                "__builtins__": {
                    "len": len, "range": range, "print": print,
                    "str": str, "int": int, "list": list,
                    "dict": dict, "set": set, "tuple": tuple,
                }
            }
            exec_globals = {}
            exec(code, safe_globals, exec_globals)
            
            # 找函数测试
            for name, obj in exec_globals.items():
                if callable(obj) and not name.startswith('_'):
                    try:
                        result = obj(10)  # 测试 fib(10)
                        return True, f"{name}(10) = {result}"
                    except:
                        pass
            
            return True, "代码可执行，无测试函数"
        except Exception as e:
            return False, str(e)
    
    def _print_summary(self, session: TestSession):
        """打印汇总"""
        print(f"\n{'='*70}")
        print("📊 测试完成")
        print(f"{'='*70}")
        print(f"会话: {session.session_id}")
        print(f"状态: {session.status.value}")
        print(f"轮次: {len(session.rounds)}")
        print(f"Token: {session.total_prompt_tokens} prompt + {session.total_completion_tokens} completion = {session.total_tokens} total")
        print(f"成本: ${session.estimated_cost:.6f}")
        
        if session.interrupted_at:
            print(f"⚠️  在第 {session.interrupted_at} 轮被切断")
            print(f"原因: {session.interrupt_reason}")
        
        # 异常统计
        anomalies = [r for r in session.rounds if r.anomaly != AnomalyType.NONE]
        if anomalies:
            print(f"\n异常 ({len(anomalies)}):")
            for a in anomalies:
                print(f"  - 第 {a.round_num} 轮: [{a.anomaly.value}] {a.anomaly_detail}")
        
        print(f"{'='*70}")
    
    async def _save_report(self, session: TestSession):
        """保存报告"""
        os.makedirs("tests/monitoring/reports", exist_ok=True)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "type": "direct_llm_test",
            "session_id": session.session_id,
            "scenario": session.scenario_name,
            "model": self.llm.model,
            "status": session.status.value,
            "rounds": len(session.rounds),
            "tokens": {
                "prompt": session.total_prompt_tokens,
                "completion": session.total_completion_tokens,
                "total": session.total_tokens
            },
            "cost_usd": session.estimated_cost,
            "interrupted": session.interrupted_at,
            "interrupt_reason": session.interrupt_reason,
            "details": [
                {
                    "round": r.round_num,
                    "user": r.user_input,
                    "ai": r.ai_response[:300],
                    "time_ms": r.response_time_ms,
                    "tokens": r.total_tokens,
                    "code": r.extracted_code[:200] if r.extracted_code else None,
                    "exec_result": r.execution_result,
                    "anomaly": r.anomaly.value,
                    "anomaly_detail": r.anomaly_detail
                }
                for r in session.rounds
            ]
        }
        
        filename = f"tests/monitoring/reports/direct_llm_{session.session_id}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"📄 报告已保存: {filename}")


async def main():
    parser = argparse.ArgumentParser(description='直接 LLM 测试')
    parser.add_argument('--scenario', type=str, default='code_generation',
                       help='测试场景名称')
    parser.add_argument('--all', action='store_true',
                       help='测试所有场景')
    parser.add_argument('--max-rounds', type=int, default=3,
                       help='每场景最大轮数')
    parser.add_argument('--model', type=str,
                       help='覆盖模型名称')
    
    args = parser.parse_args()
    
    # 检查 API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ 错误: 请设置 OPENAI_API_KEY")
        print("   export OPENAI_API_KEY=sk-xxx")
        print("   或使用本地模型: export OPENAI_BASE_URL=http://localhost:1234/v1")
        return
    
    # 覆盖模型
    if args.model:
        os.environ["OPENAI_MODEL_NAME"] = args.model
    
    tester = DirectLLMTester()
    
    # 确定测试场景
    if args.all:
        scenarios = [
            ("code_generation", ALL_SCENARIOS["code_generation"]),
            ("code_optimization", ALL_SCENARIOS["code_optimization"]),
            ("knowledge_query", ALL_SCENARIOS["knowledge_query"]),
        ]
    else:
        scenario_data = ALL_SCENARIOS.get(args.scenario, [])
        if not scenario_data:
            print(f"❌ 未知场景: {args.scenario}")
            print(f"可用场景: {list(ALL_SCENARIOS.keys())}")
            return
        scenarios = [(args.scenario, scenario_data)]
    
    # 运行测试
    results = []
    for name, data in scenarios:
        utterances = [item["cn"] for item in data[:args.max_rounds]]
        session = await tester.test_scenario(name, utterances, args.max_rounds)
        results.append(session)
        await asyncio.sleep(1)  # 避免 rate limit
    
    # 批量汇总
    if len(results) > 1:
        print(f"\n{'='*70}")
        print("📊 批量测试汇总")
        print(f"{'='*70}")
        
        total_cost = sum(r.estimated_cost for r in results)
        total_tokens = sum(r.total_tokens for r in results)
        
        for r in results:
            icon = "✅" if r.status == TestStatus.SUCCESS else "⚠️" if r.status == TestStatus.INTERRUPTED else "❌"
            print(f"{icon} {r.scenario_name}: {r.status.value}, ${r.estimated_cost:.6f}")
        
        print(f"\n总成本: ${total_cost:.6f}")
        print(f"总 Token: {total_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
