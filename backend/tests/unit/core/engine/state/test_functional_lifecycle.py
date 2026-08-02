from app.core.engine.state import AgentState
from app.core.engine.state.base import (
    add_unique_items,
    merge_dicts,
)
from app.core.engine.state.lifecycle import StateLifecycleManager
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

def test_state_lifecycle_manager():
    # Setup initial state
    state = AgentState(
        worker_outcome="SUCCESS",
        next_node="worker",
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

    # 2. consume_next_node
    target = StateLifecycleManager.consume_next_node(state)
    assert target == "worker"
    assert state.next_node is None

    # 3. consume_blocked_by_hook
    blocked = StateLifecycleManager.consume_blocked_by_hook(state)
    assert blocked is True
    assert state.blocked_by_hook is None
