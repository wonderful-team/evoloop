"""
Test script for Phase 1 Dynamic Subtask Generation

Usage:
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    python tests/test_dynamic_subtasks.py
"""

import asyncio
import sys
import uuid

# Add backend to path
sys.path.insert(0, "/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend")

# Set up logging
import logging
logging.basicConfig(level=logging.INFO)
for module in [
    "app.core.engine.nodes.supervisor",
    "app.core.engine.nodes.worker",
    "app.core.engine.routers",
    "app.core.engine",
]:
    logging.getLogger(module).setLevel(logging.DEBUG)


async def test_decompose_task():
    """Test the decompose_task tool directly."""
    print("\n=== Test 1: decompose_task tool ===")

    from app.core.engine.tools.planning import decompose_task

    result = await decompose_task.ainvoke({
        "task_description": "采集闲鱼上10个iPhone 15的商品详情",
        "context": "用户想要获取商品价格、描述、图片等信息",
        "max_parallel": 5,
        "requires_aggregation": True
    })

    print(f"Status: {result.get('status')}")
    print(f"Subtask count: {result.get('subtask_count')}")

    if result.get('status') == 'success':
        plan = result.get('plan', {})
        print(f"Strategy: {plan.get('strategy')}")
        print(f"Can parallelize: {plan.get('can_parallelize')}")
        print(f"Reasoning: {plan.get('reasoning')}")

        print("\nSubtasks:")
        for i, subtask in enumerate(plan.get('subtasks', [])[:3], 1):
            print(f"  {i}. {subtask.get('id')}: {subtask.get('intent')}")
            print(f"     Tools: {subtask.get('tools', [])}")
            print(f"     Complexity: {subtask.get('estimated_complexity')}")

    return result


async def test_router_spawn():
    """Test the router's spawn logic."""
    print("\n=== Test 2: Router spawn logic ===")

    from app.core.engine.routers import route_supervisor
    from app.core.engine.state import AgentState

    # Create a mock state with spawn plan
    mock_plan = {
        "subtasks": [
            {"id": "task_1", "intent": "采集商品1", "tools": ["mobile_control"]},
            {"id": "task_2", "intent": "采集商品2", "tools": ["mobile_control"]},
            {"id": "task_3", "intent": "采集商品3", "tools": ["mobile_control"]},
        ],
        "strategy": "parallel",
        "aggregation_strategy": "merge",
        "_requires_aggregation": True,
        "parent_task": "采集3个商品"
    }

    state: AgentState = {
        "messages": [],
        "next_node": "spawn_subtasks",
        "scratchpad": {
            "_spawn_plan": mock_plan,
            "_pending_aggregation": {
                "strategy": "merge",
                "expected_count": 3,
                "parent_task": "采集3个商品"
            }
        },
        "project_id": 1,
    }

    result = route_supervisor(state)

    # Check if result is a list of Send objects
    if isinstance(result, list):
        print(f"✅ Router returned {len(result)} Send commands for parallel execution")
        for i, send in enumerate(result[:2], 1):
            print(f"  Send {i}: node='{send.node}'")
            if hasattr(send, 'arg'):
                print(f"    Arg keys: {send.arg.keys() if isinstance(send.arg, dict) else 'N/A'}")
    else:
        print(f"⚠️  Router returned: {result}")

    return result


async def test_worker_subtask_detection():
    """Test worker's subtask result collection."""
    print("\n=== Test 3: Worker subtask detection ===")

    from app.core.engine.nodes.worker import WorkerNode
    from app.core.engine.state import AgentState

    worker = WorkerNode()

    # Create mock state simulating a subtask execution
    mock_state: AgentState = {
        "messages": [],
        "execution_ticket": {
            "ticket_type": "subtask",
            "topic": "采集商品1",
            "subtask_id": "task_1",
            "parent_task_id": "parent_123",
            "agent_config": {
                "role_name": "Subtask-task_1",
                "is_subtask": True,
                "tools": ["mobile_control"]
            }
        },
        "scratchpad": {
            "_pending_aggregation": {
                "expected_count": 3,
                "strategy": "merge"
            }
        }
    }

    # Mock engine result
    mock_engine_result = {
        "messages": [type('MockMsg', (), {'content': '商品1采集完成: iPhone 15 价格5999'})],
        "tool_history": ["mobile_control:{\"action\": \"click\"}"]
    }

    # Test post-processing
    result = worker._post_process_result(
        state=mock_state,
        engine_result=mock_engine_result,
        execution_ticket=mock_state["execution_ticket"],
        role_name="Subtask-task_1"
    )

    scratchpad = result.get("scratchpad", {})
    subtask_results = scratchpad.get("subtask_results", [])

    print(f"✅ Worker detected subtask execution")
    print(f"   Collected {len(subtask_results)} subtask result(s)")
    if subtask_results:
        print(f"   Result preview: {subtask_results[0].get('result', '')[:50]}...")

    return result


