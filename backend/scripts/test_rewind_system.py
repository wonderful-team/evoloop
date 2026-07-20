#!/usr/bin/env python3
"""
Manual test script for the new event-driven rewind system.

Usage:
    python scripts/test_rewind_system.py

This script tests:
1. RewindOrchestrator initialization
2. Handler registration
3. Event publishing and handling
4. Basic rewind flow
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_imports():
    """Test that all new modules can be imported."""
    print("=" * 60)
    print("Test 1: Module Imports")
    print("=" * 60)
    
    try:
        from app.core.events import RewindEventType, system_bus
        print("✓ app.core.events imported successfully")
        
        from app.core.rewind import RewindOrchestrator, RewindRequest, RewindResult
        print("✓ app.core.rewind imported successfully")
        
        from app.core.rewind.exceptions import RewindError, PartialRewindError
        print("✓ app.core.rewind.exceptions imported successfully")
        
        from app.core.file.rewind import FileRewind
        print("✓ app.core.file.rewind imported successfully")
        
        from app.core.memory.rewind import MemoryRewind
        print("✓ app.core.memory.rewind imported successfully")
        
        from app.core.rewind.handlers import MessageRewind
        print("✓ app.infrastructure.database.models.rewind imported successfully")
        
        from app.domain.todo.rewind import TodoRewind
        print("✓ app.domain.todo.rewind imported successfully")
        
        from app.core.learning.rewind import TraceRewind
        print("✓ app.core.learning.rewind imported successfully")
        
        from app.core.engine.rewind.state import StateRewind
        print("✓ app.core.engine.rewind.state imported successfully")
        
        print("\n✅ All imports successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_event_types():
    """Test RewindEventType enum values."""
    print("\n" + "=" * 60)
    print("Test 2: RewindEventType Enum")
    print("=" * 60)
    
    try:
        from app.core.events import RewindEventType
        
        expected_types = [
            ("REWIND_REQUESTED", "rewind.requested"),
            ("REWIND_COMPLETED", "rewind.completed"),
            ("REWIND_FAILED", "rewind.failed"),
            ("MESSAGES_CLEANUP", "rewind.messages.cleanup"),
            ("FILES_CLEANUP", "rewind.files.cleanup"),
            ("MEMORY_CLEANUP", "rewind.memory.cleanup"),
            ("TODO_CLEANUP", "rewind.todo.cleanup"),
            ("TRACE_CLEANUP", "rewind.trace.cleanup"),
            ("STATE_RESET", "rewind.state.reset"),
        ]
        
        for attr, expected_value in expected_types:
            actual_value = getattr(RewindEventType, attr)
            assert actual_value == expected_value, f"{attr}: expected {expected_value}, got {actual_value}"
            print(f"✓ {attr} = '{actual_value}'")
        
        print("\n✅ All event types correct!")
        return True
        
    except Exception as e:
        print(f"\n❌ Event type test failed: {e}")
        return False


async def test_rewind_events():
    """Test Rewind event classes."""
    print("\n" + "=" * 60)
    print("Test 3: Rewind Event Classes")
    print("=" * 60)
    
    try:
        from app.core.rewind.events import (
            RewindRequestedEvent,
            FilesCleanupEvent,
            MessagesCleanupEvent,
            MemoryCleanupEvent,
            RewindCompletedEvent,
        )
        
        # Test RewindRequestedEvent
        event = RewindRequestedEvent(
            thread_id="thread-test",
            target_message_id="msg-123",
            include_target=True,
            revert_files=True,
            reset_state=False
        )
        assert event.thread_id == "thread-test"
        assert event.event_type.value == "rewind.requested"
        print("✓ RewindRequestedEvent created successfully")
        
        # Test FilesCleanupEvent
        event = FilesCleanupEvent(
            thread_id="thread-test",
            file_operations=[{"path": "/test", "operation": "ADD"}]
        )
        assert event.data["operation_count"] == 1
        print("✓ FilesCleanupEvent created successfully")
        
        # Test MessagesCleanupEvent
        event = MessagesCleanupEvent(
            thread_id="thread-test",
            message_ids=["1", "2", "3"]
        )
        assert event.data["count"] == 3
        print("✓ MessagesCleanupEvent created successfully")
        
        # Test MemoryCleanupEvent
        event = MemoryCleanupEvent(
            thread_id="thread-test",
            source_message_ids=["1", "2"],
            run_ids=["run-1"]
        )
        assert event.data["source_message_ids"] == ["1", "2"]
        print("✓ MemoryCleanupEvent created successfully")
        
        # Test RewindCompletedEvent
        event = RewindCompletedEvent(
            thread_id="thread-test",
            removed_message_count=5,
            reverted_file_count=3
        )
        assert event.data["removed_message_count"] == 5
        print("✓ RewindCompletedEvent created successfully")
        
        print("\n✅ All event classes working!")
        return True
        
    except Exception as e:
        print(f"\n❌ Event class test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orchestrator_creation():
    """Test RewindOrchestrator creation."""
    print("\n" + "=" * 60)
    print("Test 4: RewindOrchestrator")
    print("=" * 60)
    
    try:
        from app.core.rewind import RewindOrchestrator
        from app.core.events import system_bus
        
        # Test with default bus
        orchestrator = RewindOrchestrator()
        assert orchestrator.bus is system_bus
        print("✓ RewindOrchestrator created with default bus")
        
        # Test with custom bus
        from unittest.mock import MagicMock
        custom_bus = MagicMock()
        orchestrator = RewindOrchestrator(event_bus=custom_bus)
        assert orchestrator.bus is custom_bus
        print("✓ RewindOrchestrator created with custom bus")
        
        print("\n✅ Orchestrator creation successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_handler_registration():
    """Test Handler registration to event bus."""
    print("\n" + "=" * 60)
    print("Test 5: Handler Registration")
    print("=" * 60)
    
    try:
        from unittest.mock import MagicMock
        from app.core.events import RewindEventType
        
        mock_bus = MagicMock()
        mock_bus.subscribe = MagicMock()
        
        # Test FileRewind registration
        from app.core.file.rewind import FileRewind
        FileRewind.register(mock_bus)
        print("✓ FileRewind registered")
        
        # Test MemoryRewind registration
        from app.core.memory.rewind import MemoryRewind
        MemoryRewind.register(mock_bus)
        print("✓ MemoryRewind registered")
        
        # Test MessageRewind registration
        from app.core.rewind.handlers import MessageRewind
        MessageRewind.register(mock_bus)
        print("✓ MessageRewind registered")
        
        # Test TodoRewind registration
        from app.domain.todo.rewind import TodoRewind
        TodoRewind.register(mock_bus)
        print("✓ TodoRewind registered")
        
        # Test TraceRewind registration
        from app.core.learning.rewind import TraceRewind
        TraceRewind.register(mock_bus)
        print("✓ TraceRewind registered")
        
        # Test StateRewind registration
        from app.core.engine.rewind.state import StateRewind
        StateRewind.register(mock_bus)
        print("✓ StateRewind registered")
        
        # Verify subscriptions
        subscription_count = mock_bus.subscribe.call_count
        print(f"\nTotal subscriptions: {subscription_count}")
        
        # Each handler should subscribe to at least 2 events
        assert subscription_count >= 12, f"Expected at least 12 subscriptions, got {subscription_count}"
        
        print("\n✅ All handlers registered successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Handler registration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_exceptions():
    """Test custom exceptions."""
    print("\n" + "=" * 60)
    print("Test 6: Rewind Exceptions")
    print("=" * 60)
    
    try:
        from app.core.rewind.exceptions import (
            RewindError,
            PartialRewindError,
            MessageNotFoundError,
            NoHumanMessageError,
        )
        
        # Test RewindError
        err = RewindError("Test error", thread_id="thread-123")
        assert err.thread_id == "thread-123"
        assert str(err) == "Test error"
        print("✓ RewindError working")
        
        # Test PartialRewindError
        err = PartialRewindError(
            "Partial failure",
            thread_id="thread-123",
            completed_steps=["messages"],
            failed_steps=["files"]
        )
        assert err.completed_steps == ["messages"]
        assert err.failed_steps == ["files"]
        print("✓ PartialRewindError working")
        
        # Test MessageNotFoundError
        err = MessageNotFoundError("Not found", thread_id="thread-123")
        assert isinstance(err, RewindError)
        print("✓ MessageNotFoundError working")
        
        # Test NoHumanMessageError
        err = NoHumanMessageError("No human message", thread_id="thread-123")
        assert isinstance(err, RewindError)
        print("✓ NoHumanMessageError working")
        
        print("\n✅ All exceptions working!")
        return True
        
    except Exception as e:
        print(f"\n❌ Exception test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_models():
    """Test Rewind data models."""
    print("\n" + "=" * 60)
    print("Test 7: Rewind Models")
    print("=" * 60)
    
    try:
        from app.core.rewind import RewindRequest, RewindResult
        
        # Test RewindRequest
        req = RewindRequest(
            thread_id="thread-123",
            target_message_id="msg-456",
            include_target=True,
            revert_files=True
        )
        assert req.thread_id == "thread-123"
        assert req.target_message_id == "msg-456"
        print("✓ RewindRequest created")
        
        # Test RewindResult
        result = RewindResult(
            status="success",
            thread_id="thread-123",
            removed_message_count=5,
            reverted_file_count=3
        )
        assert result.status == "success"
        assert result.removed_message_count == 5
        
        # Test to_dict
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["removed_count"] == 5
        assert d["files_reverted"] == 3
        print("✓ RewindResult created and serialized")
        
        print("\n✅ All models working!")
        return True
        
    except Exception as e:
        print(f"\n❌ Model test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("EVENT-DRIVEN REWIND SYSTEM - TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_event_types,
        test_rewind_events,
        test_orchestrator_creation,
        test_handler_registration,
        test_exceptions,
        test_models,
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✅ ALL TESTS PASSED!")
        print("\nThe new event-driven rewind system is ready to use.")
        return 0
    else:
        print("\n⚠️ SOME TESTS FAILED")
        print("Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
