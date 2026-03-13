#!/usr/bin/env python3
"""
真实执行测试 - 显示 Skill 713 每一步的执行
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
            "SELECT id, name, macro_script FROM learned_skills WHERE id = $1",
            skill_id
        )
        await conn.close()

        if row:
            macro = row['macro_script']
            if isinstance(macro, str):
                macro = json.loads(macro)
            return {'name': row['name'], 'macro_script': macro}
        return None
    except Exception as e:
        print(f"❌ Database error: {e}")
        return None


async def main():
    print("=" * 80)
    print("🔬 Skill 713 真实执行测试")
    print("=" * 80)

    # 加载 Skill
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return

    print(f"\n技能名称: {skill['name']}")
    macro = skill['macro_script']

    # 计算总步骤数
    total_steps = 0
    for step in macro:
        if step.get('type') == 'loop' and 'steps' in step:
            total_steps += 1 + len(step['steps'])  # loop本身 + 子步骤
        else:
            total_steps += 1

    print(f"顶层步骤数: {len(macro)}")
    print(f"总步骤数（含子步骤）: {total_steps}")
    print()

    # 初始化 Worker
    from app.core.execution.macro.verification_models import EnvironmentConfig, AgentConfig
    from app.core.execution.macro.verification_worker import VerificationWorker

    env_config = EnvironmentConfig(platform="android", device_id="HYC5T19B11003570")
    agent_config = AgentConfig()

    worker = VerificationWorker(env_config, agent_config)
    print("📱 连接手机...")
    await worker.initialize()
    print("✅ 连接成功\n")

    # 执行每一步
    executed_count = 0
    for i, step in enumerate(macro, 1):
        step_type = step.get('type', 'unknown')
        event_type = step.get('event_type', 'N/A')
        source = step.get('source', 'unknown')

        print(f"{'─' * 80}")
        print(f"Step {i}: type={step_type}, event_type={event_type}, source={source}")

        if step_type == 'loop':
            sub_steps = step.get('steps', [])
            max_iter = step.get('max_iterations', 50)
            print(f"   [Loop] 包含 {len(sub_steps)} 个子步骤, max_iterations={max_iter}")

            # 显示子步骤
            for j, sub in enumerate(sub_steps, 1):
                sub_type = sub.get('type', 'unknown')
                sub_event = sub.get('event_type', 'N/A')
                print(f"   - Sub-step {j}: {sub_event} ({sub_type})")

        # 执行步骤
        try:
            result = await worker.execute_step(step)
            executed_count += 1
            status = "✅" if "error" not in str(result).lower() else "⚠️"
            print(f"   {status} 执行结果: {str(result)[:200]}")
        except Exception as e:
            print(f"   ❌ 执行失败: {e}")

        print()
        await asyncio.sleep(0.5)

    print(f"{'=' * 80}")
    print(f"执行完成: {executed_count}/{len(macro)} 顶层步骤")

    await worker.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
