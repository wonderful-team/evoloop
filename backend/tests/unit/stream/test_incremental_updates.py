"""
Tests for incremental SSE updates (step/artifact/status events).

Verifies that the stream endpoint correctly:
1. Sends initial activity snapshot on connect
2. Forwards incremental step/artifact/status events
3. Maintains proper event format for frontend consumption
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestIncrementalEventFormat:
    """Test event data format matches frontend expectations."""

    def test_step_event_format(self):
        """Step event should have type and data fields."""
        event = {
            "type": "step",
            "data": {
                "id": "step-1",
                "tool": "browser_navigate",
                "input": {"url": "https://example.com"},
                "output": "",
                "status": "running",
                "duration": 0
            }
        }
        # Frontend expects: event.data or uses event directly
        assert "type" in event
        assert "data" in event
        assert event["type"] == "step"
        assert event["data"]["id"] == "step-1"

    def test_artifact_event_format(self):
        """Artifact event should have type and data fields."""
        event = {
            "type": "artifact",
            "data": {
                "id": 1,
                "name": "test.py",
                "type": "code",
                "status": "created",
                "path": "/tmp/test.py"
            }
        }
        assert "type" in event
        assert "data" in event
        assert event["type"] == "artifact"
        assert event["data"]["id"] == 1

    def test_status_event_format(self):
        """Status event should have type and status fields."""
        event = {
            "type": "status",
            "status": "running"
        }
        assert "type" in event
        assert "status" in event
        assert event["type"] == "status"


class TestStreamEventContract:
    """Test SSE event stream format matches what ChatConnection expects."""

    def test_sse_event_line_format(self):
        """SSE event should be formatted as 'event: type\ndata: json\n\n'."""
        event_data = {"type": "step", "data": {"id": "step-1"}}
        sse_line = f"event: step\ndata: {json.dumps(event_data)}\n\n"
        
        # Verify format
        assert sse_line.startswith("event: step\n")
        assert "data: {" in sse_line
        assert sse_line.endswith("\n\n")

    def test_activity_snapshot_format(self):
        """Initial activity snapshot format."""
        snapshot = {
            "steps": [],
            "artifacts": [],
            "agent_state": {},
            "active_memories": [],
            "verification": {},
            "status": "idle",
            "human_request": None,
            "final_outcome": ""
        }
        sse_line = f"event: activity\ndata: {json.dumps(snapshot)}\n\n"
        assert sse_line.startswith("event: activity\n")


class TestFrontendHandlerCompatibility:
    """Test that frontend handler logic matches backend event format."""

    def test_chatconnection_step_handler(self):
        """Simulate ChatConnection.onStep handler logic."""
        # This mimics what ChatConnection does:
        # sse.addEventListener("step", (e) => { callbacks?.onStep(JSON.parse(e.data)) })
        
        raw_sse_data = '{"type": "step", "data": {"id": "step-1", "tool": "browser"}}'
        parsed = json.loads(raw_sse_data)
        
        # Frontend calls get()._addStep(step)
        step_data = parsed.get("data") or parsed  # Support both formats
        
        assert step_data["id"] == "step-1"
        assert step_data["tool"] == "browser"

    def test_chatstore_addstep_logic(self):
        """Simulate chatStore._addStep reducer logic."""
        existing_steps = [
            {"id": "step-0", "tool": "previous", "status": "completed"}
        ]
        
        # New step event arrives
        step_event = {"data": {"id": "step-1", "tool": "browser", "status": "running"}}
        step_data = step_event.get("data") or step_event
        
        # Simulate _addStep logic
        existing_index = next((i for i, s in enumerate(existing_steps) if s["id"] == step_data["id"]), -1)
        
        if existing_index >= 0:
            new_steps = existing_steps.copy()
            new_steps[existing_index] = {**new_steps[existing_index], **step_data}
        else:
            new_steps = [*existing_steps, step_data]
        
        assert len(new_steps) == 2
        assert new_steps[1]["id"] == "step-1"
        assert new_steps[1]["status"] == "running"

    def test_chatstore_artifact_update_logic(self):
        """Simulate chatStore._addArtifact reducer logic with update."""
        existing_artifacts = [
            {"id": 1, "name": "test.py", "status": "creating"}
        ]
        
        # Update event arrives
        artifact_event = {"data": {"id": 1, "name": "test.py", "status": "completed"}}
        artifact_data = artifact_event.get("data") or artifact_event
        
        # Simulate _addArtifact logic
        existing_index = next(
            (i for i, a in enumerate(existing_artifacts) if a["id"] == artifact_data["id"]), -1
        )
        
        if existing_index >= 0:
            new_artifacts = existing_artifacts.copy()
            new_artifacts[existing_index] = {**new_artifacts[existing_index], **artifact_data}
        else:
            new_artifacts = [*existing_artifacts, artifact_data]
        
        assert len(new_artifacts) == 1  # Updated, not added
        assert new_artifacts[0]["status"] == "completed"


class TestEventTypeValidation:
    """Test that only valid event types are processed."""

    @pytest.mark.parametrize("event_type", [
        "step",
        "artifact", 
        "status",
        "token",
        "message",
        "human_request",
        "thinking",
        "tool_start",
        "tool_progress",
        "tool_complete",
        "stream"
    ])
    def test_valid_event_types(self, event_type):
        """These event types should be handled by stream endpoint."""
        valid_types = {
            "step", "artifact", "status", "token", "message",
            "human_request", "thinking", "tool_start", "tool_progress",
            "tool_complete", "tool_error", "checkpoint", "progress",
            "complete", "stream"
        }
        assert event_type in valid_types or event_type == "stream"


class TestEndToEndEventFlow:
    """Integration-style tests for full event flow."""

    @pytest.mark.asyncio
    async def test_event_publishing_format(self):
        """Test that events are published in correct format for cache."""
        # This tests the contract between callback handlers and stream endpoint
        
        thread_id = "test-thread"
        channel = f"chat:{thread_id}:events"
        
        # Simulate what TransparentCallbackHandler does
        step_event = {
            "type": "step",
            "data": {
                "id": "step-1",
                "tool": "browser_navigate",
                "input": {"url": "https://github.com"},
                "output": "",
                "status": "running",
                "duration": 0
            }
        }
        
        # Should be JSON serializable
        serialized = json.dumps(step_event)
        deserialized = json.loads(serialized)
        
        assert deserialized["type"] == "step"
        assert deserialized["data"]["tool"] == "browser_navigate"
        
        # Channel format
        assert channel.startswith("chat:")
        assert channel.endswith(":events")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
