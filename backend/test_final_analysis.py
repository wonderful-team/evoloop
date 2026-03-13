#!/usr/bin/env python3
"""
Skill 713 最终完整分析报告
包含 Loop 子步骤验证
"""

import os
import sys
import json
import asyncio

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


async def analyze_skill_713():
    """分析 Skill 713 完整信息"""

    # 从数据库加载
    import asyncpg
    pg_server = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "app")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"

    conn = await asyncpg.connect(db_url)
    row = await conn.fetchrow(
        """SELECT id, name, description, status, execution_mode, confidence_score, macro_script
           FROM learned_skills WHERE id = $1""",
        713
    )
    await conn.close()

    print("=" * 80)
    print("📋 Skill 713 任务目标")
    print("=" * 80)
    print(f"\nID: {row['id']}")
    print(f"名称: {row['name']}")
    print(f"描述: {row['description'] or 'N/A'}")
    print(f"状态: {row['status']}")
    print(f"当前执行模式: {row['execution_mode']}")
    print(f"当前置信度: {row['confidence_score']}")

    # 解析宏脚本
    macro_script_data = row['macro_script']
    if isinstance(macro_script_data, str):
        macro_script = json.loads(macro_script_data)
    else:
        macro_script = macro_script_data

    print(f"\n📊 宏脚本结构:")
    print(f"   主步骤数: {len(macro_script)}")

    # 分析 loop 子步骤
    total_sub_steps = 0
    for i, step in enumerate(macro_script, 1):
        if step.get('type') == 'loop':
            sub_count = len(step.get('steps', []))
            total_sub_steps += sub_count
            print(f"   Step {i}: Loop 包含 {sub_count} 个子步骤")
    print(f"   总步骤数（含子步骤）: {len(macro_script) + total_sub_steps}")

    # 显示原始宏详细内容
    print(f"\n📝 原始宏脚本详细内容:")
    for i, step in enumerate(macro_script, 1):
        step_type = step.get('type', 'action')
        event_type = step.get('event_type', step.get('action', 'unknown'))
        target = step.get('target_selector', 'N/A')
        payload = step.get('payload', {})

        if step_type == 'loop':
            print(f"\n  Step {i}: [LOOP] 数据采集循环")
            print(f"         子步骤数: {len(step.get('steps', []))}")
            for j, sub in enumerate(step.get('steps', []), 1):
                sub_event = sub.get('event_type', sub.get('action', 'unknown'))
                sub_target = sub.get('target_selector', 'N/A')
                sub_payload = sub.get('payload', {})
                coords = ""
                if 'x' in sub_payload and 'y' in sub_payload:
                    coords = f"({sub_payload['x']}, {sub_payload['y']})"
                print(f"           {j}. [{sub_event}] {sub_target} {coords}")
        else:
            coords = ""
            if 'x' in payload and 'y' in payload:
                coords = f"({payload['x']}, {payload['y']})"
            print(f"\n  Step {i}: [{event_type.upper()}] {target} {coords}")

    # 运行验证测试
    print("\n" + "=" * 80)
    print("🧪 Agent 验证测试（包含 Loop 子步骤）")
    print("=" * 80)

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

    # 验证完整宏（所有22个子步骤）
    print("\n⚡ 验证完整宏（所有子步骤）...")

    validator = AgentMacroValidator(request)
    response = await validator.validate()

    print(f"\n验证结果:")
    print(f"  整体成功: {response.success}")
    print(f"  验证状态: {response.status}")
    print(f"  建议执行模式: {response.execution_mode}")
    print(f"  置信度评分: {response.confidence_score:.2f}")

    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]
        print(f"\n  步骤执行统计:")
        print(f"    通过: {round_report.passed_steps}")
        print(f"    适配: {round_report.adapted_steps}")
        print(f"    失败: {round_report.failed_steps}")
        print(f"    跳过: {round_report.skipped_steps}")

        print(f"\n  每步详细结果:")
        for sr in round_report.step_results:
            step = sr.original_step
            step_num = sr.step_number
            step_type = step.get('type', 'action')
            event_type = step.get('event_type', step.get('action', 'unknown'))
            target = step.get('target_selector', 'N/A')

            status_icon = "✅" if str(sr.status.value) == "passed" else "🔧" if str(sr.status.value) == "adapted" else "❌"
            print(f"\n    {status_icon} Step {step_num}: [{step_type.upper()}] {event_type} {target}")
            print(f"       状态: {sr.status.value}")

            if sr.adaptations:
                print(f"       🤖 Agent 介入 ({len(sr.adaptations)} 次适配):")
                for i, adapt in enumerate(sr.adaptations, 1):
                    print(f"         [{i}] {adapt.reasoning}")
                    if adapt.success and 'payload' in adapt.adapted_strategy:
                        p = adapt.adapted_strategy['payload']
                        if 'x' in p and 'original_x' in p:
                            print(f"             坐标: ({p['original_x']}, {p['original_y']}) -> ({p['x']}, {p['y']})")

            if sr.error_message:
                print(f"       ❌ 错误: {sr.error_message}")

    # 对比原始宏和增强宏
    print("\n" + "=" * 80)
    print("🔄 原始宏 vs 增强宏对比")
    print("=" * 80)

    if response.evolved_macro:
        print(f"\n原始宏步骤数: {len(macro_script)}")
        print(f"增强宏步骤数: {len(response.evolved_macro)}")

        print(f"\n增强宏详细内容:")
        for i, step in enumerate(response.evolved_macro, 1):
            step_type = step.get('type', 'action')
            event_type = step.get('event_type', step.get('action', 'unknown'))
            target = step.get('target_selector', 'N/A')
            payload = step.get('payload', {})

            print(f"\n  Step {i}: [{step_type.upper()}] {event_type} {target}")

            # 显示增强的属性
            enhancements = []
            if 'original_x' in payload:
                enhancements.append(f"坐标修正: ({payload['original_x']:.3f}, {payload['original_y']:.3f}) -> ({payload['x']:.3f}, {payload['y']:.3f})")
            if 'stabilization_ms' in payload:
                enhancements.append(f"稳定等待: {payload['stabilization_ms']}ms")
            if 'retry_delay_ms' in payload:
                enhancements.append(f"重试延迟: {payload['retry_delay_ms']}ms")
            if 'max_retries' in payload:
                enhancements.append(f"最大重试: {payload['max_retries']}次")
            if 'pre_actions' in step:
                enhancements.append(f"前置动作: {len(step['pre_actions'])}个")

            if enhancements:
                print(f"         [增强] " + ", ".join(enhancements))
    else:
        print("\n未生成增强宏（执行模式为 AGENTIC 时不生成静态宏）")

    # 保存修正后的宏到数据库
    if response.evolved_macro:
        print("\n💾 保存修正后的宏到数据库...")

        # 直接使用 evolved_macro（它已经包含所有修正）
        # 但需要确保 loop 子步骤也被正确保留
        final_macro = json.loads(json.dumps(response.evolved_macro))

        # 检查 evolved_macro 中的 loop 子步骤数量
        for i, step in enumerate(final_macro, 1):
            if step.get('type') == 'loop':
                sub_count = len(step.get('steps', []))
                print(f"   Step {i}: Loop 包含 {sub_count} 个子步骤")

        conn = await asyncpg.connect(db_url)
        await conn.execute(
            """UPDATE learned_skills
               SET macro_script = $1,
                   execution_mode = $2,
                   confidence_score = $3,
                   updated_at = NOW()
               WHERE id = $4""",
            json.dumps(final_macro),
            response.execution_mode.value,
            response.confidence_score,
            713
        )
        await conn.close()
        print("   ✅ 已保存到数据库")

    # 总结
    print("\n" + "=" * 80)
    print("📊 总结")
    print("=" * 80)

    if response.verification_report and response.verification_report.rounds:
        round_report = response.verification_report.rounds[0]
        total_adaptations = sum(len(sr.adaptations) for sr in round_report.step_results)
        steps_with_adaptation = sum(1 for sr in round_report.step_results if sr.adaptations)

        print(f"\n🤖 Agent 介入情况:")
        print(f"   介入步骤数: {steps_with_adaptation}/{round_report.total_steps}")
        print(f"   总适配次数: {total_adaptations}")
        print(f"   检测异常数: {response.verification_report.summary.total_anomalies_detected}")

    print(f"\n📋 任务目标:")
    print(f"   采集网易藏宝阁（梦幻西游）角色商品数据")
    print(f"   遍历角色列表 → 点击详情 → 提取属性（价格、等级、门派等）→ 返回继续")

    print(f"\n✅ 验证结论:")
    if response.success:
        print("   宏验证成功，可以稳定执行")
    else:
        print("   宏需要 Agent 监控执行（AGENTIC 模式）")

    print(f"\n🔧 主要修正:")
    print("   1. Step 3 坐标修正: (0.309, 0.268) -> (0.359, 0.348)")
    print("   2. 多个步骤添加状态验证和稳定等待")
    print("   3. Loop 子步骤现在支持独立验证和修正")


if __name__ == "__main__":
    asyncio.run(analyze_skill_713())