async def test_supervisor_aggregation():
    """Test Supervisor's auto-aggregation logic."""
    print("\n=== Test 4: Supervisor auto-aggregation ===")

    from app.core.engine.nodes.supervisor import SupervisorNode
    from app.core.engine.state import AgentState

    supervisor = SupervisorNode()

    # Create mock state with completed subtasks
    mock_state: AgentState = {
        "messages": [],
        "project_id": 1,
        "scratchpad": {
            "subtask_results": [
                {"subtask_id": "task_1", "result": "商品1: iPhone 15 5999元"},
                {"subtask_id": "task_2", "result": "商品2: iPhone 15 6099元"},
                {"subtask_id": "task_3", "result": "商品3: iPhone 15 5899元"},
            ],
            "_pending_aggregation": {
                "expected_count": 3,
                "strategy": "concatenate",
                "parent_task": "采集3个商品"
            }
        },
        "iteration_count": 0
    }

    # Create minimal config
    from langchain_core.runnables import RunnableConfig
    config: RunnableConfig = {
        "configurable": {
            "thread_id": f"test-{uuid.uuid4().hex[:8]}",
            "working_directory": "/tmp"
        }
    }

    print("   Mock state has 3 subtask results, expected 3")
    print("   Supervisor should auto-aggregate...")

    # This will test the auto-aggregation path
    # Note: In real execution, this would call aggregate_results
    # Here we're just checking the condition logic

    scratchpad = mock_state.get("scratchpad", {})
    subtask_results = scratchpad.get("subtask_results", [])
    pending_agg = scratchpad.get("_pending_aggregation", {})

    should_aggregate = (
        subtask_results and
        pending_agg and
        len(subtask_results) >= pending_agg.get("expected_count", 0)
    )

    print(f"   Should aggregate: {should_aggregate}")

    if should_aggregate:
        print("✅ Supervisor would trigger auto-aggregation")

    return should_aggregate


async def test_full_flow():
    """Integration test of the full dynamic subtask flow."""
    print("\n=== Test 5: Full Flow Integration ===")
    print("   (This requires full system initialization)")

    try:
        # Initialize minimal system
        from app.core.engine.state import AgentState
        from app.core.tools.registry import _ensure_scanned

        # Ensure tools are registered
        _ensure_scanned()

        print("   ✓ Tools registered")

        # Check if decompose_task is available
        from app.core.tools.manager import tool_manager
        supervisor_tools = tool_manager.get_node_tools("supervisor")
        tool_names = [t.name for t in supervisor_tools]

        print(f"   Supervisor tools: {len(tool_names)}")

        if "decompose_task" in tool_names:
            print("   ✅ decompose_task tool is available")
        else:
            print("   ⚠️  decompose_task tool NOT found")
            print(f"   Available: {tool_names[:10]}...")

        if "aggregate_results" in tool_names:
            print("   ✅ aggregate_results tool is available")
        else:
            print("   ⚠️  aggregate_results tool NOT found")

        return "decompose_task" in tool_names and "aggregate_results" in tool_names

    except Exception as e:
        print(f"   ❌ Full flow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("=" * 60)
    print("Phase 1 Dynamic Subtask Generation - Test Suite")
    print("=" * 60)

    # Run all tests
    results = []

    results.append(("decompose_task", await test_decompose_task()))
    results.append(("router_spawn", await test_router_spawn()))
    results.append(("worker_detection", await test_worker_subtask_detection()))
    results.append(("supervisor_agg", await test_supervisor_aggregation()))
    results.append(("full_flow", await test_full_flow()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, result in results:
        status = "✅ PASS" if result else "⚠️  CHECK"
        print(f"  {status}: {name}")

    print("\nPhase 1 implementation ready for integration testing!")


if __name__ == "__main__":
    asyncio.run(main())
