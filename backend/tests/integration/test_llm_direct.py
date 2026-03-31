"""
直接调用 LLM 测试 - 不经过后端 HTTP API

用于快速验证 LLM 能力，测试成本更低、速度更快

运行：
    export OPENAI_API_KEY=sk-xxx
    python -m pytest tests/integration/test_llm_direct.py -v
"""

import pytest
import os
from openai import AsyncOpenAI

# 检查 API Key
if not os.getenv("OPENAI_API_KEY"):
    pytest.skip("需要设置 OPENAI_API_KEY", allow_module_level=True)

client = AsyncOpenAI()


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_direct_llm_code_generation():
    """
    直接测试 LLM 代码生成能力
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "写一个 Python 函数计算斐波那契数列"}
        ],
        max_tokens=500
    )
    
    content = response.choices[0].message.content
    
    # 验证
    assert "def " in content
    assert "fibonacci" in content.lower() or "fib" in content.lower()
    
    # 提取并执行代码
    import re
    code_match = re.search(r'```python\n(.*?)\n```', content, re.DOTALL)
    if code_match:
        code = code_match.group(1)
        exec_globals = {}
        exec(code, {}, exec_globals)
        
        # 找到函数并测试
        for name, obj in exec_globals.items():
            if callable(obj):
                result = obj(10)
                assert result == 55
                print(f"✅ {name}(10) = {result}")
                break


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_direct_llm_with_scenarios():
    """
    使用场景话术直接测试 LLM
    """
    import sys
    sys.path.insert(0, '/Users/huangjinhuan/项目/develop-assistant.cn/evoloop')
    from test_dialogue_scenarios import CODE_GENERATION_SCENARIOS
    
    scenario = CODE_GENERATION_SCENARIOS[0]  # 斐波那契
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": scenario["cn"]}],
        max_tokens=500
    )
    
    content = response.choices[0].message.content
    print(f"\n输入: {scenario['cn']}")
    print(f"输出: {content[:300]}...")
    
    # 基本验证
    assert len(content) > 50
    assert "def " in content
    
    # 统计 Token 使用量
    print(f"Token 使用: {response.usage.total_tokens}")
    print(f"预估成本: ${response.usage.total_tokens * 0.00000015:.6f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
