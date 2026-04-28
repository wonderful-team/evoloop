#!/usr/bin/env python3
"""
Skill 713 验证分析报告 - 清晰展示验证、修正和冗余检测结果

输出结构:
1. Skill 基本信息
2. 验证执行日志 (每轮验证的步骤状态)
3. 验证结果汇总
4. 原始 vs 修正后宏脚本对比
"""

import os
import sys
import json
import asyncio
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

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

# 执行日志记录
execution_logs: List[Dict[str, Any]] = []


def patch_validator():
    """增强验证器输出"""
    try:
        from app.core.execution.macro.agent_validator import AgentMacroValidator
        from app.core.execution.macro.verification_models import StepExecutionStatus

        original_execute_step = AgentMacroValidator._execute_step_with_adaptation

        async def enhanced_execute(self, step, step_number, round_config):
            event_type = step.get('event_type', 'unknown')
            target = step.get('target_selector', '') or 'N/A'
            payload = step.get('payload', {})

            print(f"\n  ┌─ Step {step_number}: [{event_type.upper()}] {target}")

            # 执行验证
            result = await original_execute_step(self, step, step_number, round_config)

            # 显示执行结果
            status_icon = {
                StepExecutionStatus.PASSED: "✅",
                StepExecutionStatus.ADAPTED: "🔧",
                StepExecutionStatus.FAILED: "❌",
                StepExecutionStatus.SKIPPED: "⏭️",
                StepExecutionStatus.REDUNDANT: "⚠️",
            }.get(result.status, "❓")

            print(f"  └─ {status_icon} 状态: {result.status.value}", end="")

            # 显示耗时 (转换为秒)
            time_sec = result.execution_time_ms / 1000.0
            print(f" | 耗时: {time_sec:.2f}s", end="")

            # 显示冗余信息
            if result.redundancy_check and result.redundancy_check.is_redundant:
                rc = result.redundancy_check
                print(f"\n      ⚠️  冗余: {rc.reason}", end="")

            # 显示适配信息
            if result.adaptations:
                for i, adapt in enumerate(result.adaptations, 1):
                    print(f"\n      🔧 适配#{i}: {adapt.reasoning}", end="")

            print()  # 换行

            # 记录日志
            execution_logs.append({
                'step_number': step_number,
                'event_type': event_type,
                'status': result.status.value,
                'time_ms': result.execution_time_ms,
                'adaptations': len(result.adaptations),
                'redundant': result.redundancy_check.is_redundant if result.redundancy_check else False
            })

            return result

        AgentMacroValidator._execute_step_with_adaptation = enhanced_execute
        print("✅ 验证器增强已安装\n")

    except Exception as e:
        print(f"⚠️ 安装失败: {e}")


