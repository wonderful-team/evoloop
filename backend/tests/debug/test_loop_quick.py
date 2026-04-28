#!/usr/bin/env python3
"""
快速测试 - 验证 Loop 子步骤是否被验证
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


async def test_loop_validation():
    """测试 Loop 子步骤验证"""
    print("=" * 70)
    print("🔄 Loop 子步骤验证测试")
    print("=" * 70)

    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    # 模拟 Skill 713 的简化版 loop - 只有3个子步骤
    # 直接从 loop 开始测试（假设已经在微信中）
    test_macro = [
        {
            "type": "loop",
            "steps": [
                {"type": "action", "event_type": "tap", "source": "mobile", "target_selector": "first_character_card", "payload": {"x": 0.5, "y": 0.5}, "step_number": 1},
                {"type": "action", "event_type": "wait", "source": "mobile", "payload": {"duration_ms": 1000}, "step_number": 2},
                {"type": "action", "event_type": "tap", "source": "mobile", "target_selector": "back_button", "payload": {"x": 0.1, "y": 0.1}, "step_number": 3},
            ],
            "max_iterations": 3,
            "step_number": 1
        }
    ]

    print(f"\n📋 测试宏结构:")
    print(f"   Step 1: loop (包含 {len(test_macro[0]['steps'])} 个子步骤)")

    request = VerificationRequest(
        macro_script=test_macro,
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

    # 添加日志输出
    original_execute_loop = validator._execute_loop_with_adaptation

    async def debug_execute_loop(step, step_number, round_config, result):
        print(f"\n🔄 [Loop 验证开始] Step {step_number} 有 {len(step.get('steps', []))} 个子步骤")
        sub_results = await original_execute_loop(step, step_number, round_config, result)
        print(f"✅ [Loop 验证完成] Step {step_number} 完成，收集到 {len(result.adaptations)} 个适配记录")
        return sub_results

    validator._execute_loop_with_adaptation = debug_execute_loop

    print("\n🚀 开始验证...")
    response = await validator.validate()

    print("\n" + "=" * 70)
    print("📊 验证结果")
    print("=" * 70)
    print(f"整体成功: {response.success}")
    print(f"状态: {response.status}")

    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]
        print(f"\n步骤统计:")
        print(f"  通过: {round_report.passed_steps}")
        print(f"  适配: {round_report.adapted_steps}")
        print(f"  失败: {round_report.failed_steps}")

        print(f"\n详细结果:")
        for sr in round_report.step_results:
            step_num = sr.step_number
            step = sr.original_step
            step_type = step.get('type', 'action')
            event_type = step.get('event_type', 'unknown')

            status_icon = "✅" if str(sr.status.value) == "passed" else "🔧" if str(sr.status.value) == "adapted" else "❌"
            print(f"\n{status_icon} Step {step_num}: [{step_type}] {event_type} - {sr.status.value}")

            if sr.adaptations:
                print(f"   Agent 介入 ({len(sr.adaptations)} 次):")
                for i, adapt in enumerate(sr.adaptations, 1):
                    print(f"     {i}. {adapt.reasoning[:60]}...")

    print("\n" + "=" * 70)
    print("✅ Loop 子步骤验证已启用！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_loop_validation())
