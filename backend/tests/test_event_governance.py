import asyncio
import json
import logging
from unittest.mock import MagicMock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EventTester")

# Mock Redis/WebSocket Transport
class MockEventBus:
    def __init__(self):
        self.published_messages = []
    
    async def publish(self, channel: str, message: str):
        self.published_messages.append({"channel": channel, "message": json.loads(message)})
        logger.info(f"[MockTransport] Published to {channel}: {message[:100]}...")

async def test_scenario_1_session_lifecycle():
    """Test standard session lifecycle bridging."""
    logger.info(">>> Scenario 1: Session Lifecycle")
    from app.core.events.subscribers.bridge import UniversalBridgeSubscriber
    from app.core.events.schemas import SessionCompletedEvent, SessionCompletedData
    from langchain_core.messages import AIMessage
    
    mock_transport = MockEventBus()
    bridge = UniversalBridgeSubscriber()
    
    # Manually inject mock transport to avoid real Redis
    from app.core.engine.message.event_bus import get_event_bus
    with MagicMock() as mock_get_bus:
        import app.core.events.subscribers.bridge as bridge_mod
        bridge_mod.get_event_bus = lambda: mock_transport
        
        # Create Event
        event = SessionCompletedEvent(
            data=SessionCompletedData(
                thread_id="test_thread_123",
                run_id="run_456",
                summary="Task completed successfully",
                outcome="done"
            )
        )
        
        # Trigger Bridge
        await bridge.handle_event(event)
        
        # Verify
        found = False
        for msg in mock_transport.published_messages:
            if msg["channel"] == "chat:test_thread_123:events" and msg["message"].get("type") == "session_completed":
                logger.info("  ✓ SessionCompletedEvent correctly bridged")
                found = True
        assert found

async def test_scenario_2_background_tasks():
    """Test background task updates and output streaming."""
    logger.info(">>> Scenario 2: Background Tasks")
    from app.core.events.subscribers.bridge import UniversalBridgeSubscriber
    from app.core.tools.event import BackgroundTaskEvent, BackgroundTaskOutputEvent
    
    mock_transport = MockEventBus()
    bridge = UniversalBridgeSubscriber()
    
    import app.core.events.subscribers.bridge as bridge_mod
    bridge_mod.get_event_bus = lambda: mock_transport
    
    # Test Task Update
    task_event = BackgroundTaskEvent(
        thread_id="thread_task",
        task_id="cmd-123",
        action="started",
        task_data={"id": "cmd-123", "title": "test task"}
    )
    await bridge.handle_event(task_event)
    
    # Test Task Output
    output_event = BackgroundTaskOutputEvent(
        thread_id="thread_task",
        task_id="cmd-123",
        output="Hello World"
    )
    await bridge.handle_event(output_event)
    
    # Verify
    updates = [m for m in mock_transport.published_messages if m["message"].get("type") == "task_started"]
    outputs = [m for m in mock_transport.published_messages if m["message"].get("output") == "Hello World"]
    
    assert len(updates) > 0, "Task update not bridged"
    assert len(outputs) > 0, "Task output not bridged"
    logger.info("  ✓ Background task events correctly bridged")

async def test_scenario_3_hitl_interaction():
    """Test Human-In-The-Loop interaction events."""
    logger.info(">>> Scenario 3: HITL Interaction")
    from app.core.events.subscribers.bridge import UniversalBridgeSubscriber
    from app.models.schemas.events import HumanRequestEvent
    
    mock_transport = MockEventBus()
    bridge = UniversalBridgeSubscriber()
    
    import app.core.events.subscribers.bridge as bridge_mod
    bridge_mod.get_event_bus = lambda: mock_transport
    
    event = HumanRequestEvent(
        thread_id="thread_hitl",
        action="create",
        prompt="Please confirm",
        request_type="confirm"
    )
    await bridge.handle_event(event)
    
    found = any(m["message"].get("type") == "human_request" for m in mock_transport.published_messages)
    assert found
    logger.info("  ✓ HumanRequestEvent correctly bridged")

async def test_scenario_4_error_handling():
    """Test error event bridging (Quota, Auth)."""
    logger.info(">>> Scenario 4: Error Handling")
    from app.core.events.subscribers.bridge import UniversalBridgeSubscriber
    from app.models.schemas.events import QuotaExhaustedEvent
    
    mock_transport = MockEventBus()
    bridge = UniversalBridgeSubscriber()
    
    import app.core.events.subscribers.bridge as bridge_mod
    bridge_mod.get_event_bus = lambda: mock_transport
    
    event = QuotaExhaustedEvent(
        thread_id="thread_error",
        title="No Money",
        message="Please top up"
    )
    await bridge.handle_event(event)
    
    found = any(m["message"].get("type") == "quota_exhausted" for m in mock_transport.published_messages)
    assert found
    logger.info("  ✓ Error events correctly bridged")

async def test_scenario_5_summary_rendering():
    """Test that summary templates are correctly rendered in background tasks."""
    logger.info(">>> Scenario 5: Summary Rendering")
    from app.core.tools.background.models import BackgroundTask
    from app.core.tools.schemas import TaskType
    
    task = BackgroundTask(
        task_id="summary-123",
        task_type=TaskType.COMMAND,
        tool_name="execute_command",
        title="evoloop.tool_summary.execute_command",
        metadata={"command": "ls -la", "working_directory": "/tmp/test"}
    )
    
    data = task.to_dict()
    logger.info(f"  Rendered Title: {data.get('title')}")
    
    # Check if title is rendered (not starting with evoloop.tool_summary.)
    assert not data.get("title").startswith("evoloop.tool_summary."), f"Summary template not rendered: {data.get('title')}"
    logger.info("  ✓ Summary template correctly rendered")

async def run_all_tests():
    try:
        await test_scenario_1_session_lifecycle()
        await test_scenario_2_background_tasks()
        await test_scenario_3_hitl_interaction()
        await test_scenario_4_error_handling()
        await test_scenario_5_summary_rendering()
        logger.info("\n🎉 ALL TESTS PASSED SUCCESSFULLY")
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}", exc_info=True)
        exit(1)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
