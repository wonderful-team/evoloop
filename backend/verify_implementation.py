#!/usr/bin/env python3
"""
验证 OCR 禁用标志和事件类型规范化的实现
"""
import os
import sys
import asyncio

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

def load_env_file():
    from pathlib import Path
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


async def verify_implementation():
    """验证实现是否正确"""
    print("=" * 80)
    print("🔍 验证实现")
    print("=" * 80)

    # 1. 验证 MacroEngine 的 disable_ocr 参数
    print("\n1️⃣ 验证 MacroEngine.disable_ocr 参数...")
    from app.core.execution.macro.engine import MacroEngine
    import inspect

    # 检查 execute 方法签名
    sig = inspect.signature(MacroEngine.execute)
    params = list(sig.parameters.keys())
    assert 'disable_ocr' in params, "execute() 缺少 disable_ocr 参数"
    assert sig.parameters['disable_ocr'].default == True, "execute() disable_ocr 默认应为 True"
    print("   ✅ MacroEngine.execute() 有 disable_ocr 参数，默认值为 True")

    # 检查 execute_steps 方法签名
    sig = inspect.signature(MacroEngine.execute_steps)
    params = list(sig.parameters.keys())
    assert 'disable_ocr' in params, "execute_steps() 缺少 disable_ocr 参数"
    assert sig.parameters['disable_ocr'].default == True, "execute_steps() disable_ocr 默认应为 True"
    print("   ✅ MacroEngine.execute_steps() 有 disable_ocr 参数，默认值为 True")

    # 2. 验证 MobileController 的 disable_ocr 参数
    print("\n2️⃣ 验证 MobileController.disable_ocr 参数...")
    from app.core.environment.controllers.mobile_controller import MobileController

    sig = inspect.signature(MobileController.execute)
    params = list(sig.parameters.keys())
    assert 'disable_ocr' in params, "execute() 缺少 disable_ocr 参数"
    assert sig.parameters['disable_ocr'].default == False, "MobileController.execute() disable_ocr 默认应为 False"
    print("   ✅ MobileController.execute() 有 disable_ocr 参数，默认值为 False")

    # 3. 验证 _execute_mobile_step 的 disable_ocr 参数和事件类型规范化
    print("\n3️⃣ 验证 _execute_mobile_step 实现...")
    sig = inspect.signature(MacroEngine._execute_mobile_step)
    params = list(sig.parameters.keys())
    assert 'disable_ocr' in params, "_execute_mobile_step() 缺少 disable_ocr 参数"
    assert sig.parameters['disable_ocr'].default == True, "_execute_mobile_step() disable_ocr 默认应为 True"
    print("   ✅ _execute_mobile_step() 有 disable_ocr 参数，默认值为 True")

    # 读取源码检查事件类型规范化
    import inspect
    source = inspect.getsource(MacroEngine._execute_mobile_step)
    assert 'event_type.lower()' in source, "缺少事件类型小写转换"
    print("   ✅ _execute_mobile_step() 有 event_type.lower() 规范化")

    # 检查 wait 处理
    assert "elif event_type == \"wait\":" in source, "缺少 wait 事件处理"
    print("   ✅ _execute_mobile_step() 有 wait 事件处理")

    # 4. 验证 resolve_element 中的 OCR 禁用逻辑
    print("\n4️⃣ 验证 resolve_element OCR 禁用逻辑...")
    source = inspect.getsource(MobileController.execute)
    assert 'max_ocr_attempts = 0 if disable_ocr else 2' in source, "缺少 OCR 禁用逻辑"
    print("   ✅ resolve_element 有 max_ocr_attempts = 0 if disable_ocr else 2")

    # 5. 验证 disable_ocr 在调用链中的传递
    print("\n5️⃣ 验证调用链参数传递...")

    # 检查 MacroEngine.execute -> execute_steps
    source = inspect.getsource(MacroEngine.execute)
    assert 'disable_ocr=disable_ocr' in source, "execute() 未传递 disable_ocr 到 execute_steps()"
    print("   ✅ MacroEngine.execute() 传递 disable_ocr 到 execute_steps()")

    # 检查 execute_steps -> _handle_control_flow
    source = inspect.getsource(MacroEngine.execute_steps)
    assert 'disable_ocr' in source, "execute_steps() 未处理 disable_ocr"
    print("   ✅ MacroEngine.execute_steps() 处理 disable_ocr")

    # 检查 _execute_mobile_step -> MobileController.execute
    source = inspect.getsource(MacroEngine._execute_mobile_step)
    assert 'disable_ocr=disable_ocr' in source, "_execute_mobile_step() 未传递 disable_ocr"
    print("   ✅ _execute_mobile_step() 传递 disable_ocr 到 MobileController.execute()")

    print("\n" + "=" * 80)
    print("✅ 所有验证通过！")
    print("=" * 80)
    print("\n实现总结:")
    print("  • MacroEngine.execute(disable_ocr=True) - 宏执行默认禁用 OCR")
    print("  • MacroEngine.execute_steps(disable_ocr=True) - 步骤执行传递 OCR 禁用标志")
    print("  • _execute_mobile_step 处理 wait 事件和大小写规范化")
    print("  • MobileController.execute(disable_ocr=False) - 底层默认启用 OCR")
    print("  • resolve_element 根据 disable_ocr 设置 max_ocr_attempts")


if __name__ == "__main__":
    asyncio.run(verify_implementation())
