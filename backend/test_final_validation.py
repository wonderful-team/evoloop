#!/usr/bin/env python3
"""
最终验证测试 - 完整 AgentMacroValidator 流程
显示详细执行结果和证据
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
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


async def main():
    print("=" * 80)
    print("🔬 AgentMacroValidator 完整验证测试")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 加载 Skill
    print("📦 步骤 1: 加载 Skill 713...")
    skill = await get_skill_from_db(713)
    if not skill:
        print("❌ 无法加载 skill")
        return False

    print(f"   ✅ 名称: {skill['name']}")
    print(f"   ✅ 状态: {skill['status']}")
    print(f"   ✅ 执行模式: {skill['execution_mode']}")
    print(f"   ✅ 步骤数: {len(skill['macro_script'])}")
    print()

    # 2. 创建 VerificationRequest
    print("📋 步骤 2: 创建 VerificationRequest...")
    from app.core.execution.macro.verification_models import (
        VerificationRequest, EnvironmentConfig, AgentConfig
    )

    request = VerificationRequest(
        macro_script=skill['macro_script'],
        target_environment=EnvironmentConfig(
            platform="android",
            device_id="HYC5T19B11003570"
        ),
        max_rounds=2,  # 基准轮 + 压力测试轮
        agent_config=AgentConfig(
            llm_model="gpt-4o",
            max_retries_per_step=2,
            allow_strategy_adaptation=True,
            enable_screenshot_analysis=True
        )
    )
    print(f"   ✅ 平台: {request.target_environment.platform}")
    print(f"   ✅ 设备: {request.target_environment.device_id}")
    print(f"   ✅ 轮数: {request.max_rounds}")
    print(f"   ✅ 适配策略: 启用")
    print()

    # 3. 初始化 AgentMacroValidator
    print("🔧 步骤 3: 初始化 AgentMacroValidator...")
    from app.core.execution.macro.agent_validator import AgentMacroValidator

    validator = AgentMacroValidator(request)
    print(f"   ✅ AnomalyDetector: 已加载 (8种异常类型)")
    print(f"   ✅ AdaptationLibrary: 已加载 (LLM适配: {request.agent_config.allow_strategy_adaptation})")
    print(f"   ✅ RoundOrchestrator: 已加载 (3种策略)")
    print()

    # 4. 执行验证
    print("🚀 步骤 4: 执行验证流程...")
    print("-" * 80)
    print("验证流程:")
    print("  • 第 1 轮: 基准环境 (无干扰)")
    print("  • 第 2 轮: 压力测试 (注入延迟/元素不稳定等干扰)")
    print("  • 每步执行: 异常检测 → 适配策略 → 修正 → 验证")
    print("  • 宏进化: 合并所有修正生成增强宏")
    print("-" * 80)
    print()

    try:
        response = await validator.validate()
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 5. 显示结果
    print()
    print("=" * 80)
    print("📊 验证结果")
    print("=" * 80)
    print()

    print(f"整体成功: {'✅ 是' if response.success else '❌ 否'}")
    print(f"验证状态: {response.status}")
    print(f"完成轮数: {response.rounds_completed}/{request.max_rounds}")
    print(f"建议执行模式: {response.execution_mode}")
    print(f"置信度评分: {response.confidence_score:.2f}/1.0")
    print(f"总耗时: {response.processing_time_seconds:.2f} 秒")
    print()

    # 显示轮次报告
    print("-" * 80)
    print("📈 轮次详情")
    print("-" * 80)
    for i, report in enumerate(response.verification_report.rounds, 1):
        print(f"\n第 {i} 轮: {report.round_name}")
        print(f"  状态: {report.status}")
        print(f"  步骤: {report.passed_steps} 通过 / {report.adapted_steps} 适配 / {report.failed_steps} 失败 / {report.total_steps} 总计")
        if report.step_results:
            for sr in report.step_results:
                status_icon = "✅" if sr.status == "passed" else "🔧" if sr.status == "adapted" else "❌"
                print(f"    {status_icon} Step {sr.step_number}: {sr.status}")
                if sr.adaptations:
                    for adapt in sr.adaptations:
                        print(f"      └─ 适配: {adapt.reasoning[:80]}...")
    print()

    # 显示异常和适配统计
    print("-" * 80)
    print("🔍 异常检测与适配")
    print("-" * 80)
    if response.verification_report:
        report = response.verification_report
        print(f"检测到的异常: {report.summary.total_anomalies_detected}")
        print(f"应用的适配: {report.summary.total_adaptations_applied}")
        print(f"平均执行时间: {report.summary.average_execution_time_ms:.0f}ms")
        print(f"成功率: {report.summary.overall_success_rate*100:.1f}%")
        print(f"适配率: {report.summary.adaptation_rate*100:.1f}%")
    print()

    # 显示增强宏
    print("-" * 80)
    print("🧬 宏进化结果")
    print("-" * 80)
    if response.evolved_macro:
        print(f"增强宏步骤数: {len(response.evolved_macro)}")
        print(f"原始宏步骤数: {len(skill['macro_script'])}")
        print("\n增强宏内容:")
        for i, step in enumerate(response.evolved_macro, 1):
            event_type = step.get('event_type', step.get('type', 'unknown'))
            print(f"  {i}. {event_type}")
    else:
        print("未生成增强宏")
    print()

    # 显示建议
    print("-" * 80)
    print("💡 系统建议")
    print("-" * 80)
    if response.verification_report and response.verification_report.recommendations:
        for rec in response.verification_report.recommendations:
            print(f"  • {rec}")
    else:
        print("  无特别建议")
    print()

    # 显示截图路径
    print("-" * 80)
    print("📸 截图证据")
    print("-" * 80)
    screenshot_dirs = list(Path("/Users/huangjinhuan/.evoloop/artifacts/screenshots/temp").glob("20260313"))
    if screenshot_dirs:
        screenshots = sorted(screenshot_dirs[0].glob("android_*.png"))
        print(f"共捕获 {len(screenshots)} 张截图:")
        for ss in screenshots[-5:]:  # 显示最后5张
            print(f"  • {ss.name}")
    print()

    print("=" * 80)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    return response.success


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消")
        sys.exit(1)