async def analyze_skill_713():
    """分析 Skill 713 验证过程"""

    patch_validator()

    # 加载 Skill
    import asyncpg
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        "SELECT id, name, description, status, execution_mode, confidence_score, "
        "macro_script FROM learned_skills WHERE id = $1",
        713
    )
    await conn.close()

    if not row:
        print("❌ Skill 713 不存在")
        return

    macro_script = json.loads(row['macro_script']) if isinstance(row['macro_script'], str) else row['macro_script']

    # 统计宏步骤
    main_steps = len(macro_script)
    loop_substeps = sum(len(s.get('steps', [])) for s in macro_script if s.get('type') == 'loop')

    print("=" * 80)
    print(f"📋 Skill #{row['id']}: {row['name']}")
    print("=" * 80)
    print(f"描述: {row['description'] or 'N/A'}")
    print(f"当前状态: {row['status']}")
    print(f"执行模式: {row['execution_mode']}")
    print(f"置信度: {row['confidence_score']}")
    print(f"\n宏脚本结构:")
    print(f"  主步骤: {main_steps}")
    print(f"  Loop子步骤: {loop_substeps}")
    print(f"  总计: {main_steps + loop_substeps}")

    # 运行验证
    print("\n" + "=" * 80)
    print("🧪 开始验证")
    print("=" * 80)

    from app.core.execution.macro.agent_validator import AgentMacroValidator
    from app.core.execution.macro.verification_models import VerificationRequest, EnvironmentConfig

    request = VerificationRequest(
        macro_script=macro_script,
        target_environment=EnvironmentConfig(platform="android"),
        max_rounds=1,  # Single round for quick verification
        agent_config={"llm_model": "gpt-4o-mini", "max_retries_per_step": 2}
    )

    validator = AgentMacroValidator(request)
    start_time = time.time()

    try:
        response = await validator.validate()
        total_time_ms = int((time.time() - start_time) * 1000)
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 验证结果汇总
    print("\n" + "=" * 80)
    print("📊 验证结果汇总")
    print("=" * 80)

    print(f"\n总体状态: {response.status.value}")
    print(f"执行模式: {response.execution_mode.value}")
    print(f"置信度评分: {response.confidence_score:.2f}")
    print(f"验证耗时: {total_time_ms/1000.0:.2f}s")
    print(f"完成轮次: {response.rounds_completed}")

    if response.verification_report:
        report = response.verification_report
        summary = report.summary

        print(f"\n【执行统计】")
        print(f"  总步骤: {summary.total_steps_checked}")
        print(f"  通过: {int(summary.overall_success_rate * summary.total_steps_checked)}")
        print(f"  适配: {summary.total_adaptations_applied}")
        print(f"  异常: {summary.total_anomalies_detected}")
        print(f"  成功率: {summary.overall_success_rate*100:.1f}%")

        # 冗余检测
        if summary.redundant_steps_count > 0:
            print(f"\n【冗余步骤检测】")
            print(f"  检测到的冗余步骤: {summary.redundant_steps_count}")
            print(f"  按类型: {summary.redundant_steps_by_type}")
            print(f"  估算节省时间: {summary.estimated_time_saved_ms/1000.0:.2f}s")

        # 优化统计
        if report.optimization_stats:
            opt = report.optimization_stats
            print(f"\n【MacroOptimizer 优化】")
            print(f"  原始步骤: {opt.get('original_steps', 'N/A')}")
            print(f"  优化后: {opt.get('optimized_steps', 'N/A')}")
            print(f"  移除: {opt.get('removed_steps', 0)} | 合并: {opt.get('merged_steps', 0)}")
            print(f"  节省: {opt.get('time_saved_ms', 0)/1000.0:.2f}s")

    # 修正详情
    print("\n" + "=" * 80)
    print("🔧 修正详情")
    print("=" * 80)

    if response.evolution_records:
        print(f"\n共 {len(response.evolution_records)} 处修正:\n")
        for i, record in enumerate(response.evolution_records, 1):
            orig = record.original_step
            evolved = record.evolved_step
            print(f"  #{i} Step {orig.get('step_number', '?')}: {record.evolution_reason}")

            # 显示具体变化
            orig_payload = orig.get('payload', {})
            evolved_payload = evolved.get('payload', {})

            if orig_payload.get('x') != evolved_payload.get('x') or \
               orig_payload.get('y') != evolved_payload.get('y'):
                print(f"     坐标: ({orig_payload.get('x')}, {orig_payload.get('y')}) -> "
                      f"({evolved_payload.get('x')}, {evolved_payload.get('y')})")

            if orig.get('target_selector') != evolved.get('target_selector'):
                print(f"     目标: {orig.get('target_selector')} -> {evolved.get('target_selector')}")
    else:
        print("\n  无修正记录")

    # 宏脚本对比
    print("\n" + "=" * 80)
    print("📝 宏脚本对比")
    print("=" * 80)

    print("\n【原始宏脚本】")
    print("-" * 80)
    for step in macro_script:
        step_num = step.get('step_number', 0)
        event = step.get('event_type') or step.get('type', 'unknown')
        target = step.get('target_selector', '') or 'N/A'
        payload = step.get('payload', {})

        # 标记冗余步骤
        is_redundant = any(
            log.get('step_number') == step_num and log.get('redundant')
            for log in execution_logs
        )
        marker = " ⚠️冗余" if is_redundant else ""

        # For loop steps, show sub-step count
        sub_steps = step.get('steps', [])
        if sub_steps:
            print(f"  Step {step_num}: [{event}] {target} ({len(sub_steps)} sub-steps){marker}")
        else:
            print(f"  Step {step_num}: [{event}] {target}{marker}")

    print("\n【修正后的宏脚本】")
    print("-" * 80)
    if response.evolved_macro:
        for step in response.evolved_macro:
            step_num = step.get('step_number', 0)
            # Use event_type for action steps, type for control flow (loop/if)
            event = step.get('event_type') or step.get('type', 'unknown')
            target = step.get('target_selector', '') or 'N/A'
            # For loop steps, show sub-step count
            sub_steps = step.get('steps', [])
            if sub_steps:
                print(f"  Step {step_num}: [{event}] {target} ({len(sub_steps)} sub-steps)")
            else:
                print(f"  Step {step_num}: [{event}] {target}")
    else:
        print("  (与原始相同)")

    print("\n" + "=" * 80)
    print("✅ 分析完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze_skill_713())
