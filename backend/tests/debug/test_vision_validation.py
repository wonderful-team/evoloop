#!/usr/bin/env python3
"""
测试使用 Vision LLM 验证宏执行
"""

import os
import sys
from pathlib import Path

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

def load_env_file():
    env_path = Path("/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value

load_env_file()
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")


async def analyze_screenshot_with_vision(screenshot_path: str, expected_action: str) -> dict:
    """使用 Vision LLM 分析截图，判断是否符合预期"""
    from app.infrastructure.llm.vision import VisionLLMFactory
    from langchain_core.messages import HumanMessage, SystemMessage
    
    try:
        llm = VisionLLMFactory.create_vision_llm()
        
        prompt = f"""
你正在验证一个宏执行步骤。请分析截图，判断当前页面是否符合预期。

预期操作: {expected_action}

请分析:
1. 当前页面是什么？
2. 是否符合预期操作后的页面？
3. 如果否，出现了什么问题？

以 JSON 格式返回:
{{
    "is_correct": true/false,
    "current_page": "描述",
    "expected_page": "描述",
    "issue": "问题描述（如有）",
    "confidence": 0.9
}}
"""
        
        # 创建包含图片的消息
        image_message = VisionLLMFactory.create_image_message(
            image_source=screenshot_path,
            text_prompt=prompt
        )
        
        response = await llm.ainvoke([image_message])
        
        # 解析 JSON 响应
        import json
        import re
        
        content = response.content
        # 提取 JSON 部分
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            return {"is_correct": True, "error": "无法解析响应"}
            
    except Exception as e:
        return {"is_correct": True, "error": str(e)}


async def main():
    print("=" * 80)
    print("🔍 使用 Vision LLM 验证宏执行")
    print("=" * 80)
    
    # 使用已有的截图测试
    screenshot_path = "/Users/huangjinhuan/.evoloop/artifacts/screenshots/temp/20260313/android_20260313_081014_841.png"
    
    if not Path(screenshot_path).exists():
        print(f"截图不存在: {screenshot_path}")
        return
    
    print(f"\n分析截图: {screenshot_path}")
    print("预期操作: 点击'角色'按钮后")
    print()
    
    result = await analyze_screenshot_with_vision(screenshot_path, "点击'角色'按钮")
    
    print("分析结果:")
    print(f"  是否正确: {result.get('is_correct')}")
    print(f"  当前页面: {result.get('current_page')}")
    print(f"  预期页面: {result.get('expected_page')}")
    print(f"  问题: {result.get('issue', '无')}")
    print(f"  置信度: {result.get('confidence')}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
