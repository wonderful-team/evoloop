#!/usr/bin/env python3
"""
Kimi Context Optimization Test Script

测试不同上下文大小对 Kimi API 响应时间的影响，
帮助确定合理的上下文优化范围。

Usage:
    cd evoloop/backend
    python tests/test_kimi_context_optimization.py --local --quick

Token 获取方式:
    自动登录: 使用 EVOLOOP_USERNAME/EVOLOOP_PASSWORD 登录获取 token
    默认账号: preterchan / hellomylife

Environment Variables:
    GATEWAY_URL: EvoLoop Gateway URL (default: http://127.0.0.1)
    EVOLOOP_USERNAME: EvoLoop 用户名 (default: preterchan)
    EVOLOOP_PASSWORD: EvoLoop 密码 (default: hellomylife)
    TEST_MODEL: Model to test (default: kimi-k2-thinking-turbo)
"""

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

# 添加 backend 目录到 Python 路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 设置环境变量以避免启动 web 服务器
os.environ["ENVIRONMENT"] = "local"
os.environ["EMBEDDED_MODE"] = "True"

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("test_kimi")


@dataclass
class TestResult:
    """Test result container"""
    test_name: str
    system_prompt_size: int
    history_messages: int
    total_tokens: int
    first_token_time: float
    total_time: float
    response_length: int
    success: bool
    error: Optional[str] = None


