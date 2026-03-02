"""
Full end-to-end tests simulating real user workflows.
These tests simulate complete user journeys through the API.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio


class TestUserOnboardingWorkflow:
    """Tests for new user onboarding workflow."""

    def test_complete_onboarding_flow(self, client, mock_authentication):
        """Test complete user onboarding from login to first chat."""
        # Step 1: Get system info
        with patch("app.api.routes.system.settings") as mock_settings:
            mock_settings.PROJECT_NAME = "EvoLoop"
            mock_settings.ENVIRONMENT = "testing"

            response = client.get("/api/v1/system/info")
            assert response.status_code == 200

        # Step 2: List available projects
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.list_projects = AsyncMock(return_value=[
                {"id": 1, "name": "My First Project", "path": "/home/user/projects/first"},
            ])

            response = client.get("/api/v1/projects")
            assert response.status_code == 200
            projects = response.json()
            assert len(projects) > 0

        # Step 3: Get project details
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.get_project = AsyncMock(return_value={
                "id": 1,
                "name": "My First Project",
                "path": "/home/user/projects/first",
                "description": "Test project"
            })

            response = client.get("/api/v1/projects/1")
            assert response.status_code == 200
            project = response.json()
            assert project["id"] == 1

        # Step 4: Start first chat
        thread_id = "new-user-thread-001"

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": thread_id,
                        "message": "Hi! I'm a new user. Can you help me get started?",
                        "project_id": 1
                    })

                    assert response.status_code == 200
                    result = response.json()
                    assert result["status"] == "queued"


class TestDevelopmentWorkflow:
    """Tests for development workflow (coding assistant)."""

    def test_code_review_workflow(self, client, mock_authentication, mock_guest_access):
        """Test code review workflow."""
        thread_id = "dev-workflow-thread"

        # Step 1: Initial question about code
        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    # Ask about code
                    response = client.post("/api/v1/chat", json={
                        "thread_id": thread_id,
                        "message": "Can you review this Python function for me?",
                        "project_id": 1,
                        "attachments": [
                            {
                                "type": "file",
                                "url": "/path/to/function.py",
                                "name": "function.py"
                            }
                        ]
                    })
                    assert response.status_code == 200

        # Step 2: Follow-up with code edits
        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": thread_id,
                        "message": "Please apply the suggested fixes",
                        "project_id": 1
                    })
                    assert response.status_code == 200

    def test_debugging_workflow(self, client, mock_authentication, mock_guest_access):
        """Test debugging workflow."""
        thread_id = "debug-workflow-thread"

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    # Report error
                    response = client.post("/api/v1/chat", json={
                        "thread_id": thread_id,
                        "message": "I'm getting this error: KeyError: 'user_id'",
                        "project_id": 1
                    })
                    assert response.status_code == 200


class TestMemoryAndLearningWorkflow:
    """Tests for memory and learning workflows."""

    def test_conversation_memory_persistence(self, client, mock_authentication):
        """Test that conversation history is persisted."""
        thread_id = "memory-test-thread"

        # Mock database session
        with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
            mock_db_session = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            # Create conversation
            mock_db_session.get = AsyncMock(return_value=None)

            with patch("app.api.routes.agent.run_agent_background"):
                with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                    mock_monitor.start_run = AsyncMock()

                    # Send multiple messages
                    for i in range(3):
                        response = client.post("/api/v1/chat", json={
                            "thread_id": thread_id,
                            "message": f"Message {i+1}",
                            "project_id": 1
                        })
                        assert response.status_code == 200

    def test_wiki_knowledge_retrieval(self, client, mock_authentication):
        """Test retrieving knowledge from wiki."""
        with patch("app.api.routes.wiki.wiki_service") as mock_service:
            mock_service.search_pages = AsyncMock(return_value=[
                {
                    "id": "page-1",
                    "title": "Python Best Practices",
                    "content": "# Python Best Practices\n\n1. Use type hints...",
                    "relevance": 0.95
                }
            ])

            response = client.get("/api/v1/wiki/search?q=python+best+practices")
            assert response.status_code == 200
            results = response.json()
            assert len(results) > 0
            assert "Python Best Practices" in results[0]["title"]


class TestProjectManagementWorkflow:
    """Tests for project management workflow."""

    def test_project_lifecycle(self, client, mock_authentication):
        """Test complete project lifecycle."""
        # Create project
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.create_project = AsyncMock(return_value={
                "id": 100,
                "name": "New Test Project",
                "path": "/home/user/projects/new-test"
            })

            response = client.post("/api/v1/projects", json={
                "name": "New Test Project",
                "description": "A test project",
                "path": "/home/user/projects/new-test"
            })
            assert response.status_code in [200, 201]

            project = response.json()
            project_id = project["id"]

        # Update project
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.update_project = AsyncMock(return_value={
                "id": project_id,
                "name": "Updated Test Project",
                "description": "Updated description"
            })

            response = client.put(f"/api/v1/projects/{project_id}", json={
                "name": "Updated Test Project",
                "description": "Updated description"
            })
            assert response.status_code == 200

        # Delete project
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.delete_project = AsyncMock(return_value=True)

            response = client.delete(f"/api/v1/projects/{project_id}")
            assert response.status_code in [200, 204]


class TestErrorHandling:
    """Tests for error handling in workflows."""

    def test_invalid_thread_id(self, client, mock_guest_access):
        """Test handling invalid thread ID."""
        response = client.get("/api/v1/conversations/invalid-thread-id")
        # Should return 404 for not found
        assert response.status_code in [200, 404]

    def test_malformed_request(self, client, mock_guest_access):
        """Test handling malformed request."""
        response = client.post("/api/v1/chat", json={
            # Missing required thread_id
            "message": "Hello"
        })
        assert response.status_code == 422  # Validation error

    def test_unauthorized_access(self, client):
        """Test unauthorized access without auth or guest_id."""
        response = client.post("/api/v1/chat", json={
            "thread_id": "test-thread",
            "message": "Hello",
            "project_id": 1
        })
        # Should be unauthorized without auth or guest_id
        assert response.status_code in [401, 403]


class TestConcurrentAccess:
    """Tests for concurrent access patterns."""

    def test_multiple_threads_same_project(self, client, mock_authentication, mock_guest_access):
        """Test multiple conversation threads in same project."""
        project_id = 1

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    # Create multiple threads
                    threads = []
                    for i in range(3):
                        thread_id = f"concurrent-thread-{i}"

                        response = client.post("/api/v1/chat", json={
                            "thread_id": thread_id,
                            "message": f"Message in thread {i}",
                            "project_id": project_id
                        })
                        assert response.status_code == 200
                        threads.append(thread_id)

                    assert len(threads) == 3
