#!/usr/bin/env python3
"""
完整流程详细调试 - 使用猴子补丁查看内部状态
"""

import os
import sys
import json
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

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


async def debug_full_flow():
    """完整流程调试"""
    print("=" * 70)
    print("🔬 完整流程详细调试")
    print("=" * 70)

    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator
    from app.core.execution.macro.anomaly_detector import AnomalyDetector

    # 只使用 Step 3
    step3_only_macro = [{
        "type": "action",
        "event_type": "tap",
        "source": "mobile",
        "target_selector": "角色",
        "payload": {"x": 0.309, "y": 0.268},
        "step_number": 3
    }]

    request = VerificationRequest(
        macro_script=step3_only_macro,
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=1,
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=2,
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True
        )
    )

    validator = AgentMacroValidator(request)

    # 先初始化 worker
    print("\n🔧 初始化 Worker...")
    worker = await validator._create_worker()
    validator.worker = worker

    # 猴子补丁 capture_state 来查看返回值
    original_capture_state = validator.worker.capture_state

    async def debug_capture_state():
        state = await original_capture_state()
        print(f"   [capture_state] Activity: {state.get('current_activity')}")
        print(f"   [capture_state] Elements: {len(state.get('elements', []))}")
        print(f"   [capture_state] Screenshot: {state.get('screenshot')}")
        return state

    validator.worker.capture_state = debug_capture_state

    # 猴子补丁 detect_post_execution_anomaly
    original_detect_post = validator.anomaly_detector.detect_post_execution_anomaly

    async def debug_detect_post(step, pre_state, post_state, execution_result):
        print(f"   [detect_post] pre_state activity: {pre_state.get('current_activity') if pre_state else None}")
        print(f"   [detect_post] post_state activity: {post_state.get('current_activity') if post_state else None}")
        print(f"   [detect_post] execution_result: {execution_result}")

        result = await original_detect_post(step, pre_state, post_state, execution_result)
        print(f"   [detect_post] is_anomaly: {result.is_anomaly}")
        print(f"   [detect_post] anomaly_type: {result.anomaly_type}")
        return result

    validator.anomaly_detector.detect_post_execution_anomaly = debug_detect_post

    # 执行验证
    print("\n🚀 执行验证...")
    response = await validator.validate()

    print("\n" + "=" * 70)
    print("📊 结果")
    print("=" * 70)

    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]
        print(f"通过: {round_report.passed_steps}")
        print(f"适配: {round_report.adapted_steps}")

        if round_report.step_results:
            for sr in round_report.step_results:
                print(f"\nStep {sr.step_number}: {sr.status}")
                if sr.adaptations:
                    for adapt in sr.adaptations:
                        print(f"  适配: {adapt.reasoning}")
                        if 'payload' in adapt.adapted_strategy:
                            p = adapt.adapted_strategy['payload']
                            if 'x' in p:
                                print(f"  新坐标: ({p['x']}, {p['y']})")
                            if 'original_x' in p:
                                print(f"  原始坐标: ({p['original_x']}, {p['original_y']})")


if __name__ == "__main__":
    asyncio.run(debug_full_flow())
