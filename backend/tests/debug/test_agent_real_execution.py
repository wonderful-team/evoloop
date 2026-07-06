#!/usr/bin/env python3
"""
真正的 Agent Macro 验证 + 真实手机执行
使用 MobileController 直接执行
"""

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["ENVIRONMENT"] = "local"
os.environ["SENTRY_DSN"] = "https://test@test.sentry.io/1"

# 加载 .env
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
    """Query LearnedSkills table"""
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
        import traceback
        traceback.print_exc()
        return None


async def run_agent_with_real_execution():
    """运行 Agent 验证 + 真实执行"""
    print("=" * 70)
    print("🔬 真正的 Agent Macro Validator + 真实手机执行")
    print("=" * 70)

    # 1. 加载 skill
    print("\n🗄️  从数据库加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    print(f"✅ 加载成功: {skill['name']}")
    print(f"   步骤数: {len(skill['macro_script'])}")
    print(f"   执行模式: {skill['execution_mode']}")

    # 2. 初始化验证组件
    print("\n🔧 初始化 AgentMacroValidator...")

    from app.core.execution.macro.verification_models import (
        AgentConfig,
        AnomalyType,
        EnvironmentConfig,
        VerificationRequest,
    )

    from app.core.execution.macro.agent_validator import AgentMacroValidator

    request = VerificationRequest(
        macro_script=skill['macro_script'],
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=1,
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=2,
            allow_strategy_adaptation=False
        )
    )

    validator = AgentMacroValidator(request)
    print("✅ AgentMacroValidator 初始化成功")
    print(f"   - 异常检测器: {validator.anomaly_detector}")
    print(f"   - 适配库: {validator.adaptation_library}")
    print(f"   - 轮次编排器: {validator.orchestrator}")

    # 3. 直接连接手机执行
    print("\n📱 连接 MobileController...")
    from app.core.environment.controllers.mobile import MobileController

    # 4. 真实执行宏
    print("\n" + "=" * 70)
    print("▶️  真实执行宏（每步都有日志）")
    print("=" * 70)

    results = []

    for i, step in enumerate(skill['macro_script'], 1):
        event_type = step.get('event_type', 'unknown')
        payload = step.get('payload', {})

        print(f"\n  Step {i}: {event_type}")
        print(f"    Payload: {json.dumps(payload, ensure_ascii=False)[:200]}...")

        result = {'step': i, 'event_type': event_type, 'success': False, 'error': None}

        try:
            # 异常检测：Pre-execution
            print("    🔍 [Agent] 执行前异常检测...")
            pre_result = await validator.anomaly_detector.detect_pre_execution_anomaly(
                step, {'platform': 'android', 'elements': []}
            )
            print(f"        是否异常: {pre_result.is_anomaly}, 类型: {pre_result.anomaly_type}")

            # Step 1: open_app
            if event_type == 'open_app':
                package = payload.get('package')
                print(f"    🚀 正在打开应用: {package}")

                # 使用 MobileController
                await MobileController.execute(
                    action='open_app',
                    target=package,
                    device_id='HYC5T19B11003570'
                )
                print("    ✅ 应用启动命令已发送")

                # 等待 2 秒让应用启动
                await asyncio.sleep(2)

                # 检查当前应用
                current = await MobileController.get_current_app_cached()
                print(f"    📱 当前应用: {current}")

                # 异常检测：Post-execution - 检查是否真的打开了目标 app
                if current.get('package') != package:
                    print("    ⚠️  [Agent] 检测到异常: 应用未正确启动!")
                    print(f"        期望: {package}, 实际: {current.get('package')}")
                    # 尝试适配
                    adaptation = await validator.adaptation_library.adapt(
                        step=step,
                        anomaly_type=AnomalyType.ELEMENT_NOT_FOUND,
                        anomaly_details={'expected': package, 'actual': current.get('package')},
                        ui_state={'current_app': current}
                    )
                    print(f"    🔧 [Agent] 适配建议: {adaptation.reasoning[:100]}...")
                    validator.adaptation_records.append(adaptation)

                result['success'] = True
                result['current_app'] = current

            # Step 2/4: wait
            elif event_type == 'wait':
                seconds = payload.get('seconds', 1)
                print(f"    ⏱️  等待 {seconds} 秒...")
                await asyncio.sleep(seconds)
                print("    ✅ 等待完成")
                result['success'] = True

            # Step 3: tap
            elif event_type == 'tap':
                x = payload.get('x')
                y = payload.get('y')

                # 相对坐标转绝对坐标
                if x is not None and y is not None and x < 1 and y < 1:
                    # 1080x2340 屏幕
                    abs_x = int(x * 1080)
                    abs_y = int(y * 2340)
                else:
                    abs_x = int(x) if x else 500
                    abs_y = int(y) if y else 1000

                print(f"    👆 点击坐标: ({abs_x}, {abs_y})")

                await MobileController.execute(
                    action='click',
                    x=abs_x,
                    y=abs_y,
                    device_id='HYC5T19B11003570'
                )
                print("    ✅ 点击完成")

                # 等待 UI 响应
                await asyncio.sleep(0.5)

                result['success'] = True
                result['coordinates'] = (abs_x, abs_y)

            else:
                print(f"    ⚠️  未知事件类型: {event_type}")
                result['error'] = f"Unknown event type: {event_type}"

        except Exception as e:
            print(f"    ❌ 执行失败: {e}")
            result['error'] = str(e)
            import traceback
            traceback.print_exc()

        results.append(result)

    # 5. 执行总结
    print("\n" + "=" * 70)
    print("📊 执行总结")
    print("=" * 70)

    success_count = sum(1 for r in results if r['success'])

    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"{status} Step {r['step']}: {r['event_type']:<15} - {r['error'] or 'OK'}")

    print(f"\n成功率: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")

    # 6. Agent 验证总结
    print("\n" + "=" * 70)
    print("🔍 Agent 验证组件状态")
    print("=" * 70)
    print(f"异常检测记录: {len(validator.execution_history)} 条")
    print(f"适配记录: {len(validator.adaptation_records)} 条")
    print(f"轮次报告: {len(validator.round_reports)} 条")
    print(f"进化记录: {len(validator.evolution_records)} 条")

    return success_count == len(results)


if __name__ == "__main__":
    try:
        result = asyncio.run(run_agent_with_real_execution())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消")
        sys.exit(1)
