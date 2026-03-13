#!/usr/bin/env python3
"""
测试修复后的 Agent 验证流程
"""

import os
import sys
import json
import asyncio
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


async def get_skill_from_db(skill_id: int = 713):
    try:
        import asyncpg
        pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_db = os.environ.get("POSTGRES_DB", "app")
        pg_user = os.environ.get("POSTGRES_USER", "postgres")
        pg_password = os.environ.get("POSTGRES_PASSWORD", "")
        db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

        conn = await asyncpg.connect(db_url)
        row = await conn.fetchrow(
            "SELECT macro_script FROM learned_skills WHERE id = $1", skill_id
        )
        await conn.close()

        if row:
            macro = row['macro_script']
            if isinstance(macro, str):
                macro = json.loads(macro)
            return macro
        return None
    except Exception as e:
        print(f"❌ Database error: {e}")
        return None


async def main():
    print("=" * 80)
    print("🔬 测试修复后的 Agent 验证流程")
    print("=" * 80)
    print()

    macro_script = await get_skill_from_db(713)
    if not macro_script:
        print("❌ 无法加载 skill")
        return

    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    request = VerificationRequest(
        macro_script=macro_script,
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
    print("🔧 AgentMacroValidator 初始化完成")
    print("   - 支持 Vision LLM 分析截图")
    print("   - 支持坐标自动修正")
    print()

    try:
        response = await validator.validate()
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return

    print()
    print("=" * 80)
    print("📊 验证结果")
    print("=" * 80)
    print(f"成功: {response.success}")
    print(f"状态: {response.status}")
    print(f"置信度: {response.confidence_score}")
    print(f"执行模式: {response.execution_mode}")
    print(f"耗时: {response.processing_time_seconds:.2f} 秒")

    if response.verification_report:
        report = response.verification_report
        print(f"\n检测到的异常: {report.summary.total_anomalies_detected}")
        print(f"应用的适配: {report.summary.total_adaptations_applied}")

        for round_report in report.rounds:
            print(f"\n{round_report.round_name}:")
            print(f"  通过: {round_report.passed_steps} / 适配: {round_report.adapted_steps} / 失败: {round_report.failed_steps}")

            for sr in round_report.step_results:
                status_icon = "✅" if sr.status == "passed" else "🔧" if sr.status == "adapted" else "❌"
                print(f"\n  {status_icon} Step {sr.step_number}: {sr.status}")

                # 显示适配详情
                if sr.adaptations:
                    for adapt in sr.adaptations:
                        print(f"    └─ 适配: {adapt.reasoning}")
                        # 显示坐标修正
                        adapted_payload = adapt.adapted_strategy.get("payload", {})
                        if "original_x" in adapted_payload:
                            orig_x = adapted_payload.get("original_x")
                            orig_y = adapted_payload.get("original_y")
                            new_x = adapted_payload.get("x")
                            new_y = adapted_payload.get("y")
                            print(f"       坐标修正: ({orig_x:.3f}, {orig_y:.3f}) -> ({new_x:.3f}, {new_y:.3f})")

    # 显示进化后的宏
    if response.evolved_macro:
        print("\n" + "=" * 80)
        print("🧬 进化后的宏脚本")
        print("=" * 80)
        for i, step in enumerate(response.evolved_macro, 1):
            event_type = step.get("event_type", step.get("type", "unknown"))
            payload = step.get("payload", {})
            print(f"\nStep {i}: {event_type}")
            if "x" in payload and "y" in payload:
                print(f"  坐标: ({payload['x']:.3f}, {payload['y']:.3f})")
            if "original_x" in payload:
                print(f"  原始坐标: ({payload['original_x']:.3f}, {payload['original_y']:.3f})")


if __name__ == "__main__":
    asyncio.run(main())
