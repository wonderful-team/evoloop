#!/usr/bin/env python3
"""
Skill 713 分析报告 - 展示验证和执行的区别，基于已有数据结构分析
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


async def analyze():
    """分析 Skill 713 的结构和预期耗时"""

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
        """SELECT id, name, description, macro_script, execution_mode, confidence_score
           FROM learned_skills WHERE id = $1""",
        713
    )
    await conn.close()

    if not row:
        print("❌ Skill 713 不存在")
        return

    print("=" * 80)
    print("📋 Skill 713 分析报告 - 验证 vs 执行")
    print("=" * 80)

    print(f"""
┌──────────────────────────────────────────────────────────────────────────────┐
│ 基本概念                                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  【验证阶段】AgentMacroValidator.validate()                                  │
│  ├── 目的: 在正式执行前检查宏的可靠性                                        │
│  ├── 方式: Agent 模拟执行每一步，检测异常                                    │
│  ├── 触发 LLM: 当检测到异常需要适配策略时                                    │
│  └── 输出: 验证报告 + 增强后的宏 + 建议执行模式                              │
│                                                                              │
│  【执行阶段】MacroEngine.execute()                                           │
│  ├── 目的: 在真实设备上运行宏                                                │
│  ├── 方式: 直接执行每一步操作（tap/wait/scroll 等）                          │
│  ├── 触发 LLM: 通常不触发（除非配置为 agentic 模式）                        │
│  └── 输出: 执行结果 + 实际耗时                                               │
│                                                                              │
│  关键区别:                                                                   │
│  • 验证 = 预演/彩排（可能多次尝试同一步骤）                                 │
│  • 执行 = 正式演出（按脚本执行一次）                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
""")

    print(f"Skill 基本信息:")
    print(f"  名称: {row['name']}")
    print(f"  执行模式: {row['execution_mode']}")
    print(f"  置信度: {row['confidence_score']}")

    # 解析宏脚本
    macro_script = json.loads(row['macro_script']) if isinstance(row['macro_script'], str) else row['macro_script']

    print(f"\n宏脚本结构:")
    print(f"  主步骤数: {len(macro_script)}")

    # 详细分析每一步
    print("\n" + "=" * 80)
    print("📊 每步分析 (类型 + 预期耗时 + 是否可能触发 LLM)")
    print("=" * 80)

    for i, step in enumerate(macro_script, 1):
        step_type = step.get('type', 'action')
        event_type = step.get('event_type', 'unknown')
        target = step.get('target_selector', 'N/A')
        payload = step.get('payload', {})

        # 分析是否可能触发 LLM
        may_trigger_llm = False
        llm_reason = ""

        if step_type == 'loop':
            sub_steps = step.get('steps', [])
            print(f"\n  Step {i}: [LOOP] {event_type}")
            print(f"         子步骤数: {len(sub_steps)}")
            for j, sub in enumerate(sub_steps, 1):
                sub_event = sub.get('event_type', 'unknown')
                sub_target = sub.get('target_selector', 'N/A')
                # 元素解析可能触发 LLM 适配
                if sub_target and sub_target != 'N/A':
                    may_trigger_llm = True
                    llm_reason = f"子步骤 {j} 需要元素解析"
                print(f"           {j}. {sub_event} -> {sub_target}")
        else:
            # 判断步骤类型
            has_coords = 'x' in payload and 'y' in payload
            has_target = target and target != 'N/A'

            print(f"\n  Step {i}: [{event_type.upper()}]")
            if has_target:
                print(f"         目标: {target}")
            if has_coords:
                print(f"         坐标: ({payload['x']}, {payload['y']})")

            # 分析预期耗时
            if event_type in ['tap', 'click']:
                if has_coords and has_target:
                    print(f"         预期耗时: 0.5-8s (尝试元素解析，超时后用坐标)")
                    may_trigger_llm = True
                    llm_reason = "元素解析失败时可能触发 LLM 适配"
                elif has_coords:
                    print(f"         预期耗时: 0.5s (直接坐标点击)")
                else:
                    print(f"         预期耗时: 0.5-8s (必须元素解析)")
                    may_trigger_llm = True
                    llm_reason = "元素解析失败时可能触发 LLM 适配"

            elif event_type == 'wait':
                duration = payload.get('seconds', payload.get('duration_ms', 1000) / 1000)
                print(f"         预期耗时: {duration}s (固定等待)")

            elif event_type in ['scroll', 'swipe']:
                print(f"         预期耗时: 1s (滑动操作)")

            elif event_type == 'open_app':
                print(f"         预期耗时: 2-5s (应用启动)")

            elif event_type == 'extract':
                print(f"         预期耗时: 2-5s (数据提取，可能涉及 OCR)")
                may_trigger_llm = True
                llm_reason = "数据提取可能需要 LLM 解析"

        if may_trigger_llm:
            print(f"         ⚠️ 可能触发 LLM: {llm_reason}")

    # 分析执行模式
    print("\n" + "=" * 80)
    print("🤖 执行模式分析")
    print("=" * 80)

    execution_mode = row['execution_mode']
    print(f"\n当前执行模式: {execution_mode}")

    if execution_mode == 'agentic':
        print("""
说明:
  AGENTIC 模式意味着在执行阶段也需要 Agent 实时监控

  执行流程:
  1. 验证阶段: Agent 预演宏 → 生成增强宏
  2. 执行阶段: Agent 每步监控 → 异常时实时适配

  耗时特点:
  • 验证阶段: 慢（需要完整执行一次 + 可能多次 LLM 调用）
  • 执行阶段: 中等（每步都有监控开销）

  LLM 触发时机:
  • 验证阶段: 检测到异常时
  • 执行阶段: 实际执行失败时
        """)
    elif execution_mode == 'deterministic':
        print("""
说明:
  DETERMINISTIC 模式意味着宏可以直接执行，无需 Agent 监控

  执行流程:
  1. 验证阶段: 可能跳过或快速验证
  2. 执行阶段: MacroEngine 直接执行，无监控

  耗时特点:
  • 验证阶段: 快或跳过
  • 执行阶段: 快（无额外开销）

  LLM 触发时机:
  • 验证阶段: 通常不触发
  • 执行阶段: 不触发
        """)

    # 总结
    print("\n" + "=" * 80)
    print("📈 总结")
    print("=" * 80)

    print("""
如果你想看到实际的 LLM 调用和每步耗时:

1. 【验证阶段的 LLM 调用】
   运行: test_skill_713_analysis.py
   这会显示:
   - 每个验证步骤的耗时
   - 每次 LLM 调用的参数和响应
   - 验证结果统计

   注意: 验证阶段会实际在设备上预执行宏，耗时较长

2. 【执行阶段的耗时】
   运行: test_execute_skill_713.py
   这会显示:
   - 每个执行步骤的实际耗时
   - LOOP 子步骤的详细分解
   - 总执行时间统计

   注意: 这是实际执行宏，会操作真实设备

3. 【想看完整的两者对比】
   运行: test_skill_713_full_analysis.py
   这会依次运行验证和执行，并对比两者的耗时

   注意: 总耗时 = 验证耗时 + 执行耗时，可能需要几分钟
""")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze())
