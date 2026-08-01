from app.core.engine.state import AgentState
from app.core.engine.state.base import (
    add_unique_items,
    add_unique_subtasks,
    merge_dicts,
)
from app.core.engine.state.lifecycle import StateLifecycleManager
from app.core.engine.state.sub_schemas import SubtaskResult
from app.models.learning import LearnedSkill


def test_merge_dicts():
    assert merge_dicts(None, None) == {}
    assert merge_dicts({"a": "1"}, None) == {"a": "1"}
    assert merge_dicts(None, {"b": "2"}) == {"b": "2"}
    assert merge_dicts({"a": "1"}, {"b": "2", "a": "3"}) == {"a": "3", "b": "2"}

def test_add_unique_items():
    assert add_unique_items(None, None) == []
    assert add_unique_items(["node_1"], ["node_2"]) == ["node_1", "node_2"]
    assert add_unique_items(["node_1"], ["node_1"]) == ["node_1"]

def test_add_unique_subtasks():
    r1 = SubtaskResult(subtask_id="task_1", status="success", result="ok")
    r2 = SubtaskResult(subtask_id="task_2", status="success", result="ok")
    assert add_unique_subtasks(None, None) == []
    assert add_unique_subtasks([r1], [r2]) == [r1, r2]
    # duplicate check
    assert add_unique_subtasks([r1], [r1]) == [r1]

def test_state_lifecycle_manager():
    # Setup initial state
    state = AgentState(
        worker_outcome="SUCCESS",
        spawn_plan={"parent_task": "task_1", "requires_aggregation": True},
        next_node="worker",
        pending_aggregation={"strategy": "merge", "expected_count": 2, "actual_count": 1},
        subtask_results=[SubtaskResult(subtask_id="1", status="success", result="ok")],
        workflow_plan=[LearnedSkill(name="step1"), LearnedSkill(name="step2")],
        workflow_step_index=1,
        workflow_results=[],
        final_outcome="SUCCESS",
        shadow_audit=True,
        blocked_by_hook=True
    )

    # 1. consume_worker_outcome
    outcome = StateLifecycleManager.consume_worker_outcome(state)
    assert outcome == "SUCCESS"
    assert state.worker_outcome is None

    # 2. consume_spawn_plan
    StateLifecycleManager.consume_spawn_plan(state)
    assert state.spawn_plan is None

    # 3. consume_next_node
    target = StateLifecycleManager.consume_next_node(state)
    assert target == "worker"
    assert state.next_node is None

    # 4. clear_aggregation_state
    StateLifecycleManager.clear_aggregation_state(state)
    assert state.pending_aggregation is None
    assert state.subtask_results == []
    assert state.spawn_plan is None

    # 5. consume_blocked_by_hook
    blocked = StateLifecycleManager.consume_blocked_by_hook(state)
    assert blocked is True
    assert state.blocked_by_hook is None
