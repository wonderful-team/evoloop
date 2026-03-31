#!/usr/bin/env python3
"""
调试 Step 3 的完整执行流程
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
    await worker.initialize()

    # Step 3
    step = {
        "type": "action",
        "event_type": "tap",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268}
    }

    print("\n📸 捕获执行前状态...")
    pre_state = await worker.capture_state()
    print(f"  当前应用: {pre_state.get('package_name')}")
    print(f"  截图路径: {pre_state.get('screenshot')}")

    print("\n🚀 执行 Step 3: 点击'角色'...")
    result = await worker.execute_step(step)
    print(f"  结果: {result}")

    print("\n📸 捕获执行后状态...")
    post_state = await worker.capture_state()
    print(f"  当前应用: {post_state.get('package_name')}")
    print(f"  截图路径: {post_state.get('screenshot')}")

    # 检测异常
    print("\n🔍 执行异常检测...")
    from app.core.execution.macro.anomaly_detector import AnomalyDetector
    detector = AnomalyDetector()

    anomaly = await detector.detect_post_execution_anomaly(
        step, pre_state, post_state, result
    )

    print(f"  is_anomaly: {anomaly.is_anomaly}")
    print(f"  type: {anomaly.anomaly_type}")
    print(f"  details: {anomaly.details}")

    if anomaly.is_anomaly and anomaly.details.get("vision_analysis"):
        print("\n  ✅ Vision LLM 检测到异常，准备触发 adaptation...")

        # 测试 adaptation
        from app.core.execution.macro.adaptation_library import AdaptationStrategyLibrary
        lib = AdaptationStrategyLibrary(use_llm=True)

        record = await lib.adapt(
            step=step,
            anomaly_type=anomaly.anomaly_type,
            anomaly_details=anomaly.details,
            ui_state=post_state
        )

        print(f"\n  Adaptation 结果:")
        print(f"    success: {record.success}")
        print(f"    reasoning: {record.reasoning}")

        adapted_payload = record.adapted_strategy.get("payload", {})
        if "original_x" in adapted_payload:
            print(f"    坐标修正: ({adapted_payload['original_x']:.3f}, {adapted_payload['original_y']:.3f}) -> ({adapted_payload['x']:.3f}, {adapted_payload['y']:.3f})")
        else:
            print(f"    ⚠️ 没有坐标修正!")

    await worker.cleanup()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
