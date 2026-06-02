import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings

# 1. Override Settings for Real Test
settings.BRAIN_MEMORY_ROOT = ".brain_test_real"
settings.SSM_API_BASE = "http://localhost:1234/v1" 
settings.SSM_MODEL_NAME = "mamba-codestral-7b-v0.1" # Matches user's model

from app.core.brain.drivers.ssm_driver import SSMDriver

async def test_real_conversation():
    print(f"🔥 开始真机多轮对话验证 (地址: {settings.SSM_API_BASE})...")
    print(f"   模型: {settings.SSM_MODEL_NAME}")
    
    driver = SSMDriver()
    await driver.initialize()
    
    if driver.mode != "active":
        print(f"❌ 连接失败！驱动模式为: {driver.mode}")
        return

    print("✅ 连接成功！开始中文对话测试...\n")

    # 对话历史
    history = ""
    turns = [
        "你好，我是一名正在测试你记忆能力的开发者。",
        "你还记得我的职业是什么吗？",
        "请帮我用 Python 写一个计算斐波那契数列的函数。"
    ]

    for i, user_input in enumerate(turns):
        print(f"🔹 [第 {i+1} 轮] 用户: {user_input}")
        
        try:
            # 生成回复
            response = await driver.generate(
                context=history, 
                user_input=user_input,
                system_prompt="你是一个名为 EvoLoop 的专业编程助手，请用中文回答。"
            )
            
            print(f"🤖 [第 {i+1} 轮] 大脑: {response}\n")
            
            # 更新历史
            history += f"User: {user_input}\nAssistant: {response}\n"
            
        except Exception as e:
            print(f"❌ 第 {i+1} 轮推理失败: {e}")
            break

    print("-" * 40)
    print("✅ 中文多轮对话验证完成！")

if __name__ == "__main__":
    asyncio.run(test_real_conversation())
