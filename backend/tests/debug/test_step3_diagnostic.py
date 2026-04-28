#!/usr/bin/env python3
"""
Step 3 详细诊断 - 查看异常检测和适配过程
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


async def diagnose_step3():
    """诊断 Step 3 的执行过程"""
    print("=" * 70)
    print("🔬 Step 3 详细诊断")
    print("=" * 70)

    # 1. 加载 Skill
    print("\n📦 加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    macro_script = skill['macro_script']
    step3 = macro_script[2]  # Step 3 (0-indexed)
    print(f"\n📋 Step 3 原始内容:")
    print(json.dumps(step3, indent=2, ensure_ascii=False))

    # 2. 初始化 Worker
    print("\n🔧 初始化 VerificationWorker...")
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
        allow_strategy_adaptation=True,
        enable_screenshot_analysis=True
    )

    worker = VerificationWorker(env_config, agent_config)
    await worker.initialize()
    print("✅ Worker 初始化成功")

    # 3. 捕获执行前状态
    print("\n📸 捕获执行前状态...")
    pre_state = await worker.capture_state()
    print(f"   当前应用: {pre_state.get('package_name', 'unknown')}")
    print(f"   Activity: {pre_state.get('current_activity', 'unknown')}")
    print(f"   Elements数量: {len(pre_state.get('elements', []))}")
    print(f"   Screenshot: {pre_state.get('screenshot')}")

    # 4. 执行前异常检测
    print("\n🔍 执行前异常检测...")
    from app.core.execution.macro.anomaly_detector import AnomalyDetector
    detector = AnomalyDetector()

    pre_anomaly = await detector.detect_pre_execution_anomaly(step3, pre_state)
    print(f"   是否异常: {pre_anomaly.is_anomaly}")
    print(f"   异常类型: {pre_anomaly.anomaly_type}")
    print(f"   置信度: {pre_anomaly.confidence}")
    print(f"   详情: {pre_anomaly.details}")
    print(f"   建议操作: {pre_anomaly.suggested_action}")

    # 5. 执行 Step 3
    print("\n▶️ 执行 Step 3...")
    start_time = asyncio.get_event_loop().time()
    result = await worker.execute_step(step3)
    elapsed = asyncio.get_event_loop().time() - start_time
    print(f"   执行时间: {elapsed:.2f}秒")
    print(f"   结果: {json.dumps(result, ensure_ascii=False, default=str)[:500]}")

    # 6. 等待一下
    await asyncio.sleep(2)

    # 7. 捕获执行后状态
    print("\n📸 捕获执行后状态...")
    post_state = await worker.capture_state()
    print(f"   当前应用: {post_state.get('package_name', 'unknown')}")
    print(f"   Activity: {post_state.get('current_activity', 'unknown')}")
    print(f"   Elements数量: {len(post_state.get('elements', []))}")
    print(f"   Screenshot: {post_state.get('screenshot')}")

    # 8. 执行后异常检测
    print("\n🔍 执行后异常检测...")
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

    # 9. 如果检测到异常，尝试适配
    if post_anomaly.is_anomaly:
        print("\n🔧 尝试适配...")
        from app.core.execution.macro.adaptation_library import AdaptationStrategyLibrary
        library = AdaptationStrategyLibrary(use_llm=True)

        adaptation_result = await library.adapt(
            step=step3,
            anomaly_type=post_anomaly.anomaly_type,
            anomaly_details=post_anomaly.details,
            ui_state=post_state,
            attempt_number=1
        )

        print(f"   适配成功: {adaptation_result.success}")
        print(f"   适配原因: {adaptation_result.reasoning}")
        print(f"   适配后步骤:")
        print(json.dumps(adaptation_result.adapted_strategy, indent=2, ensure_ascii=False))

        # 10. 如果适配成功，执行适配后的步骤
        if adaptation_result.success:
            print("\n▶️ 执行适配后的步骤...")
            retry_result = await worker.execute_step(adaptation_result.adapted_strategy)
            print(f"   结果: {json.dumps(retry_result, ensure_ascii=False, default=str)[:500]}")

            await asyncio.sleep(2)

            # 11. 验证适配后的状态
            print("\n📸 验证适配后状态...")
            final_state = await worker.capture_state()
            print(f"   当前应用: {final_state.get('package_name', 'unknown')}")
            print(f"   Activity: {final_state.get('current_activity', 'unknown')}")

            # 检查状态是否变化
            pre_elements = set(str(e) for e in pre_state.get("elements", []))
            post_elements = set(str(e) for e in final_state.get("elements", []))
            state_changed = pre_elements != post_elements
            print(f"   状态是否变化: {state_changed}")

    # 清理
    await worker.cleanup()
    print("\n✅ 诊断完成")
    return True


if __name__ == "__main__":
    try:
        asyncio.run(diagnose_step3())
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户取消")
    except Exception as e:
        print(f"\n❌ 诊断失败: {e}")
        import traceback
        traceback.print_exc()
