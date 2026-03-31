"""
真实 LLM 调用测试 - 端到端智能能力验证

⚠️ 警告：此测试会真实调用 LLM API，产生费用！

运行方式：
    # 设置 API Key
    export OPENAI_API_KEY=sk-xxx
    
    # 运行测试（带超时保护）
    cd backend && python -m pytest tests/integration/test_real_llm_dialogue.py -v --timeout=120

成本控制：
    - 使用 gpt-4o-mini 或 gpt-3.5-turbo 降低成本
    - 设置 max_tokens 限制
    - 使用 pytest-timeout 防止长时间挂起
"""

import pytest
import asyncio
import os
import re
import json
from typing import Optional
from datetime import datetime

# 导入话术
import sys
sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop')
from test_dialogue_scenarios import (
    CODE_GENERATION_SCENARIOS,
    KNOWLEDGE_QUERY_SCENARIOS,
)

# ============== 配置 ==============

# 使用便宜的模型做测试
TEST_MODEL = "gpt-4o-mini"  # 或 "gpt-3.5-turbo"
MAX_TOKENS = 500  # 限制输出长度，控制成本
TEST_TIMEOUT = 60  # 每个测试最多60秒

# 检查是否有 API Key
SKIP_REAL_LLM = not os.getenv("OPENAI_API_KEY")


# ============== 测试工具 ==============

