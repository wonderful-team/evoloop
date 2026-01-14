"""
API Layer Tests - Chat Endpoint
Covers: CHAT-001 to CHAT-006
"""
import pytest
import httpx
from unittest.mock import patch, AsyncMock

from tests.config import config


class TestChatEndpoint:
    """Test suite for /api/v1/chat endpoint."""

    # CHAT-001: Basic Message Sending
    @pytest.mark.asyncio
    async def test_chat_001_basic_message(self, async_client, thread_id):
        """Test basic message sending returns queued status."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "Hello, this is a test message",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["queued", "running"]

    # CHAT-002: Multimodal Message (Image)
    @pytest.mark.asyncio
    async def test_chat_002_multimodal_image(self, async_client, thread_id):
        """Test message with image attachment."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "分析这张图片",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID,
            "attachments": [{
                "type": "image",
                "url": "https://example.com/test.png"
            }]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["queued", "running"]

    # CHAT-003: Empty Message Rejection
    @pytest.mark.asyncio
    async def test_chat_003_empty_message(self, async_client, thread_id):
        """Test empty message is rejected or ignored."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        # Should either return error or be ignored
        assert response.status_code in [200, 400, 422]

    # CHAT-004: Invalid Thread ID
    @pytest.mark.asyncio
    async def test_chat_004_invalid_thread_id(self, async_client):
        """Test invalid thread_id handling."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "Test message",
            "thread_id": "invalid-uuid-format",
            "project_id": config.PROJECT_ID
        })
        
        # Should either create new conversation or return error
        assert response.status_code in [200, 400, 422]

    # CHAT-005: Stop Running Task
    @pytest.mark.asyncio
    async def test_chat_005_stop_task(self, async_client, thread_id):
        """Test stopping a running task."""
        # First send a message to start a task
        await async_client.post("/api/v1/chat", json={
            "message": "Write a long essay about Python",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        # Then try to stop it
        response = await async_client.post("/api/v1/stop", json={
            "thread_id": thread_id
        })
        
        assert response.status_code in [200, 202, 404]

    # CHAT-006: Resume Interrupted Task
    @pytest.mark.asyncio
    async def test_chat_006_resume_task(self, async_client, thread_id):
        """Test resuming an interrupted task."""
        response = await async_client.post("/api/v1/resume", json={
            "thread_id": thread_id,
            "user_input": "Continue with the task"
        })
        
        # May return 404 if no interrupted task exists
        assert response.status_code in [200, 202, 404]


class TestChatEndpointValidation:
    """Validation and edge case tests for chat endpoint."""

    @pytest.mark.asyncio
    async def test_missing_thread_id(self, async_client):
        """Test request without thread_id."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "Test",
            "project_id": config.PROJECT_ID
        })
        
        # Should auto-generate or return error
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_missing_project_id(self, async_client, thread_id):
        """Test request without project_id."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "Test",
            "thread_id": thread_id
        })
        
        # Should use default or return error
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_very_long_message(self, async_client, thread_id):
        """Test handling of very long messages."""
        long_message = "这是一条很长的消息。" * 1000  # ~10000 chars
        
        response = await async_client.post("/api/v1/chat", json={
            "message": long_message,
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        assert response.status_code in [200, 400, 413]

    @pytest.mark.asyncio
    async def test_special_characters(self, async_client, thread_id):
        """Test message with special characters."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "Test with special chars: <script>alert('xss')</script> & \"quotes\" 'single'",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        assert response.status_code == 200

    @pytest.mark.asyncio 
    async def test_unicode_message(self, async_client, thread_id):
        """Test message with unicode characters."""
        response = await async_client.post("/api/v1/chat", json={
            "message": "测试中文 🎉 日本語 العربية",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        assert response.status_code == 200
