#!/usr/bin/env python3
"""
真正的 Agent Macro 验证测试
使用 AgentMacroValidator + VerificationWorker + MobileController
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 设置环境
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


async def run_agent_validation():
    """
    运行真正的 Agent Macro Validator
    """
    print("=" * 70)
    print("🔬 真正的 Agent Macro Validator 测试")
    print("=" * 70)

    # 1. 加载 skill
    print("\n🗄️  从数据库加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    print(f"✅ 加载成功: {skill['name']}")
    print(f"   步骤数: {len(skill['macro_script'])}")
    print(f"   宏数据: {json.dumps(skill['macro_script'], indent=2, ensure_ascii=False)[:500]}...")

    # 2. 尝试初始化验证系统
    print("\n🔧 初始化 AgentMacroValidator...")

    try:
        # 导入验证模型
        from app.core.execution.macro.verification_models import (
            VerificationRequest, EnvironmentConfig, AgentConfig
        )

        # 创建请求
        request = VerificationRequest(
            macro_script=skill['macro_script'],
            target_environment=EnvironmentConfig(
                platform="android",
                device_id="HYC5T19B11003570"
            ),
            max_rounds=1,  # 只运行一轮 baseline
            agent_config=AgentConfig(
                llm_model="gpt-4o",
                max_retries_per_step=2,
                allow_strategy_adaptation=False  # 不用 LLM，避免依赖
            )
        )
        print("✅ VerificationRequest 创建成功")
        print(f"   平台: {request.target_environment.platform}")
        print(f"   轮数: {request.max_rounds}")

        # 3. 尝试导入并初始化 AgentMacroValidator
        print("\n🚀 初始化 AgentMacroValidator...")
        from app.core.execution.macro.agent_validator import AgentMacroValidator

        validator = AgentMacroValidator(request)
        print("✅ AgentMacroValidator 初始化成功")

        # 4. 查看内部组件
        print("\n📦 内部组件状态:")
        print(f"   - AnomalyDetector: {validator.anomaly_detector}")
        print(f"   - AdaptationLibrary: {validator.adaptation_library}")
        print(f"   - RoundOrchestrator: {validator.orchestrator}")
        print(f"   - 当前宏步骤数: {len(validator.current_macro)}")

        # 5. 尝试创建 VerificationWorker（这会真正连接手机）
        print("\n📱 创建 VerificationWorker...")
        from app.core.execution.macro.verification_worker import VerificationWorker

        worker = VerificationWorker(
            environment_config=request.target_environment,
            agent_config=request.agent_config
        )
        print("✅ VerificationWorker 创建成功")

        # 6. 尝试初始化（连接手机）
        print("\n📲 正在连接手机...")
        try:
            await worker.initialize()
            print("✅ 手机连接成功")

            # 如果能到这里，说明真的连上了
            # 尝试执行一步看看
            print("\n▶️  尝试执行第一步...")

            # 获取当前 UI 状态
            ui_state = await worker.capture_state()
            print(f"✅ 获取 UI 状态成功")
            print(f"   UI 元素数: {len(ui_state.get('elements', []))}")

            # 执行第一步
            if validator.current_macro:
                step = validator.current_macro[0]
                print(f"\n   执行: {step.get('event_type')} - {step.get('payload', {})}")

                # 真正执行
                result = await worker.execute_step(step)
                print(f"✅ 执行结果: {result}")

        except Exception as e:
            print(f"❌ 连接/执行失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(run_agent_validation())
    sys.exit(0 if result else 1)
