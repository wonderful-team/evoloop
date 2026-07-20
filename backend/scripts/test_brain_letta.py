import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings

# 1. Override Settings for Real Test
settings.BRAIN_MEMORY_ROOT = ".brain_test_letta"
settings.SSM_API_BASE = "http://localhost:1234/v1" 
settings.SSM_MODEL_NAME = "mamba-codestral-7b-v0.1"

from app.core.brain.kernel import LightningKernel
from app.core.brain.drivers.ssm_driver import SSMDriver
from app.core.brain.drivers.llm_driver import ReflectiveDriver
from app.core.brain.filesystem.manager import BrainFileSystem

# 强制性的 Letta 模式指令
LETTA_GUIDELINES = """
You are a Letta-style AI assistant. You MANAGE your own memory explicitly.
You MUST NOT just say you remembered something. You MUST use commands to write to your memory files.

Available Commands:
1. Update Core Memory (Scratchpad): <cmd>write_file path="working/scratchpad.md" content="[key]: [value]"</cmd>
2. Archive to Knowledge Base: <cmd>write_file path="knowledge/[filename].md" content="[content]"</cmd>

Example:
User: Remember my name is Alex.
Assistant: <cmd>write_file path="working/scratchpad.md" content="User Name: Alex"</cmd> I have updated my core memory.
"""

async def test_letta_memory_v2():
    print(f"🧠 开始 Letta 模式 (增强指令版) 验证...")
    
    # 初始化组件
    fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
    ssm = SSMDriver()
    reflective = ReflectiveDriver()
    kernel = LightningKernel(ssm, fs, reflective)
    
    await kernel.initialize()
    
    print("\n1. 测试：强制要求模型使用 XML 更新记忆")
    user_input = "请使用工具指令，将我的名字叫 Alex 存入 working/scratchpad.md 中。"
    
    print(f"🔹 用户: {user_input}")
    
    # 注入增强型 Prompt
    response = await kernel.step(user_input, system_prompt=LETTA_GUIDELINES)
    
    print(f"🤖 大脑响应: {response}")
    
    # 检查文件系统
    if fs._validate_path("working/scratchpad.md").exists():
        focus_content = fs.read_file("working/scratchpad.md")
        print(f"📂 核心记忆内容 (scratchpad.md): \n{focus_content}")
        if "Alex" in focus_content:
            print("✅ Letta 模式 (V2): 核心记忆物理更新成功！")
        else:
            print("❌ Letta 模式 (V2): 文件存在但内容不匹配。")
    else:
        print("❌ Letta 模式 (V2): 仍然未能触发工具调用生成文件。")

if __name__ == "__main__":
    if os.path.exists(settings.BRAIN_MEMORY_ROOT):
        import shutil
        shutil.rmtree(settings.BRAIN_MEMORY_ROOT)
    asyncio.run(test_letta_memory_v2())
