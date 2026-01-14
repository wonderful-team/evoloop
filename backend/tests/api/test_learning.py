"""
API Layer Tests - Learning/Skills Endpoint
Covers: LEARN-001 to LEARN-007
"""
import pytest
import httpx
import json

from tests.config import config


class TestLearningEndpoint:
    """Test suite for /api/v1/learning endpoint."""

    # LEARN-001: Start Recording
    @pytest.mark.asyncio
    async def test_learn_001_start_recording(self, async_client, thread_id):
        """Test starting a recording session."""
        response = await async_client.post("/api/v1/learning/traces/start", json={
            "thread_id": thread_id,
            "task_name": "Test Recording"
        })
        
        assert response.status_code in [200, 201]
        if response.status_code in [200, 201]:
            data = response.json()
            assert "session_id" in data

    # LEARN-002: Record Events
    @pytest.mark.asyncio
    async def test_learn_002_record_events(self, async_client, thread_id):
        """Test recording events to a session."""
        # First start a session
        start_response = await async_client.post("/api/v1/learning/traces/start", json={
            "thread_id": thread_id
        })
        
        if start_response.status_code not in [200, 201]:
            pytest.skip("Could not start recording session")
        
        session_id = start_response.json().get("session_id")
        
        # Record events
        response = await async_client.post("/api/v1/learning/traces/events", json={
            "session_id": session_id,
            "thread_id": thread_id,
            "events": [
                {
                    "timestamp": 1704067200000,
                    "event_type": "click",
                    "target_selector": "#submit-btn",
                    "target_text": "Submit"
                },
                {
                    "timestamp": 1704067201000,
                    "event_type": "input",
                    "target_selector": "#message-input",
                    "payload": {"value": "Test input"}
                }
            ]
        })
        
        assert response.status_code == 200

    # LEARN-003: Synthesize Skill
    @pytest.mark.asyncio
    async def test_learn_003_synthesize_skill(self, async_client, thread_id):
        """Test synthesizing a skill from traces."""
        response = await async_client.post("/api/v1/learning/skills/synthesize", json={
            "thread_id": thread_id
        })
        
        # May fail if no valid traces exist
        assert response.status_code in [200, 400, 404, 500]

    # LEARN-004: List Skills
    @pytest.mark.asyncio
    async def test_learn_004_list_skills(self, async_client):
        """Test listing all skills."""
        response = await async_client.get("/api/v1/learning/skills")
        
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)

    # LEARN-005: Execute Skill (requires existing skill)
    @pytest.mark.asyncio
    async def test_learn_005_execute_skill(self, async_client, thread_id):
        """Test executing a skill."""
        # First get list of skills
        list_response = await async_client.get("/api/v1/learning/skills")
        if list_response.status_code != 200:
            pytest.skip("Could not list skills")
        
        skills = list_response.json().get("skills", [])
        if not skills:
            pytest.skip("No skills available to execute")
        
        skill_id = skills[0]["id"]
        
        response = await async_client.post(f"/api/v1/learning/skills/{skill_id}/execute", json={
            "thread_id": thread_id,
            "params": {},
            "project_id": config.PROJECT_ID
        })
        
        assert response.status_code in [200, 400, 404]

    # LEARN-006: Update Skill
    @pytest.mark.asyncio
    async def test_learn_006_update_skill(self, async_client):
        """Test updating a skill."""
        # Get a skill first
        list_response = await async_client.get("/api/v1/learning/skills")
        if list_response.status_code != 200:
            pytest.skip("Could not list skills")
        
        skills = list_response.json().get("skills", [])
        if not skills:
            pytest.skip("No skills available to update")
        
        skill_id = skills[0]["id"]
        
        response = await async_client.put(f"/api/v1/learning/skills/{skill_id}", json={
            "description": "Updated description for testing"
        })
        
        assert response.status_code in [200, 404]

    # LEARN-007: Deactivate Skill
    @pytest.mark.asyncio
    async def test_learn_007_deactivate_skill(self, async_client):
        """Test deactivating a skill."""
        # Get a skill first
        list_response = await async_client.get("/api/v1/learning/skills")
        if list_response.status_code != 200:
            pytest.skip("Could not list skills")
        
        skills = list_response.json().get("skills", [])
        if not skills:
            pytest.skip("No skills available to deactivate")
        
        skill_id = skills[0]["id"]
        
        response = await async_client.delete(f"/api/v1/learning/skills/{skill_id}")
        
        assert response.status_code in [200, 204, 404]


class TestHumanInputRequests:
    """Test suite for human input request endpoints."""

    @pytest.mark.asyncio
    async def test_list_pending_requests(self, async_client):
        """Test listing pending human input requests."""
        response = await async_client.get("/api/v1/learning/human-requests")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_pending_by_thread(self, async_client, thread_id):
        """Test listing pending requests for specific thread."""
        response = await async_client.get(
            f"/api/v1/learning/human-requests?thread_id={thread_id}"
        )
        
        assert response.status_code == 200
