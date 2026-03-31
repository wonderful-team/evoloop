#!/usr/bin/env python3
"""
完整验证流程测试 - 使用 AgentMacroValidator.validate()
符合方案文档要求
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


async def run_full_validation():
    """运行完整的 validate() 流程"""
    print("=" * 70)
    print("🔬 完整验证流程测试 - 使用 AgentMacroValidator.validate()")
    print("=" * 70)

    # 1. 加载 skill
    print("\n🗄️  加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    print(f"✅ 加载成功: {skill['name']}")
    print(f"   步骤数: {len(skill['macro_script'])}")

    # 2. 创建 VerificationRequest
    print("\n📋 创建 VerificationRequest...")
    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )

    request = VerificationRequest(
        macro_script=skill['macro_script'],
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=2,  # 跑两轮：baseline + stress
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=2,
            allow_strategy_adaptation=True
        )
    )
    print(f"✅ Request 创建成功")
    print(f"   平台: {request.target_environment.platform}")
    print(f"   轮数: {request.max_rounds}")
    print(f"   步骤: {len(request.macro_script)}")

    # 3. 初始化 AgentMacroValidator
    print("\n🔧 初始化 AgentMacroValidator...")
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    validator = AgentMacroValidator(request)
    print("✅ Validator 初始化成功")

    # 4. 运行完整验证流程
    print("\n" + "=" * 70)
    print("🚀 运行 validator.validate() - 完整流程")
    print("=" * 70)
    print("这将会：")
    print("  1. 初始化 VerificationWorker（连接手机）")
    print("  2. 运行第 1 轮：基准环境")
    print("  3. 运行第 2 轮：干扰环境（注入延迟/网络降级等）")
    print("  4. 每步执行：检测异常 → 适配策略 → 修正 → 验证")
    print("  5. 宏进化：合并所有修正生成增强宏")
    print("  6. 生成验证报告")
    print("=" * 70)

    print("\n⚠️  这将在真实手机上执行宏并可能触发修复逻辑！")
    print("3 秒后继续...")
    await asyncio.sleep(3)

    try:
        # 运行完整验证
        response = await validator.validate()

        # 5. 输出结果
        print("\n" + "=" * 70)
        print("📊 验证结果")
        print("=" * 70)

        print(f"成功: {response.success}")
        print(f"状态: {response.status}")
        print(f"完成轮数: {response.rounds_completed}")
        print(f"执行模式: {response.execution_mode}")
        print(f"置信度: {response.confidence_score}")
        print(f"耗时: {response.processing_time_seconds:.2f} 秒")

        if response.evolved_macro:
            print(f"\n增强宏步骤数: {len(response.evolved_macro)}")

        if response.verification_report:
            report = response.verification_report
            print(f"\n验证报告:")
            print(f"  摘要: {report.summary}")
            print(f"  问题数: {len(report.issues)}")
            print(f"  建议: {report.recommendations}")

        return response.success

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(run_full_validation())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消")
        sys.exit(1)
