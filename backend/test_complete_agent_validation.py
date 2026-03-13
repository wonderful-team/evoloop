#!/usr/bin/env python3
"""
完整 Agent 验证流程 - 使用 Vision LLM 智能验证
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

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
            "SELECT id, name, macro_script FROM learned_skills WHERE id = $1", skill_id
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
    print(f"🔬 完整 Agent 验证流程 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    print("本次验证将使用 Vision LLM 智能分析每一步的截图")
    print()

    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return

    print(f"技能: {skill['name']}")
    print(f"步骤数: {len(skill['macro_script'])}")
    print()

    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    request = VerificationRequest(
        macro_script=skill['macro_script'],
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=1,  # 只跑1轮节省时间
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=2,
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True  # 启用截图分析
        )
    )

    validator = AgentMacroValidator(request)
    print("🔧 AgentMacroValidator 初始化完成")
    print("   - AnomalyDetector: 已加载 (支持 Vision LLM)")
    print("   - AdaptationLibrary: 已加载")
    print("   - Screenshot Analysis: 已启用")
    print()

    try:
        response = await validator.validate()
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return

    print()
    print("=" * 80)
    print("📊 验证结果")
    print("=" * 80)
    print(f"成功: {response.success}")
    print(f"状态: {response.status}")
    print(f"置信度: {response.confidence_score}")
    print(f"建议执行模式: {response.execution_mode}")
    print(f"耗时: {response.processing_time_seconds:.2f} 秒")

    if response.verification_report:
        report = response.verification_report
        print(f"\n检测到的异常: {report.summary.total_anomalies_detected}")
        print(f"应用的适配: {report.summary.total_adaptations_applied}")

        for i, round_report in enumerate(report.rounds, 1):
            print(f"\n第 {i} 轮: {round_report.round_name}")
            print(f"  通过: {round_report.passed_steps} / 适配: {round_report.adapted_steps} / 失败: {round_report.failed_steps}")

            for sr in round_report.step_results:
                status_icon = "✅" if sr.status == "passed" else "🔧" if sr.status == "adapted" else "❌"
                print(f"    {status_icon} Step {sr.step_number}: {sr.status}")
                if sr.adaptations:
                    for adapt in sr.adaptations:
                        print(f"      └─ 适配: {adapt.reasoning[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