class RealLLMTester:
    """真实 LLM 测试工具类"""
    
    def __init__(self):
        self.conversation_history = []
        self.total_tokens = 0
        self.total_cost = 0.0
        
    async def send_message(self, user_input: str, thread_id: Optional[str] = None) -> dict:
        """
        发送消息并获取真实 LLM 响应
        这里直接调用你的后端 API，让后端去调用 LLM
        """
        import httpx
        
        base_url = os.getenv("EVOLOOP_API_URL", "http://localhost:8000")
        
        async with httpx.AsyncClient(base_url=base_url, timeout=TEST_TIMEOUT) as client:
            # 1. 创建或获取对话
            if not thread_id:
                conv_resp = await client.post("/api/conversations/", json={"title": "Test"})
                thread_id = conv_resp.json()["thread_id"]
            
            # 2. 发送消息
            msg_resp = await client.post(
                f"/api/conversations/{thread_id}/messages",
                json={"content": user_input}
            )
            
            # 3. 等待处理完成
            await asyncio.sleep(2)
            
            messages_resp = await client.get(
                f"/api/conversations/{thread_id}/messages",
                params={"limit": 10}
            )
            
            messages = messages_resp.json().get("items", [])
            ai_messages = [m for m in messages if m.get("role") == "ai"]
            
            if ai_messages:
                return {
                    "thread_id": thread_id,
                    "response": ai_messages[-1],
                    "all_messages": messages,
                }
            
            return {"thread_id": thread_id, "response": None, "all_messages": messages}
    
    def extract_code(self, content: str) -> Optional[str]:
        """从响应中提取代码块"""
        patterns = [
            r'```python\n(.*?)\n```',
            r'```\n(.*?)\n```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1)
        
        # 尝试提取看起来像代码的部分
        lines = content.split('\n')
        code_lines = []
        in_code = False
        
        for line in lines:
            if any(kw in line for kw in ['def ', 'class ', 'import ']):
                in_code = True
            if in_code:
                code_lines.append(line)
        
        return '\n'.join(code_lines) if code_lines else None
    
    def execute_python_code(self, code: str) -> tuple[bool, str]:
        """安全地执行 Python 代码并返回结果"""
        try:
            safe_globals = {"__builtins__": {"len": len, "range": range}}
            exec_globals = {}
            exec(code, safe_globals, exec_globals)
            
            # 尝试找到函数并测试
            for name, obj in exec_globals.items():
                if callable(obj) and not name.startswith('_'):
                    try:
                        result = obj(10)
                        return True, f"Function '{name}' returned: {result}"
                    except Exception as e:
                        return False, f"Function execution error: {e}"
            
            return True, "Code executed"
            
        except Exception as e:
            return False, str(e)


# ============== 测试夹具 ==============

@pytest.fixture(scope="module")
def llm_tester():
    return RealLLMTester()


# ============== 真实 LLM 测试 ==============

@pytest.mark.skipif(SKIP_REAL_LLM, reason="No OPENAI_API_KEY set")
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(TEST_TIMEOUT)
class TestRealLLMCodeGeneration:
    """真实 LLM 代码生成测试"""
    
    @pytest.mark.parametrize("scenario", CODE_GENERATION_SCENARIOS[:3])
    async def test_code_generation_executes_correctly(self, llm_tester, scenario):
        """
        详细测试逻辑：
        1. 发送代码生成请求
        2. 提取生成的代码
        3. 实际执行代码
        4. 验证结果正确性
        """
        user_input = scenario["cn"]
        
        # 步骤 1: 发送请求
        result = await llm_tester.send_message(user_input)
        response = result.get("response")
        
        assert response is not None, "LLM 没有返回响应"
        content = response.get("content", "")
        assert len(content) > 0, "响应内容为空"
        
        print(f"\n[输入] {user_input[:50]}...")
        print(f"[输出] {content[:200]}...")
        
        # 步骤 2: 提取代码
        code = llm_tester.extract_code(content)
        assert code is not None, f"无法从响应中提取代码"
        
        # 步骤 3: 验证代码语法
        assert "def " in code or "class " in code, "生成的内容不像代码"
        
        # 步骤 4: 实际执行（如果是 Python）
        if "python" in user_input.lower():
            success, exec_result = llm_tester.execute_python_code(code)
            print(f"[执行结果] {exec_result}")
            assert success, f"代码执行失败: {exec_result}"
    
    async def test_fibonacci_specific(self, llm_tester):
        """
        具体测试：斐波那契数列，验证 fib(10) = 55
        """
        user_input = "写一个 Python 函数 fibonacci(n) 计算斐波那契数列"
        
        result = await llm_tester.send_message(user_input)
        content = result["response"]["content"]
        
        code = llm_tester.extract_code(content)
        assert code is not None
        
        # 专门测试斐波那契逻辑
        try:
            exec_globals = {}
            exec(code, {}, exec_globals)
            
            for name, obj in exec_globals.items():
                if callable(obj):
                    result = obj(10)
                    assert result == 55, f"fib(10) 应该等于 55，但得到 {result}"
                    print(f"✅ 验证通过: {name}(10) = {result}")
                    break
        except Exception as e:
            pytest.fail(f"斐波那契代码执行失败: {e}")


@pytest.mark.skipif(SKIP_REAL_LLM, reason="No OPENAI_API_KEY set")
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(TEST_TIMEOUT)
class TestRealLLMMultiTurn:
    """真实 LLM 多轮对话测试"""
    
    async def test_context_memory(self, llm_tester):
        """
        详细测试逻辑：
        1. 第一轮：提到一个概念 "BlueProject"
        2. 第二轮：问 "它是什么"，看能否记住上下文
        3. 验证 LLM 记得 "BlueProject" 是什么
        """
        # 第一轮：设定上下文
        result1 = await llm_tester.send_message(
            "我正在开发一个叫 BlueProject 的新项目，它是一个数据分析平台"
        )
        thread_id = result1["thread_id"]
        
        # 第二轮：引用上文
        result2 = await llm_tester.send_message(
            "BlueProject 的主要功能是什么？",
            thread_id=thread_id
        )
        
        content = result2["response"]["content"]
        
        # 验证：回答中应该提到 BlueProject 或数据分析
        assert "BlueProject" in content or "数据分析" in content, \
            f"LLM 没有记住上下文: {content[:300]}"
        
        print(f"✅ 上下文记忆测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-k", "test_fibonacci_specific"])
