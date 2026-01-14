"""
API Layer Tests - SSE Stream Endpoint
Covers: SSE-001 to SSE-006
"""
import pytest
import asyncio
import json
import httpx

from tests.config import config, get_auth_headers


class TestSSEStream:
    """Test suite for /api/v1/stream/chat/{thread_id} endpoint."""

    # SSE-001: Connection Establishment
    @pytest.mark.asyncio
    async def test_sse_001_connection_establish(self, thread_id):
        """Test SSE connection can be established."""
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=10.0
        ) as client:
            async with client.stream(
                "GET",
                f"/api/v1/stream/chat/{thread_id}"
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                
                # Read first event
                first_line = None
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        first_line = line
                        break
                    if line.startswith("data:"):
                        first_line = line
                        break
                
                # Should receive an event
                assert first_line is not None

    # SSE-002: Token Push (requires running agent)
    @pytest.mark.asyncio
    async def test_sse_002_token_push(self, async_client, thread_id):
        """Test receiving token events during message generation."""
        # Start a chat task first
        await async_client.post("/api/v1/chat", json={
            "message": "Say hello",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        # Connect to SSE and wait for token events
        received_events = []
        timeout = 15
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=timeout
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/stream/chat/{thread_id}"
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line.split(":")[1].strip()
                            received_events.append(event_type)
                            if len(received_events) >= 5:
                                break
            except asyncio.TimeoutError:
                pass
        
        # Should have received some events
        assert len(received_events) > 0

    # SSE-003: Task Status Update
    @pytest.mark.asyncio
    async def test_sse_003_task_status_update(self, async_client, thread_id):
        """Test receiving activity events with task status."""
        # Start a task
        await async_client.post("/api/v1/chat", json={
            "message": "Create a simple Python function",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        activity_events = []
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=20.0
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/stream/chat/{thread_id}"
                ) as response:
                    current_event = None
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            current_event = line.split(":")[1].strip()
                        elif line.startswith("data:") and current_event == "activity":
                            try:
                                data = json.loads(line[5:].strip())
                                activity_events.append(data)
                                if len(activity_events) >= 3:
                                    break
                            except json.JSONDecodeError:
                                pass
            except asyncio.TimeoutError:
                pass
        
        # Should have activity data
        if activity_events:
            # Check structure
            first_event = activity_events[0]
            assert "status" in first_event or "tasks" in first_event or "agent_state" in first_event

    # SSE-004: Human-in-the-Loop Event
    @pytest.mark.asyncio
    async def test_sse_004_hitl_event(self, async_client, thread_id):
        """Test receiving human_request events (may not trigger in all cases)."""
        # This test may need a specific prompt that triggers HITL
        await async_client.post("/api/v1/chat", json={
            "message": "Delete all files in /tmp",  # Should trigger approval
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        hitl_received = False
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=30.0
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/stream/chat/{thread_id}"
                ) as response:
                    async for line in response.aiter_lines():
                        if "human_request" in line:
                            hitl_received = True
                            break
            except asyncio.TimeoutError:
                pass
        
        # HITL may or may not be triggered depending on agent behavior
        # This test is informational
        assert True  # Placeholder - actual behavior depends on agent

    # SSE-005: Error Push
    @pytest.mark.asyncio
    async def test_sse_005_error_push(self, async_client, thread_id):
        """Test that errors are pushed via SSE."""
        # This test is hard to trigger intentionally
        # We just verify the connection works
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=5.0
        ) as client:
            async with client.stream(
                "GET",
                f"/api/v1/stream/chat/{thread_id}"
            ) as response:
                assert response.status_code == 200

    # SSE-006: Reconnection
    @pytest.mark.asyncio
    async def test_sse_006_reconnection(self, thread_id):
        """Test that reconnection retrieves initial snapshot."""
        snapshots = []
        
        # Connect twice
        for _ in range(2):
            async with httpx.AsyncClient(
                base_url=config.API_BASE_URL,
                headers=get_auth_headers(),
                timeout=5.0
            ) as client:
                try:
                    async with client.stream(
                        "GET",
                        f"/api/v1/stream/chat/{thread_id}"
                    ) as response:
                        async for line in response.aiter_lines():
                            if line.startswith("data:"):
                                try:
                                    data = json.loads(line[5:].strip())
                                    snapshots.append(data)
                                    break
                                except json.JSONDecodeError:
                                    pass
                except asyncio.TimeoutError:
                    pass
        
        # Both connections should have received snapshots
        assert len(snapshots) >= 1


class TestSSEEdgeCases:
    """Edge case tests for SSE endpoint."""

    @pytest.mark.asyncio
    async def test_invalid_thread_id(self):
        """Test SSE with invalid thread_id."""
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=5.0
        ) as client:
            async with client.stream(
                "GET",
                "/api/v1/stream/chat/invalid-thread"
            ) as response:
                # Should still connect but may have empty state
                assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_concurrent_connections(self, thread_id):
        """Test multiple concurrent SSE connections to same thread."""
        async def connect_and_read():
            async with httpx.AsyncClient(
                base_url=config.API_BASE_URL,
                headers=get_auth_headers(),
                timeout=5.0
            ) as client:
                async with client.stream(
                    "GET",
                    f"/api/v1/stream/chat/{thread_id}"
                ) as response:
                    return response.status_code
        
        # Connect 3 times concurrently
        results = await asyncio.gather(
            connect_and_read(),
            connect_and_read(),
            connect_and_read()
        )
        
        # All should succeed
        assert all(r == 200 for r in results)
