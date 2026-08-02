import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.channel.output.voice_channel import VoiceChannel
from app.core.engine.loop import run_node_loop
from app.core.engine.routers import RoutingTarget
from app.core.engine.worker_registry import WorkerRegistry


@pytest.mark.asyncio
async def test_pop_previous_task_idempotency():
    """Verify calling pop_previous_task twice on the same thread returns None on the second call."""
    registry = WorkerRegistry()
    thread_id = "test-thread-idempotency"

    # Create dummy tasks
    async def dummy():
        pass
    task1 = asyncio.create_task(dummy())
    task2 = asyncio.create_task(dummy())

    await registry.register_worker(thread_id, task1, "task 1")
    # Registering task2 should cache task1 in previous_tasks
    await registry.register_worker(thread_id, task2, "task 2")

    popped1 = await registry.pop_previous_task(thread_id)
    assert popped1 == task1

    # Second pop must return None (idempotent pop behavior)
    popped2 = await registry.pop_previous_task(thread_id)
    assert popped2 is None

    # Cleanup
    await task1
    await task2


@pytest.mark.asyncio
async def test_register_overwrite_caches_correct_previous_worker():
    """Verify new register_worker correctly caches the previous running worker."""
    registry = WorkerRegistry()
    thread_id = "test-thread-cache"

    async def dummy():
        pass
    task1 = asyncio.create_task(dummy())
    task2 = asyncio.create_task(dummy())
    task3 = asyncio.create_task(dummy())

    # Step 1: Register first task
    await registry.register_worker(thread_id, task1, "task 1")
    assert thread_id not in registry._previous_tasks

    # Step 2: Register second task, caching task1
    await registry.register_worker(thread_id, task2, "task 2")
    assert registry._previous_tasks[thread_id] == task1

    # Step 3: Register third task, caching task2 (since task1 is already popped/cleared or overwritten)
    await registry.register_worker(thread_id, task3, "task 3")
    assert registry._previous_tasks[thread_id] == task2

    # Cleanup
    await task1
    await task2
    await task3


@pytest.mark.asyncio
async def test_reset_thread_and_barge_in_mute_rules():
    """Verify reset_thread clears the cancellation state so push_tts_chunk can run."""
    # Ensure VoiceChannel has static dictionaries set up
    VoiceChannel.reset_thread("test-thread-barge")

    # 1. Trigger Barge-in cancel
    VoiceChannel.cancel_thread("test-thread-barge")
    assert "test-thread-barge" in VoiceChannel._cancelled_threads

    # 2. Verify push_tts_chunk is blocked (returns early without error)
    # We mock volc client to verify send is not called
    mock_client = MagicMock()
    mock_client.send_chat_tts_text = AsyncMock()

    from app.core.voice.executor import active_volc_clients
    active_volc_clients["test-thread-barge"] = mock_client

    await VoiceChannel.push_tts_chunk("test-thread-barge", "Hello", end=False)
    mock_client.send_chat_tts_text.assert_not_called()

    # 3. Call reset_thread to clear barge-in cancellation marker
    VoiceChannel.reset_thread("test-thread-barge")
    assert "test-thread-barge" not in VoiceChannel._cancelled_threads

    # 4. Verify push_tts_chunk now runs and calls client
    await VoiceChannel.push_tts_chunk("test-thread-barge", "Hello", end=False)
    mock_client.send_chat_tts_text.assert_called_once()

    # Clean up registry
    active_volc_clients.pop("test-thread-barge", None)


