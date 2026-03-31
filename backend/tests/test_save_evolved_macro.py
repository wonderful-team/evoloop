#!/usr/bin/env python3
"""
测试保存增强宏到数据库
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


async def save_evolved_macro():
    """验证并保存增强宏"""

    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator
    import asyncpg

    # 从数据库加载原始宏
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        "SELECT id, name, macro_script FROM learned_skills WHERE id = $1",
        713
    )

    macro_script = json.loads(row['macro_script']) if isinstance(row['macro_script'], str) else row['macro_script']

    print("=" * 80)
    print("🧪 验证并保存增强宏")
    print("=" * 80)
    print(f"\n原始 Skill: {row['name']} (ID: {row['id']})")
    print(f"原始宏步骤数: {len(macro_script)}")

    # 简化 loop 用于测试
    simplified_macro = macro_script.copy()
    for step in simplified_macro:
        if step.get('type') == 'loop':
            original_sub_steps = step.get('steps', [])
            step['steps'] = original_sub_steps[:3]
            print(f"Loop 简化: {len(original_sub_steps)} -> 3 个子步骤")

    # 运行验证
    request = VerificationRequest(
        macro_script=simplified_macro,
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

    print(f"\n📊 验证结果:")
    print(f"  成功: {response.success}")
    print(f"  状态: {response.status}")
    print(f"  执行模式: {response.execution_mode}")
    print(f"  置信度: {response.confidence_score:.2f}")

    # 保存增强宏到数据库（替换 macro_script）
    if response.evolved_macro:
        print(f"\n💾 保存增强宏到数据库...")
        print(f"  增强宏步骤数: {len(response.evolved_macro)}")

        # 先将原始宏备份到 validation_report
        await conn.execute(
            """UPDATE learned_skills
               SET validation_report = jsonb_build_object(
                   'original_macro', macro_script::jsonb,
                   'evolved_at', NOW()
               ),
                   macro_script = $1,
                   execution_mode = $2,
                   confidence_score = $3,
                   updated_at = NOW()
               WHERE id = $4""",
            json.dumps(response.evolved_macro),
            response.execution_mode.value if hasattr(response.execution_mode, 'value') else str(response.execution_mode),
            response.confidence_score,
            713
        )

        print(f"  ✅ 已保存到 macro_script 字段（原始宏备份到 validation_report）")

        # 显示增强宏内容
        print(f"\n📝 增强宏内容:")
        for i, step in enumerate(response.evolved_macro, 1):
            step_type = step.get('type', 'action')
            event_type = step.get('event_type', step.get('action', 'unknown'))
            target = step.get('target_selector', 'N/A')
            payload = step.get('payload', {})

            print(f"\n  Step {i}: [{step_type.upper()}] {event_type}")

            # 显示增强属性
            if 'original_x' in payload:
                print(f"    📌 坐标修正: ({payload['original_x']:.3f}, {payload['original_y']:.3f}) -> ({payload['x']:.3f}, {payload['y']:.3f})")
            if 'stabilization_ms' in payload:
                print(f"    ⏱️ 稳定等待: {payload['stabilization_ms']}ms")
            if 'max_retries' in payload:
                print(f"    🔄 最大重试: {payload['max_retries']}次")
            if 'retry_delay_ms' in payload:
                print(f"    ⏳ 重试延迟: {payload['retry_delay_ms']}ms")
    else:
        print(f"\n❌ 未生成增强宏")

    await conn.close()

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(save_evolved_macro())
