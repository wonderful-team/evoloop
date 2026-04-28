#!/usr/bin/env python3
"""
调试 Step 3 的完整执行流程 - 修正版
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


async def main():
    from app.core.execution.macro.verification_models import EnvironmentConfig, AgentConfig
    from app.core.execution.macro.verification_worker import VerificationWorker

    print("=" * 80)
    print("🔍 调试 Step 3 执行流程")
    print("=" * 80)

    env_config = EnvironmentConfig(platform="android", device_id="HYC5T19B11003570")
    agent_config = AgentConfig(enable_screenshot_analysis=True)

    worker = VerificationWorker(env_config, agent_config)
    
    print(f"\n初始化前 _current_platform: {worker._current_platform}")
    print(f"初始化前 _initialized: {worker._initialized}")
    
    await worker.initialize()
    
    print(f"\n初始化后 _current_platform: {worker._current_platform}")
    print(f"初始化后 _initialized: {worker._initialized}")

    # Step 3
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "source": "mobile",
        "payload": {"x": 0.309, "y": 0.268}
    }

    print(f"\n步骤 source: {step.get('source')}")
    print(f"步骤 type: {step.get('type')}")
    
    # 手动路由检查
    source = step.get("source", "dom")
    print(f"\n路由检查:")
    print(f"  source == 'mobile': {source == 'mobile'}")
    print(f"  _current_platform == 'android': {worker._current_platform == 'android'}")
    print(f"  应该路由到: _execute_mobile_step")

    print("\n🚀 执行 Step 3...")
    try:
        result = await worker.execute_step(step)
        print(f"  结果: {result}")
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()

    await worker.cleanup()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
