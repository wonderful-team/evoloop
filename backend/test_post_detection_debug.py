#!/usr/bin/env python3
"""
执行后异常检测调试
"""

import os
import sys
import json
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


async def test_post_detection():
    """测试执行后异常检测"""
    print("=" * 70)
    print("🔬 执行后异常检测调试")
    print("=" * 70)

    from app.core.execution.macro.verification_models import (
        EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.verification_worker import VerificationWorker
    from app.core.execution.macro.anomaly_detector import AnomalyDetector

    # 初始化 Worker
    env_config = EnvironmentConfig(
        platform="android",
        device_id="HYC5T19B11003570"
    )
    agent_config = AgentConfig(
        llm_model="gpt-4o",
        max_retries_per_step=2,
        allow_strategy_adaptation=True,
        enable_screenshot_analysis=True
    )

    worker = VerificationWorker(env_config, agent_config)
    await worker.initialize()
    print("✅ Worker 初始化成功")

    # Step 3
    step3 = {
        "type": "action",
        "event_type": "tap",
        "source": "mobile",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268},
        "step_number": 3
    }

    # 捕获执行前状态
    print("\n📸 捕获执行前状态...")
    pre_state = await worker.capture_state()
    print(f"   Activity: {pre_state.get('current_activity')}")
    print(f"   Elements数量: {len(pre_state.get('elements', []))}")
    print(f"   Screenshot: {pre_state.get('screenshot')}")

    # 执行 Step 3
    print("\n▶️ 执行 Step 3...")
    result = await worker.execute_step(step3)
    print(f"   结果: {result}")

    # 等待
    await asyncio.sleep(2)

    # 捕获执行后状态
    print("\n📸 捕获执行后状态...")
    post_state = await worker.capture_state()
    print(f"   Activity: {post_state.get('current_activity')}")
    print(f"   Elements数量: {len(post_state.get('elements', []))}")
    print(f"   Screenshot: {post_state.get('screenshot')}")

    # 手动调用执行后异常检测
    print("\n🔍 手动调用执行后异常检测...")
    detector = AnomalyDetector()

    # 检查 _check_state_change
    print("\n   _check_state_change 检查:")
    pre_elements = set(str(e) for e in pre_state.get("elements", []))
    post_elements = set(str(e) for e in post_state.get("elements", []))
    print(f"   pre_elements数量: {len(pre_elements)}")
    print(f"   post_elements数量: {len(post_elements)}")
    print(f"   是否相等: {pre_elements == post_elements}")

    pre_activity = pre_state.get("current_activity")
    post_activity = post_state.get("current_activity")
    print(f"   pre_activity: {pre_activity}")
    print(f"   post_activity: {post_activity}")
    print(f"   activity是否相等: {pre_activity == post_activity}")

    state_changed = detector._check_state_change(pre_state, post_state)
    print(f"   _check_state_change 结果: {state_changed}")

    # 调用完整的 detect_post_execution_anomaly
    print("\n   调用 detect_post_execution_anomaly...")
    post_anomaly = await detector.detect_post_execution_anomaly(
        step=step3,
        pre_state=pre_state,
        post_state=post_state,
        execution_result=result
    )
    print(f"   是否异常: {post_anomaly.is_anomaly}")
    print(f"   异常类型: {post_anomaly.anomaly_type}")
    print(f"   置信度: {post_anomaly.confidence}")
    print(f"   详情: {json.dumps(post_anomaly.details, ensure_ascii=False, indent=2)}")
    print(f"   建议操作: {post_anomaly.suggested_action}")

    await worker.cleanup()
    print("\n✅ 调试完成")


if __name__ == "__main__":
    try:
        asyncio.run(test_post_detection())
    except Exception as e:
        print(f"\n❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
