#!/usr/bin/env python3
"""
详细验证流程测试 - 显示每一步的执行详情
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

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


async def test_worker_directly():
    """直接测试 VerificationWorker 执行每一步"""
    print("=" * 70)
    print("🔬 直接测试 VerificationWorker - 逐步执行")
    print("=" * 70)

    # 1. 加载 skill
    print("\n🗄️  加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    print(f"✅ 加载成功: {skill['name']}")
    macro_script = skill['macro_script']
    print(f"   步骤数: {len(macro_script)}")

    # 显示每一步
    for i, step in enumerate(macro_script, 1):
        print(f"\n   Step {i}: {json.dumps(step, ensure_ascii=False, indent=4)}")

    # 2. 创建 Worker
    print("\n" + "=" * 70)
    print("🔧 初始化 VerificationWorker")
    print("=" * 70)

    from app.core.execution.macro.verification_models import (
        EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.verification_worker import VerificationWorker

    env_config = EnvironmentConfig(
        platform="android",
        device_id="HYC5T19B11003570"
    )
    agent_config = AgentConfig(
        llm_model="gpt-4o",
        max_retries_per_step=2,
        allow_strategy_adaptation=True
    )

    worker = VerificationWorker(env_config, agent_config)

    try:
        print("\n📱 连接手机...")
        await worker.initialize()
        print("✅ Worker 初始化成功")
    except Exception as e:
        print(f"❌ Worker 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3. 执行每一步
    print("\n" + "=" * 70)
    print("▶️  开始执行宏步骤")
    print("=" * 70)

    results = []

    for i, step in enumerate(macro_script, 1):
        print(f"\n{'─' * 70}")
        print(f"Step {i}/{len(macro_script)}: {step.get('event_type', 'unknown')}")
        print(f"{'─' * 70}")

        # 捕获执行前状态
        print("📸 捕获执行前状态...")
        try:
            pre_state = await worker.capture_state()
            print(f"   当前应用: {pre_state.get('package_name', 'unknown')}")
            print(f"   Activity: {pre_state.get('current_activity', 'unknown')}")
        except Exception as e:
            print(f"   ⚠️  捕获状态失败: {e}")
            pre_state = {}

        # 执行步骤
        print(f"\n🚀 执行步骤...")
        start_time = asyncio.get_event_loop().time()

        try:
            result = await worker.execute_step(step)
            elapsed = asyncio.get_event_loop().time() - start_time

            print(f"   执行时间: {elapsed:.2f}秒")
            print(f"   结果: {json.dumps(result, ensure_ascii=False, default=str)[:500]}")

            results.append({
                'step': i,
                'event_type': step.get('event_type'),
                'success': 'error' not in str(result).lower(),
                'result': result
            })

        except Exception as e:
            elapsed = asyncio.get_event_loop().time() - start_time
            print(f"   ❌ 执行失败 ({elapsed:.2f}秒): {e}")
            import traceback
            traceback.print_exc()

            results.append({
                'step': i,
                'event_type': step.get('event_type'),
                'success': False,
                'error': str(e)
            })

        # 等待一下让操作完成
        await asyncio.sleep(1)

        # 捕获执行后状态
        print("\n📸 捕获执行后状态...")
        try:
            post_state = await worker.capture_state()
            print(f"   当前应用: {post_state.get('package_name', 'unknown')}")
            print(f"   Activity: {post_state.get('current_activity', 'unknown')}")
        except Exception as e:
            print(f"   ⚠️  捕获状态失败: {e}")

    # 4. 清理
    print("\n" + "=" * 70)
    print("🧹 清理资源")
    print("=" * 70)
    await worker.cleanup()
    print("✅ 清理完成")

    # 5. 总结
    print("\n" + "=" * 70)
    print("📊 执行总结")
    print("=" * 70)

    success_count = sum(1 for r in results if r.get('success'))
    print(f"成功: {success_count}/{len(results)}")

    for r in results:
        status = "✅" if r.get('success') else "❌"
        print(f"{status} Step {r['step']}: {r['event_type']}")
        if 'error' in r:
            print(f"   错误: {r['error']}")

    return success_count == len(results)


async def main():
    try:
        result = await test_worker_directly()
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
