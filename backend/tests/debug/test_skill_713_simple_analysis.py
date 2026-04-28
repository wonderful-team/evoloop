#!/usr/bin/env python3
"""
Skill 713 简化分析 - 展示验证和执行的区别
"""

import os
import sys
import json
import asyncio
import time

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


async def analyze():
    """分析 Skill 713"""

    print("=" * 80)
    print("📋 Skill 713 分析 - 验证阶段日志")
    print("=" * 80)

    # 加载 Skill
    import asyncpg
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    print(f"\n连接数据库: {pg_server}:{pg_port}/{pg_db}")
    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        """SELECT id, name, description, macro_script, execution_mode, confidence_score
           FROM learned_skills WHERE id = $1""",
        713
    )
    await conn.close()
    print("✅ 数据加载完成\n")

    if not row:
        print("❌ Skill 713 不存在")
        return

    macro_script = json.loads(row['macro_script']) if isinstance(row['macro_script'], str) else row['macro_script']

    print(f"Skill: {row['name']}")
    print(f"执行模式: {row['execution_mode']}")
    print(f"步骤数: {len(macro_script)}\n")

    # 运行验证
    print("=" * 80)
    print("🧪 开始 Agent 验证")
    print("=" * 80)
    print("说明: 这是验证阶段，Agent 会预演宏脚本\n")

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

    total_start = time.time()
    validator = AgentMacroValidator(request)

    # 手动运行验证以便打印日志
    print("初始化验证器...")
    print(f"  平台: {request.target_environment.platform}")
    print(f"  设备: {request.target_environment.device_id}")
    print(f"  LLM 模型: {request.agent_config.llm_model}")
    print(f"  最大重试: {request.agent_config.max_retries_per_step}")

    # 调用验证
    print("\n开始验证...")
    response = await validator.validate()
    total_elapsed = int((time.time() - total_start) * 1000)

    print("\n" + "=" * 80)
    print("📊 验证结果")
    print("=" * 80)
    print(f"总耗时: {total_elapsed}ms ({total_elapsed/1000:.2f}s)")
    print(f"验证成功: {response.success}")
    print(f"执行模式: {response.execution_mode}")
    print(f"置信度: {response.confidence_score}")

    # 每步结果
    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]

        print(f"\n步骤统计:")
        print(f"  通过: {round_report.passed_steps}")
        print(f"  适配: {round_report.adapted_steps}")
        print(f"  失败: {round_report.failed_steps}")

        print(f"\n每步详情:")
        for sr in round_report.step_results:
            step = sr.original_step
            step_num = step.get('step_number', sr.step_number)
            event_type = step.get('event_type', 'unknown')
            target = step.get('target_selector', 'N/A')

            icon = "✅" if sr.status.value == "passed" else "🔧" if sr.status.value == "adapted" else "❌"
            print(f"\n  {icon} Step {step_num}: [{event_type.upper()}] {target}")
            print(f"     状态: {sr.status.value}")

            if sr.adaptations:
                for i, adapt in enumerate(sr.adaptations, 1):
                    print(f"     适配 #{i}: {adapt.reasoning[:60]}...")

    print("\n" + "=" * 80)
    print("✅ 分析完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze())