@pytest.mark.asyncio
async def test_cancellation_gate_transitions():
    """Verify loop transition gate behaves correctly:

    - next_node=END (QUERY) -> old task survives.
    - next_node=WORKER (NEW_COMMAND) -> old task cancelled.
    - next_node=SEQUENTIAL_WORKFLOW -> old task cancelled.
    """
    from app.core.engine.worker_registry import worker_registry

    async def long_running_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    async def new_dummy_task():
        pass

    # --- Scenario 1: Transition to END (QUERY) ---
    thread_id = "test-query-gate"
    old_task = asyncio.create_task(long_running_task())
    new_task = asyncio.create_task(new_dummy_task())

    await worker_registry.register_worker(thread_id, old_task, "old running task")
    await worker_registry.register_worker(thread_id, new_task, "new task")

    # Mock state and transition supervisor -> END
    class MockState:
        next_node = RoutingTarget.SUPERVISOR
        iteration_count = 0
        messages = []
        structured_plan = None
        current_plan = None
        session_goal = "query"
        worker_outcome = None

    class MockSupervisorNode:
        async def __call__(self, state, config):
            from app.core.engine.nodes.supervisor import StateUpdate
            return StateUpdate(messages=[])

    state = MockState()

    # We patch SupervisorNode and route_supervisor where they are defined, since
    # loop.py imports them locally.
    from unittest.mock import patch
    with patch("app.core.engine.nodes.supervisor.SupervisorNode", return_value=MockSupervisorNode()), \
         patch("app.core.engine.routers.route_supervisor", return_value=RoutingTarget.END), \
         patch("app.core.monitoring.activity.activity_monitor.check_cancellation", AsyncMock()):
        await run_node_loop(state, {}, thread_id, max_loop_steps=1)

    assert not old_task.done()  # Old task survived!

    # --- Scenario 2: Transition to WORKER (NEW_COMMAND) ---
    state = MockState()
    with patch("app.core.engine.nodes.supervisor.SupervisorNode", return_value=MockSupervisorNode()), \
         patch("app.core.engine.routers.route_supervisor", return_value=RoutingTarget.WORKER), \
         patch("app.core.monitoring.activity.activity_monitor.check_cancellation", AsyncMock()):
        await run_node_loop(state, {}, thread_id, max_loop_steps=1)

    await asyncio.sleep(0.01)
    assert old_task.done()  # Old task was cancelled by the gate!

    # Cleanup
    await new_task
    worker_registry._records.pop(thread_id, None)
    worker_registry._previous_tasks.pop(thread_id, None)


@pytest.mark.asyncio
async def test_await_and_finalize_no_ghost_re_registration():
    """Verify await_and_finalize only re-registers the old worker if it was never popped/cancelled."""
    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.worker_registry import worker_registry

    # Bind dependencies to voice_input so self._worker_registry is not None
    voice_input.bind(
        executor=MagicMock(),
        state_machine=MagicMock(),
        state_enum=MagicMock(),
        worker_registry=worker_registry,
    )

    async def dummy():
        pass

    async def long_running():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    thread_id = "test-ghost-worker"
    old_task = asyncio.create_task(long_running())
    new_task = asyncio.create_task(dummy())

    # Case A: old task survived (it remains in previous_tasks, i.e., it was a QUERY turn)
    await worker_registry.register_worker(thread_id, old_task, "old task")
    await worker_registry.register_worker(thread_id, new_task, "new task")

    assert thread_id in worker_registry._previous_tasks

    # Awaiting new task should restore old task since it is in previous_tasks
    await voice_input.await_and_finalize(thread_id, new_task, old_task, "old task desc")
    record = await worker_registry.get_worker(thread_id)
    assert record.task == old_task

    # Case B: old task did NOT survive (it was popped/cancelled by loop.py, i.e., NEW_COMMAND)
    old_task2 = asyncio.create_task(long_running())
    new_task2 = asyncio.create_task(dummy())
    await worker_registry.register_worker(thread_id, old_task2, "old task 2")
    await worker_registry.register_worker(thread_id, new_task2, "new task 2")

    # Simulate loop.py pop
    await worker_registry.pop_previous_task(thread_id)
    assert thread_id not in worker_registry._previous_tasks

    # Awaiting new task should NOT restore old task
    await voice_input.await_and_finalize(thread_id, new_task2, old_task2, "old task desc")
    record = await worker_registry.get_worker(thread_id)
    assert record.task == new_task2  # remains the new task record

    # Cleanup long running tasks
    old_task.cancel()
    old_task2.cancel()
    await asyncio.gather(old_task, old_task2, return_exceptions=True)
