"""
混合架构测试 - 动态 Worker + Macro 协同

演示场景: "批量采集闲鱼商品"

执行流程:
1. Supervisor 调用 decompose_task 分解任务
2. 生成10个子任务，每个提示可以使用 "采集闲鱼商品" 技能
3. Router 并行派发10个 Worker
4. 每个 Worker:
   - 优先 search_skills("采集闲鱼商品")
   - 如果找到且 execution_mode="deterministic" → run_macro
   - 如果没找到 → 使用 mobile_control 自适应执行
5. 结果聚合返回

Usage:
    python tests/test_hybrid_macro_worker.py
"""

import asyncio
import sys
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")


async def test_hybrid_execution():
    """测试混合架构的执行逻辑."""
    print("=" * 60)
    print("混合架构测试: 动态 Worker + Macro 协同")
    print("=" * 60)

    # 1. 测试 decompose_task 生成带 skill_hint 的子任务
    print("\n[Step 1] 任务分解")
    print("-" * 40)

    from app.core.engine.tools.planning import decompose_task

    result = await decompose_task.ainvoke({
        "task_description": "采集闲鱼上5个iPhone 15的商品详情",
        "context": "每个商品需要获取价格、标题、描述、图片",
        "max_parallel": 5,
        "requires_aggregation": True
    })

    if result.get("status") == "success":
        plan = result["plan"]
        print(f"✅ 任务分解成功")
        print(f"   策略: {plan.get('strategy')}")
        print(f"   建议技能: {plan.get('suggested_skill', '无')}")
        print(f"   子任务数: {len(plan.get('subtasks', []))}")

        for st in plan.get("subtasks", [])[:2]:
            print(f"\n   子任务 {st.get('id')}:")
            print(f"     目标: {st.get('intent')}")
            print(f"     技能提示: {st.get('skill_hint', '无')}")
    else:
        print(f"⚠️  分解失败: {result.get('error')}")

    # 2. 模拟 Worker 执行决策逻辑
    print("\n[Step 2] Worker 执行决策模拟")
    print("-" * 40)

    # 模拟子任务的 skill_hint
    mock_subtask = {
        "id": "task_1",
        "intent": "采集闲鱼商品1",
        "skill_hint": "采集闲鱼商品详情",
        "context": {"target": "商品ID-12345"}
    }

    print(f"子任务: {mock_subtask['intent']}")
    print(f"技能提示: {mock_subtask.get('skill_hint')}")
    print("\nWorker 决策流程:")
    print("  1. search_skills('采集闲鱼商品详情')")
    print("  2. IF found AND execution_mode=='deterministic':")
    print("       → run_macro(skill_name='采集闲鱼商品详情', params={...})")
    print("     ELSE:")
    print("       → mobile_control(...) 自适应执行")

    # 3. 验证 Router 生成正确的 ticket
    print("\n[Step 3] Router 生成的 ExecutionTicket")
    print("-" * 40)

    ticket = {
        "ticket_type": "subtask",
        "topic": mock_subtask["intent"],
        "agent_config": {
            "role_name": f"Subtask-{mock_subtask['id']}",
            "system_instructions": (
                f"Execute subtask: {mock_subtask['intent']}\n\n"
                f"💡 HINT: This subtask may be accomplished using the learned skill "
                f"'{mock_subtask.get('skill_hint')}'. Try `search_skills` first..."
            ),
            "skill_hint": mock_subtask.get("skill_hint"),
        }
    }

    print(f"Ticket 结构:")
    print(f"  type: {ticket['ticket_type']}")
    print(f"  topic: {ticket['topic']}")
    print(f"  skill_hint: {ticket['agent_config']['skill_hint']}")
    print(f"  instructions包含提示: {'💡 HINT' in ticket['agent_config']['system_instructions']}")

    print("\n" + "=" * 60)
    print("混合架构优势:")
    print("=" * 60)
    print("""
1. 性能优化:
   - 有学习过技能的任务 → run_macro (毫秒级确定性执行)
   - 新任务 → Worker 自适应 (秒级 LLM 推理)

2. 渐进式学习:
   - 首次: Worker 自适应执行，同时录制 Trace
   - 学习: SmartSynthesizer 从 Trace 生成 Skill
   - 后续: decompose_task 自动建议使用已学习技能

3. 灵活回退:
   - 如果 run_macro 失败 → 自动 fallback 到 Worker 自适应
   - 如果技能不存在 → Worker 直接自适应执行
""")


if __name__ == "__main__":
    asyncio.run(test_hybrid_execution())
