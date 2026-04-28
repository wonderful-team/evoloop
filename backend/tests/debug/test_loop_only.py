#!/usr/bin/env python3
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

async def test_loop():
    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    # 只测试 Step 5 (loop) - 简化版，3个子步骤
    loop_only = [{
        "type": "loop",
        "steps": [
            {"type": "action", "event_type": "tap", "target_selector": "first_character_card", "payload": {"x": 0.5, "y": 0.5}},
            {"type": "action", "event_type": "wait", "payload": {"duration_ms": 1000}},
            {"type": "action", "event_type": "extract", "target_selector": "price", "payload": {}}
        ],
        "max_iterations": 10,
        "step_number": 5
    }]

    request = VerificationRequest(
        macro_script=loop_only,
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
    response = await validator.validate()

    print("\n" + "=" * 70)
    print("Loop 验证结果")
    print("=" * 70)
    print(f"成功: {response.success}")
    print(f"状态: {response.status}")

    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]
        print(f"\n步骤统计: 通过={round_report.passed_steps}, 适配={round_report.adapted_steps}, 失败={round_report.failed_steps}")

        for sr in round_report.step_results:
            step_num = sr.step_number
            step = sr.original_step
            step_type = step.get('type', 'action')
            print(f"\nStep {step_num}: [{step_type}] - {sr.status.value}")
            if sr.adaptations:
                print(f"  适配次数: {len(sr.adaptations)}")
                for a in sr.adaptations:
                    print(f"    - {a.reasoning[:80]}")

asyncio.run(test_loop())
