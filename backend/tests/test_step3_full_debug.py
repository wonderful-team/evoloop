#!/usr/bin/env python3
"""
Step 3 完整流程调试 - 使用 AgentMacroValidator 但只执行 Step 3
"""

import os
import sys
import json
import asyncio
import logging

logging.basicConfig(
    level=logging.DEBUG,
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
            "SELECT id, name, status, execution_mode, confidence_score, macro_script FROM learned_skills WHERE id = $1",
            skill_id
        )
        await conn.close()

        if row:
            macro_script_data = row['macro_script']
            if isinstance(macro_script_data, str):
                macro_script = json.loads(macro_script_data)
            else:
                macro_script = macro_script_data

            return {
                'id': row['id'],
                'name': row['name'],
                'status': row['status'],
                'execution_mode': row['execution_mode'],
                'confidence_score': row['confidence_score'],
                'macro_script': macro_script
            }
        return None
    except Exception as e:
        print(f"❌ Database query failed: {e}")
        return None


async def debug_step3():
    """使用 AgentMacroValidator 执行只有 Step 3 的宏"""
    print("=" * 70)
    print("🔬 Step 3 完整流程调试")
    print("=" * 70)

    # 1. 加载 Skill
    print("\n📦 加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    # 只使用 Step 3
    step3_only_macro = [skill['macro_script'][2]]
    print(f"\n📋 测试宏 (仅 Step 3):")
    print(json.dumps(step3_only_macro, indent=2, ensure_ascii=False))

    # 2. 创建 VerificationRequest
    print("\n📋 创建 VerificationRequest...")
    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )

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

    # 3. 执行验证
    print("\n🚀 执行验证...")
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    validator = AgentMacroValidator(request)

    # 添加自定义日志来跟踪 Step 3
    original_execute_step_with_adaptation = validator._execute_step_with_adaptation

    async def debug_execute_step_with_adaptation(step, step_number, round_config):
        print(f"\n{'─' * 70}")
        print(f"🔄 _execute_step_with_adaptation 被调用 (Step {step_number})")
        print(f"   Step 内容: {json.dumps(step, ensure_ascii=False)}")

        result = await original_execute_step_with_adaptation(step, step_number, round_config)

        print(f"\n📊 Step {step_number} 结果:")
        print(f"   Status: {result.status}")
        print(f"   Adaptations: {len(result.adaptations)}")
        for i, adapt in enumerate(result.adaptations):
            print(f"     [{i+1}] Success: {adapt.success}, Reason: {adapt.reasoning[:80]}")
        print(f"{'─' * 70}")
        return result

    validator._execute_step_with_adaptation = debug_execute_step_with_adaptation

    try:
        response = await validator.validate()
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. 显示结果
    print("\n" + "=" * 70)
    print("📊 验证结果")
    print("=" * 70)

    print(f"成功: {response.success}")
    print(f"状态: {response.status}")
    print(f"置信度: {response.confidence_score}")

    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]
        print(f"\n轮次详情:")
        print(f"  通过: {round_report.passed_steps}")
        print(f"  适配: {round_report.adapted_steps}")
        print(f"  失败: {round_report.failed_steps}")

        if round_report.step_results:
            for sr in round_report.step_results:
                print(f"\n  Step {sr.step_number}: {sr.status}")
                if sr.adaptations:
                    for adapt in sr.adaptations:
                        print(f"    └─ 适配: {adapt.reasoning}")
                        print(f"       成功: {adapt.success}")
                        print(f"       适配后步骤: {json.dumps(adapt.adapted_strategy, ensure_ascii=False, indent=6)[:200]}...")

    # 显示增强宏
    print("\n🧬 增强宏:")
    if response.evolved_macro:
        for i, step in enumerate(response.evolved_macro, 1):
            print(f"  {i}. {step.get('event_type', 'unknown')}")
            if 'payload' in step:
                payload = step['payload']
                if 'x' in payload and 'y' in payload:
                    print(f"     坐标: ({payload['x']}, {payload['y']})")
                if 'original_x' in payload:
                    print(f"     原始坐标: ({payload['original_x']}, {payload['original_y']})")
    else:
        print("  未生成增强宏")

    return True


if __name__ == "__main__":
    try:
        asyncio.run(debug_step3())
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户取消")
    except Exception as e:
        print(f"\n❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
