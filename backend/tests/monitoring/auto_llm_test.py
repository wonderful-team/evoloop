#!/usr/bin/env python3
"""
自动读取 .env 配置，直接调用 LLM 测试
无需手动设置环境变量，无需启动后端
"""

import asyncio
import json
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

# 添加项目路径
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop')
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend')

from test_dialogue_scenarios import ALL_SCENARIOS


class EnvLoader:
    """自动加载 .env 文件"""
    
    @staticmethod
    def load_env_file(env_path: str) -> Dict[str, str]:
        """加载 .env 文件"""
        env_vars = {}
        if not os.path.exists(env_path):
            return env_vars
        
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"\'')
        return env_vars
    
    @staticmethod
    def find_and_load() -> Dict[str, str]:
        """查找并加载 .env 文件"""
        # 尝试多个路径
        possible_paths = [
            '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env',
            '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/.env',
            os.path.join(os.getcwd(), '.env'),
            os.path.join(os.getcwd(), '..', '.env'),
            os.path.join(os.getcwd(), '..', '..', '.env'),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"✅ 加载配置: {path}")
                return EnvLoader.load_env_file(path)
        
        return {}


class LLMConfig:
    """LLM 配置"""
    
    def __init__(self):
        # 先加载 .env
        env_vars = EnvLoader.find_and_load()
        
        # 读取配置，优先使用环境变量，其次 .env，最后默认值
        self.api_key = os.getenv('OPENAI_API_KEY') or env_vars.get('OPENAI_API_KEY', '')
        self.base_url = os.getenv('OPENAI_BASE_URL') or env_vars.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        self.model = os.getenv('OPENAI_MODEL_NAME') or env_vars.get('OPENAI_MODEL_NAME', 'gpt-4o-mini')
        
        # 其他可能的配置名
        if not self.api_key:
            self.api_key = env_vars.get('LLM_API_KEY', '')
        if not self.base_url:
            self.base_url = env_vars.get('LLM_BASE_URL', self.base_url)
        if not self.model:
            self.model = env_vars.get('LLM_MODEL', self.model)
    
    def is_valid(self) -> bool:
        return bool(self.api_key)
    
    def __str__(self):
        return f"模型: {self.model}\nAPI: {self.base_url}\nKey: {self.api_key[:10]}..."