async def login_and_get_token() -> tuple[str, int] | None:
    """
    通过 EvoCloud API 登录并获取 token。
    参考: test_billing_loop.py
    """
    try:
        from app.core.evocloud import evocloud_manager
        from app.core.identity import identity_service
    except ImportError as e:
        logger.error(f"❌ 无法导入 EvoLoop 模块: {e}")
        logger.error("请确保在 evoloop/backend 目录下运行")
        return None
    
    logger.info("🔄 初始化 EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"初始化警告 (可忽略): {e}")
    
    client = evocloud_manager.api
    
    # 获取登录凭据
    username = os.getenv("EVOLOOP_USERNAME", "preterchan")
    password = os.getenv("EVOLOOP_PASSWORD", "hellomylife")
    
    logger.info(f"🔄 使用账号 {username} 登录...")
    login_res = await client.login(username, password)
    
    if not login_res.get("success"):
        logger.error(f"❌ 登录失败: {login_res}")
        return None
    
    token = login_res["token"]
    
    # 获取用户信息
    user_info_resp = await client.request("GET", "/api/member/info", token=token)
    real_member_id = user_info_resp.get("data", {}).get("member_id", user_info_resp.get("data", {}).get("id"))
    
    if not real_member_id:
        logger.error(f"❌ 无法获取 member_id: {user_info_resp}")
        return None
    
    logger.info(f"✅ 登录成功 - Member ID: {real_member_id}")
    
    # 设置 token 和 member_id
    client.set_token(token)
    await identity_service.store.save_member_id(real_member_id)
    
    return token, real_member_id


class KimiContextTester:
    """Test Kimi API via Gateway with various context sizes"""
    
    def __init__(self, token: str, gateway_url: str | None = None):
        self.gateway_url = gateway_url or os.getenv("GATEWAY_URL") or os.getenv("EVOCLOUD_API_URL", "http://127.0.0.1")
        self.token = token
        self.model = os.getenv("TEST_MODEL", "kimi-k2-thinking-turbo")
        
        # 显示 token 前缀用于验证
        logger.info(f"🔑 Gateway Token: {self.token[:20]}...{self.token[-10:]}")
        logger.info(f"🌐 Gateway URL: {self.gateway_url}")

        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(600.0, connect=30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        self.results: List[TestResult] = []
    
    def _generate_system_prompt(self, size_kb: int) -> str:
        """Generate a system prompt of approximately size_kb KB"""
        # Base template (about 2KB)
        base = """## Your Role: Documenter
Execute the assigned task accurately.

## 🧠 Execution Protocol
- **Action-Oriented**: Use your Thinking space for brief reasoning, then call the appropriate tool immediately.
- **Purposeful Tooling**: Every tool call must have a clear intent.

## 📚 Memory Usage Guidelines
When using remembered information from `recall` or `search_history`:
- **Memories capture past state**: They reflect what was true when saved, not necessarily now
- **Always verify before recommending**: If a memory names a specific file, function, or pattern, verify it still exists

### 🎯 Role-Based Tool Priority
- **Primary**: `read_file`, `write_file`, `edit_file`, `execute_command`
- **Secondary**: `search_skills`, `recall`, `search_history`

### 📝 File Editing Protocol
1. **ALWAYS read first**: Call `read_file(path)` to get the actual current content before editing.
2. **Choose the right tool for the job**
3. **Provide unique context**
4. **Never ask permission**

## 🌅 ENVIRONMENT AWARENESS
- Host: Mac16,11 (Apple M4 Pro), macOS 15.7.2
- Network: Online

## ⚙️ System Info
Project ID: 43
CWD: /Users/test/project

## ✅ Completion Verification Protocol
After EVERY tool execution, you MUST check against the **Acceptance Criteria**:
1. **Did the action satisfy the criteria?**
   - YES → Provide final answer as plain text **IMMEDIATELY**
   - NO → Proceed to next step with a different approach

## 🌐 Browser Automation Protocol
When your mission involves web pages or browser UI:
1. **Use `browser_control` directly**: It handles the entire lifecycle
2. **DOM-first interaction**: Always prefer `selector`-based actions
3. **OS Coordination**: Only use `desktop_control` for tasks outside the browser viewport

## 🛡 Constraints & Guardrails
- **Mission Focused**: Stick strictly to the goals defined in the Mission Ticket.
- **Stateless**: You do not have long-term memory.
- **Least Privilege**: Only use the tools provided to you.

## 📝 Final Reporting
Once the criteria in the Mission Ticket are met:
- **DO NOT** generate a detailed summary report
- **DO** provide a brief confirmation (1-2 sentences max)

## 🧭 Reading Your Mission Ticket
The Supervisor has handed you an **ExecutionTicket**. It contains:
- `topic` / `reason` — the core objective in plain language.
- `focus_paths` — 1–3 files/directories identified as critical. **Start here.**
- `acceptance_criteria` — measurable outcomes that define "done".
"""
        
        current_size = len(base.encode('utf-8'))
        target_size = size_kb * 1024
        
        if current_size >= target_size:
            return base[:target_size]
        
        # Add filler content to reach target size
        filler_needed = target_size - current_size
        filler_line = "\n- Additional instruction line for context size testing. This is filler content to reach target size."
        lines_needed = filler_needed // len(filler_line.encode('utf-8')) + 1
        
        return base + "".join([f"{filler_line} ({i})" for i in range(lines_needed)])
    
    def _generate_history_messages(self, count: int) -> List[dict]:
        """Generate simulated history messages"""
        messages = []
        
        for i in range(count):
            # Human message
            messages.append({
                "role": "user",
                "content": f"Previous task {i+1}: Analyze the project structure and provide recommendations."
            })
            
            # Assistant message with tool call
            messages.append({
                "role": "assistant",
                "content": f"I'll analyze the project structure for task {i+1}.",
                "tool_calls": [{
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": "list_dir",
                        "arguments": json.dumps({"path": "/test/project", "tree": True})
                    }
                }]
            })
            
            # Tool result (simulated, ~5KB each)
            tool_result = f"""software-ecommerce/
├── addon/
│   ├── plugin_{i}/
│   ├── config/
│   ├── model/
│   └── service/
├── app/
│   ├── api/
│   ├── model/
│   └── service/
├── config/
├── public/
└── tests/
    └── test_{i}.py

[Directory listing result for task {i+1}. This is simulated content to test context window handling.]"""
            
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": tool_result
            })
        
        return messages
    
    async def _send_request(
        self,
        system_prompt: str,
        history: List[dict],
        user_message: str
    ) -> tuple[float, float, str, bool]:
        """
        Send request to Kimi via Gateway
        
        Returns: (first_token_time, total_time, response_content, success)
        """
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096,
            "stream": False
        }
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        start_time = time.time()
        first_token_time = None
        
        try:
            response = await self.client.post(
                f"{self.gateway_url}/gateway/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            total_time = time.time() - start_time
            
            if response.status_code != 200:
                error_text = response.text[:500]
                return first_token_time or total_time, total_time, error_text, False
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            return first_token_time or total_time, total_time, content, True
            
        except Exception as e:
            total_time = time.time() - start_time
            return first_token_time or total_time, total_time, str(e), False
    
    async def run_test(
        self,
        test_name: str,
        system_size_kb: int,
        history_count: int
    ) -> TestResult:
        """Run a single test case"""
        logger.info(f"\n🧪 Running: {test_name}")
        logger.info(f"   System Prompt: {system_size_kb}KB, History: {history_count} messages")
        
        system_prompt = self._generate_system_prompt(system_size_kb)
        history = self._generate_history_messages(history_count)
        user_message = "Please summarize the project structure based on previous analysis."
        
        first_token_time, total_time, response, success = await self._send_request(
            system_prompt, history, user_message
        )
        
        # Estimate tokens (rough approximation)
        total_chars = len(system_prompt) + sum(len(str(m)) for m in history) + len(user_message)
        estimated_tokens = total_chars // 4
        
        result = TestResult(
            test_name=test_name,
            system_prompt_size=system_size_kb * 1024,
            history_messages=history_count,
            total_tokens=estimated_tokens,
            first_token_time=first_token_time,
            total_time=total_time,
            response_length=len(response),
            success=success,
            error=response if not success else None
        )
        
        self.results.append(result)
        
        if success:
            logger.info(f"   ✅ Success: {total_time:.2f}s (estimated {estimated_tokens} tokens)")
        else:
            logger.info(f"   ❌ Failed: {response[:200]}")
        
        return result
    
    async def run_benchmark(self):
        """Run full benchmark suite"""
        logger.info("=" * 70)
        logger.info("🚀 Kimi Context Optimization Benchmark (Gateway Mode)")
        logger.info("=" * 70)
        logger.info(f"Model: {self.model}")
        logger.info(f"Gateway: {self.gateway_url}")
        logger.info("")
        
        # Test cases with varying context sizes
        test_cases = [
            # Baseline: Small context
            ("Baseline (20KB sys + 0 hist)", 20, 0),
            
            # System prompt size tests
            ("Medium System (40KB + 0 hist)", 40, 0),
            ("Large System (80KB + 0 hist)", 80, 0),
            ("XLarge System (130KB + 0 hist)", 130, 0),
            ("XXLarge System (190KB + 0 hist)", 190, 0),
            
            # History message tests (with fixed 40KB system)
            ("2 History (40KB + 2 hist)", 40, 2),
            ("4 History (40KB + 4 hist)", 40, 4),
            ("6 History (40KB + 6 hist)", 40, 6),
            
            # Combined large context
            ("Large Combined (80KB + 4 hist)", 80, 4),
            
            # Optimized target
            ("Optimized (30KB + 2 hist)", 30, 2),
        ]
        
        for name, sys_size, hist_count in test_cases:
            await self.run_test(name, sys_size, hist_count)
            
            # Wait between tests to avoid rate limiting
            await asyncio.sleep(2)
        
        self._print_summary()
    
    def _print_summary(self):
        """Print test summary"""
        logger.info("\n" + "=" * 70)
        logger.info("📊 Test Summary")
        logger.info("=" * 70)
        print(f"{'Test Name':<35} {'Tokens':<10} {'Time':<10} {'Status':<10}")
        print("-" * 70)
        
        for r in self.results:
            status = "✅" if r.success else "❌"
            print(f"{r.test_name:<35} {r.total_tokens:<10} {r.total_time:>6.1f}s   {status:<10}")
        
        print("\n" + "=" * 70)
        print("💡 Optimization Recommendations")
        print("=" * 70)
        
        # Find reasonable thresholds
        successful = [r for r in self.results if r.success]
        if not successful:
            logger.error("❌ No successful tests to analyze")
            return
        
        # Find time threshold
        fast_tests = [r for r in successful if r.total_time < 60]
        slow_tests = [r for r in successful if r.total_time > 120]
        
        print(f"\n✅ Fast responses (< 60s): {len(fast_tests)} tests")
        for r in fast_tests:
            print(f"   - {r.test_name}: {r.total_time:.1f}s")
        
        print(f"\n⚠️  Slow responses (> 120s): {len(slow_tests)} tests")
        for r in slow_tests:
            print(f"   - {r.test_name}: {r.total_time:.1f}s")
        
        # Recommendations
        print("\n📋 Recommended Context Limits:")
        
        if fast_tests:
            max_tokens = max(r.total_tokens for r in fast_tests)
            max_sys = max(r.system_prompt_size for r in fast_tests)
            max_hist = max(r.history_messages for r in fast_tests)
            print(f"   - Max total tokens: ~{max_tokens:,} (~{max_tokens//4} chars)")
            print(f"   - System prompt: < {max_sys//1024}KB")
            print(f"   - History messages: < {max_hist} pairs")
        
        print("\n🎯 Suggested EvoLoop Constants:")
        print("   DEFAULT_WINDOW_SIZE = 2  # Reduced from 5")
        print("   MAX_CONTEXT_CHARS = 30000  # ~24K tokens")
        print("   CONTEXT_PRUNE_THRESHOLD = 3000")
        print("   Documenter role: 20-30KB system prompt")
    
    async def close(self):
        """Cleanup"""
        await self.client.aclose()


async def quick_test(tester: KimiContextTester):
    """Quick test with specific configurations"""
    
    logger.info("=" * 70)
    logger.info("⚡ Quick Context Test")
    logger.info("=" * 70)
    
    # Test large configuration (190KB)
    logger.info("\n🔴 Testing LARGE configuration (190KB + 6 history)...")
    large = await tester.run_test("Large (190KB + 6 hist)", 190, 6)
    
    # Test current problematic configuration (130KB)
    logger.info("\n🟠 Testing CURRENT configuration (130KB + 6 history)...")
    current = await tester.run_test("Current (130KB + 6 hist)", 130, 6)
    
    # Test proposed optimized configuration (30KB)
    logger.info("\n🟢 Testing OPTIMIZED configuration (30KB + 2 history)...")
    optimized = await tester.run_test("Optimized (30KB + 2 hist)", 30, 2)
    
    # Compare
    logger.info("\n" + "=" * 70)
    logger.info("📈 Comparison")
    logger.info("=" * 70)
    
    if large.success and current.success and optimized.success:
        # Large vs Current
        improvement_large = (large.total_time - current.total_time) / large.total_time * 100
        token_reduction_large = (large.total_tokens - current.total_tokens) / large.total_tokens * 100
        
        # Current vs Optimized
        improvement_opt = (current.total_time - optimized.total_time) / current.total_time * 100
        token_reduction_opt = (current.total_tokens - optimized.total_tokens) / current.total_tokens * 100
        
        print(f"\n📊 190KB → 130KB (Context Reduction)")
        print(f"   Time Improvement: {improvement_large:.1f}%")
        print(f"   Token Reduction: {token_reduction_large:.1f}%")
        print(f"   190KB: {large.total_time:.1f}s ({large.total_tokens:,} tokens)")
        print(f"   130KB: {current.total_time:.1f}s ({current.total_tokens:,} tokens)")
        
        print(f"\n📊 130KB → 30KB (Further Optimization)")
        print(f"   Time Improvement: {improvement_opt:.1f}%")
        print(f"   Token Reduction: {token_reduction_opt:.1f}%")
        print(f"   130KB: {current.total_time:.1f}s ({current.total_tokens:,} tokens)")
        print(f"   30KB:  {optimized.total_time:.1f}s ({optimized.total_tokens:,} tokens)")
        
        print(f"\n📊 Overall (190KB → 30KB)")
        overall_improvement = (large.total_time - optimized.total_time) / large.total_time * 100
        overall_token_reduction = (large.total_tokens - optimized.total_tokens) / large.total_tokens * 100
        print(f"   Total Time Improvement: {overall_improvement:.1f}%")
        print(f"   Total Token Reduction: {overall_token_reduction:.1f}%")
    
    await tester.close()


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kimi Context Optimization Test")
    parser.add_argument("--quick", action="store_true", help="Run quick comparison test")
    parser.add_argument("--full", action="store_true", help="Run full benchmark")
    parser.add_argument("--direct", action="store_true", help="Use direct Kimi API (CompatibleChatAnthropic)")
    parser.add_argument("--local", action="store_true", help="Use local Gateway (http://localhost:9001)")
    
    args = parser.parse_args()
    
    # 检查参数互斥
    mode_count = sum([args.direct, args.local])
    if mode_count > 1:
        logger.error("❌ --direct 和 --local 不能同时使用")
        sys.exit(1)
    
    # 根据模式创建测试器
    if args.direct:
        logger.error("❌ --direct mode not implemented in simplified version")
        sys.exit(1)
    elif args.local:
        logger.info("🚀 使用本地 Gateway 模式 (http://localhost:9001)")
        logger.info("💡 请确保本地 Gateway 已启动: cd member-center/gateway && ./start_local.sh")
        
        # 本地开发模式下，使用任意 token 即可
        token = "local-dev-token-00000000"
        
        local_url = os.getenv("LOCAL_GATEWAY_URL", "http://localhost:9001")
        tester = KimiContextTester(token, gateway_url=local_url)
    else:
        logger.info("🚀 使用远程 Gateway 模式")
        result = await login_and_get_token()
        if not result:
            logger.error("❌ 登录失败，测试无法继续")
            logger.error("\n请确保:")
            logger.error("   1. 在 evoloop/backend 目录下运行")
            logger.error("   2. 账号密码正确 (默认: preterchan/hellomylife)")
            logger.error("   3. 网络连接正常")
            sys.exit(1)
        token, member_id = result
        tester = KimiContextTester(token)
    
    try:
        if args.full:
            await tester.run_benchmark()
        else:
            # Default: quick test
            await quick_test(tester)
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
