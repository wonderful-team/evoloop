"""
API Layer Tests - Conversations Endpoint
Covers: CONV-001 to CONV-004
"""
import pytest
import httpx

from tests.config import config


class TestConversationsEndpoint:
    """Test suite for /api/v1/conversations endpoint."""

    # CONV-001: List Conversations
    @pytest.mark.asyncio
    async def test_conv_001_list_conversations(self, async_client):
        """Test listing conversations for a project."""
        response = await async_client.get(
            f"/api/v1/conversations/?project_id={config.PROJECT_ID}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))
        
        # If dict with data key
        if isinstance(data, dict):
            assert "data" in data or "conversations" in data or "items" in data

    # CONV-002: Get Conversation Messages
    @pytest.mark.asyncio
    async def test_conv_002_get_messages(self, async_client, thread_id):
        """Test retrieving messages for a conversation."""
        # First create a message
        await async_client.post("/api/v1/chat", json={
            "message": "Test message for history",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        # Wait a bit for persistence
        import asyncio
        await asyncio.sleep(1)
        
        # Get messages
        response = await async_client.get(
            f"/api/v1/conversations/{thread_id}/messages"
        )
        
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            # Should return list of messages or wrapped object
            assert isinstance(data, (list, dict))

    # CONV-003: Delete Conversation
    @pytest.mark.asyncio
    async def test_conv_003_delete_conversation(self, async_client, thread_id):
        """Test deleting a conversation."""
        # First create a conversation
        await async_client.post("/api/v1/chat", json={
            "message": "Message to be deleted",
            "thread_id": thread_id,
            "project_id": config.PROJECT_ID
        })
        
        import asyncio
        await asyncio.sleep(1)
        
        # Delete it
        response = await async_client.delete(
            f"/api/v1/conversations/{thread_id}"
        )
        
        assert response.status_code in [200, 204, 404]

    # CONV-004: Pagination
    @pytest.mark.asyncio
    async def test_conv_004_pagination(self, async_client):
        """Test pagination of conversations list."""
        response = await async_client.get(
            f"/api/v1/conversations/?project_id={config.PROJECT_ID}&page=1&page_size=5"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check pagination structure if present
        if isinstance(data, dict):
            # May have pagination info
            if "page" in data:
                assert data["page"] == 1
            if "page_size" in data or "per_page" in data:
                size = data.get("page_size") or data.get("per_page")
                assert size == 5


class TestConversationsValidation:
    """Validation tests for conversations endpoint."""

    @pytest.mark.asyncio
    async def test_list_without_project_id(self, async_client):
        """Test listing without project_id."""
        response = await async_client.get("/api/v1/conversations/")
        
        # Should return all or require project_id
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation(self, async_client):
        """Test getting messages for non-existent conversation."""
        response = await async_client.get(
            "/api/v1/conversations/nonexistent-thread-id/messages"
        )
        
        assert response.status_code in [200, 404]  # Empty list or not found

    @pytest.mark.asyncio
    async def test_invalid_page_params(self, async_client):
        """Test invalid pagination parameters."""
        response = await async_client.get(
            f"/api/v1/conversations/?project_id={config.PROJECT_ID}&page=-1&page_size=0"
        )
        
        assert response.status_code in [200, 400, 422]