class DirectLLMTester:
    """直接 LLM 测试器"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        
    async def get_client(self):
        """获取或创建客户端"""
        if self.client is None:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url
                )
            except ImportError:
                raise ImportError("请安装 openai: pip install openai")
        return self.client
    
    async def chat(self, message: str, system_prompt: Optional[str] = None, max_tokens: int = 800) -> Dict:
        """直接调用 LLM"""
        client = await self.get_client()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        
        try:
            import time
            start = time.time()
            
            response = await client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            elapsed = (time.time() - start) * 1000
            
            return {
                "success": True,
                "content": response.choices[0].message.content,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "time_ms": elapsed
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": f"[ERROR: {e}]",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "time_ms": 0
            }


@dataclass
class TestResult:
    """测试结果"""
    scenario: str
    user_input: str
    ai_response: str
    time_ms: float
    tokens: int
    success: bool
    error: Optional[str] = None
    extracted_code: Optional[str] = None
    execution_result: Optional[str] = None
    anomaly: Optional[str] = None


class CodeExecutor:
    """代码执行器"""
    
    @staticmethod
    def extract_code(content: str) -> Optional[str]:
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
    
    @staticmethod
    def execute(code: str) -> Tuple[bool, str]:
        """安全执行代码"""
        try:
            safe_globals = {"__builtins__": {"len": len, "range": range, "print": print}}
            exec_globals = {}
            exec(code, safe_globals, exec_globals)
            
            # 找函数测试
            for name, obj in exec_globals.items():
                if callable(obj) and not name.startswith('_'):
                    try:
                        result = obj(10)
                        return True, f"{name}(10) = {result}"
                    except:
                        pass
            return True, "代码可执行"
        except Exception as e:
            return False, str(e)


class AnomalyDetector:
    """异常检测"""
    
    def __init__(self):
        self.history = []
    
    def check(self, response: str, time_ms: float, tokens: int) -> Optional[str]:
        """检查异常"""
        # 空响应
        if not response or len(response.strip()) < 30:
            return "EMPTY_RESPONSE"
        
        # 超时
        if time_ms > 30000:
            return "TIMEOUT"
        
        # Token 异常
        if tokens > 2000:
            return "COST_ANOMALY"
        
        # 重复检测
        for hist in self.history[-2:]:
            if self._similarity(response, hist) > 0.8:
                return "REPETITION"
        
        self.history.append(response)
        if len(self.history) > 5:
            self.history.pop(0)
        
        return None
    
    def _similarity(self, a: str, b: str) -> float:
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)


async def run_test_scenario(tester: DirectLLMTester, scenario_name: str, max_rounds: int = 3):
    """运行测试场景"""
    print(f"\n{'='*70}")
    print(f"🚀 测试场景: {scenario_name}")
    print(f"{'='*70}")
    
    # 获取话术
    scenarios = ALL_SCENARIOS.get(scenario_name, [])
    if not scenarios:
        print(f"❌ 未知场景: {scenario_name}")
        return
    
    utterances = [s["cn"] for s in scenarios[:max_rounds]]
    print(f"测试话术: {len(utterances)} 条\n")
    
    # 检查 LLM 连接
    print("🔍 检查 LLM 连接...", end=" ")
    test_resp = await tester.chat("Hello", max_tokens=10)
    if not test_resp["success"]:
        print(f"❌ 失败")
        print(f"错误: {test_resp.get('error', 'Unknown')}")
        return
    print(f"✅ 成功 (模型: {tester.config.model})\n")
    
    # 运行测试
    detector = AnomalyDetector()
    results = []
    total_tokens = 0
    
    for i, utterance in enumerate(utterances, 1):
        print(f"📌 [第 {i} 轮] {utterance[:60]}...")
        
        # 调用 LLM
        start_time = asyncio.get_event_loop().time()
        response = await tester.chat(
            utterance,
            system_prompt="你是一个专业的程序员，帮助用户编写高质量代码。",
            max_tokens=800
        )
        
        if not response["success"]:
            print(f"  ❌ LLM 调用失败: {response.get('error')}")
            continue
        
        # 提取和验证
        content = response["content"]
        code = CodeExecutor.extract_code(content)
        exec_success, exec_result = (False, "") if not code else CodeExecutor.execute(code)
        
        # 异常检测
        anomaly = detector.check(content, response["time_ms"], response["total_tokens"])
        
        # 显示结果
        print(f"  ✅ {response['time_ms']:.0f}ms, {response['total_tokens']}tokens")
        print(f"     {content[:100]}...")
        
        if code:
            icon = "✓" if exec_success else "✗"
            print(f"     [{icon}] 代码执行: {exec_result}")
        
        if anomaly:
            print(f"  ⚠️  检测到异常: {anomaly}")
        
        total_tokens += response["total_tokens"]
        
        results.append(TestResult(
            scenario=scenario_name,
            user_input=utterance,
            ai_response=content,
            time_ms=response["time_ms"],
            tokens=response["total_tokens"],
            success=response["success"],
            extracted_code=code,
            execution_result=exec_result if code else None,
            anomaly=anomaly
        ))
        
        await asyncio.sleep(0.5)
    
    # 汇总
    cost = total_tokens * 0.000000375  # gpt-4o-mini 估算
    
    print(f"\n{'='*70}")
    print("📊 测试汇总")
    print(f"{'='*70}")
    print(f"场景: {scenario_name}")
    print(f"轮次: {len(results)}")
    print(f"Token: {total_tokens}")
    print(f"成本: ${cost:.6f}")
    
    anomalies = [r for r in results if r.anomaly]
    print(f"异常: {len(anomalies)}")
    
    # 保存报告
    os.makedirs("tests/monitoring/reports", exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "scenario": scenario_name,
        "model": tester.config.model,
        "total_tokens": total_tokens,
        "cost_usd": cost,
        "results": [
            {
                "round": i+1,
                "user": r.user_input,
                "ai_preview": r.ai_response[:200],
                "time_ms": r.time_ms,
                "tokens": r.tokens,
                "code": r.extracted_code[:100] if r.extracted_code else None,
                "exec": r.execution_result,
                "anomaly": r.anomaly
            }
            for i, r in enumerate(results)
        ]
    }
    
    report_file = f"tests/monitoring/reports/auto_test_{scenario_name}_{datetime.now().strftime('%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 报告: {report_file}")
    print(f"{'='*70}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='自动 LLM 测试')
    parser.add_argument('--scenario', type=str, default='code_generation',
                       help='测试场景')
    parser.add_argument('--max-rounds', type=int, default=3,
                       help='最大轮数')
    parser.add_argument('--all', action='store_true',
                       help='测试所有场景')
    args = parser.parse_args()
    
    print("="*70)
    print("🚀 EvoLoop 自动 LLM 测试")
    print("="*70)
    
    # 加载配置
    config = LLMConfig()
    print(f"\n配置信息:")
    print(f"{config}\n")
    
    if not config.is_valid():
        print("❌ 错误: 未找到有效的 API Key")
        print("   请确保 .env 文件中设置了 OPENAI_API_KEY")
        return
    
    # 创建测试器
    tester = DirectLLMTester(config)
    
    # 运行测试
    if args.all:
        scenarios = ['code_generation', 'code_optimization', 'knowledge_query']
        for s in scenarios:
            await run_test_scenario(tester, s, args.max_rounds)
    else:
        await run_test_scenario(tester, args.scenario, args.max_rounds)


if __name__ == "__main__":
    asyncio.run(main())
