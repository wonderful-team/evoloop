#!/usr/bin/env python3
"""
逐步执行日志 - 记录每一步的详细执行信息
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# 配置详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
    print("=" * 100)
    print(f"🔬 Skill 713 逐步执行日志 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    print()

    # 加载 Skill
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return

    macro = skill['macro_script']
    print(f"技能: {skill['name']}")
    print(f"顶层步骤: {len(macro)}")
    print()

    # 初始化 Worker
    from app.core.execution.macro.verification_models import EnvironmentConfig, AgentConfig
    from app.core.execution.macro.verification_worker import VerificationWorker

    env_config = EnvironmentConfig(platform="android", device_id="HYC5T19B11003570")
    agent_config = AgentConfig()

    worker = VerificationWorker(env_config, agent_config)
    print("📱 正在连接手机...")
    await worker.initialize()
    print("✅ 手机连接成功")
    print()
    await asyncio.sleep(1)

    # 执行每一步并记录日志
    step_num = 0
    for i, step in enumerate(macro, 1):
        step_type = step.get('type', 'unknown')
        event_type = step.get('event_type', 'N/A')
        payload = step.get('payload', {})

        print(f"{'='*100}")
        print(f"【STEP {i}】type={step_type}, event_type={event_type}")
        print(f"{'='*100}")

        if step_type == 'loop':
            sub_steps = step.get('steps', [])
            max_iter = step.get('max_iterations', 50)
            condition = step.get('condition', {})
            print(f"  ↳ Loop步骤: 包含 {len(sub_steps)} 个子步骤, max_iterations={max_iter}")
            print(f"  ↳ 条件: {condition}")
            print()

            # 执行 loop
            result = await worker.execute_step(step)
            print()
            print(f"  Loop执行结果: {result.get('status')}")
            print(f"  执行轮数: {result.get('iterations')}")

            if 'results' in result:
                for iter_data in result['results']:
                    print(f"\n  --- 第 {iter_data['iteration']} 轮 ---")
                    for step_result in iter_data.get('steps', []):
                        step_idx = step_result.get('step', 0)
                        res = step_result.get('result', '')
                        print(f"    Step {step_idx}: {str(res)[:100]}")

        else:
            # 显示详细参数
            if 'package' in payload:
                print(f"  ↳ 包名: {payload['package']}")
            if 'x' in payload and 'y' in payload:
                x, y = payload['x'], payload['y']
                if x < 1 and y < 1:
                    print(f"  ↳ 相对坐标: ({x}, {y}) -> 将转换为绝对坐标")
                else:
                    print(f"  ↳ 绝对坐标: ({int(x)}, {int(y)})")
            if 'seconds' in payload:
                print(f"  ↳ 等待时间: {payload['seconds']} 秒")
            if 'selector' in payload:
                print(f"  ↳ 选择器: {payload['selector']}")
            print()

            # 执行步骤
            start_time = asyncio.get_event_loop().time()
            result = await worker.execute_step(step)
            elapsed = asyncio.get_event_loop().time() - start_time

            print(f"  执行耗时: {elapsed:.2f} 秒")
            print(f"  结果: {result}")

        print()
        await asyncio.sleep(0.5)

    print("=" * 100)
    print("✅ 所有步骤执行完成")
    print("=" * 100)

    await worker.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
