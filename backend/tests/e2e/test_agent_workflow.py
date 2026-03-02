"""
E2E tests for agent workflows.
Tests complete agent interaction flows.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json


class TestAgentChatWorkflow:
    """Tests for complete agent chat workflow."""

    def test_simple_chat_workflow(self, client, mock_guest_access):
        """Test a simple chat workflow."""
        thread_id = "test-thread-123"

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            mock_bg.return_value = None

            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                # Step 1: Send a message
                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    # Mock conversation lookup
                    mock_db_session.get = AsyncMock(return_value=None)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": thread_id,
                        "message": "Hello, can you help me with a Python project?",
                        "project_id": 1
                    })

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "queued"
                    assert data["thread_id"] == thread_id

                    # Verify background task was queued
                    mock_bg.assert_called_once()

    def test_chat_with_attachments(self, client, mock_guest_access):
        """Test chat with file attachments."""
        thread_id = "test-thread-attachments"

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db_session = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": thread_id,
                        "message": "Please review this file",
                        "project_id": 1,
                        "attachments": [
                            {
                                "type": "file",
                                "url": "/path/to/file.py",
                                "name": "file.py"
                            }
                        ]
                    })

                    assert response.status_code == 200

    def test_retry_chat(self, client, mock_guest_access):
        """Test retrying a chat message."""
        thread_id = "test-thread-retry"

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.history_service") as mock_history:
                mock_history.perform_rewind = AsyncMock(return_value={
                    "files_reverted": 2
                })

                with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                    mock_monitor.start_run = AsyncMock()

                    with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                        mock_db_session = AsyncMock()
                        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                        # Mock finding last human message
                        mock_last_msg = MagicMock()
                        mock_last_msg.content = "Original message"
                        mock_db_session.execute = AsyncMock()
                        mock_result = AsyncMock()
                        mock_result.scalar_one_or_none = MagicMock(return_value=mock_last_msg)
                        mock_db_session.execute.return_value = mock_result

                        response = client.post("/api/v1/chat/retry", json={
                            "thread_id": thread_id,
                            "message": "retry",
                            "project_id": 1,
                            "revert_files": True
                        })

                        assert response.status_code == 200
                        data = response.json()
                        assert data["action"] == "retry"
                        assert "files_reverted" in data


class TestWebhookWorkflow:
    """Tests for webhook event workflow."""

    def test_project_switch_webhook(self, client):
        """Test project switch webhook."""
        with patch("app.api.routes.agent.indexing_manager") as mock_indexing:
            mock_indexing.start_watching = AsyncMock()
            mock_indexing.run_indexing_background = AsyncMock()

            with patch("app.api.routes.agent.IndexingService") as mock_service_class:
                mock_service = MagicMock()
                mock_service.get_or_create_repo = AsyncMock(return_value=MagicMock(id=1))
                mock_service_class.return_value = mock_service

                response = client.post("/api/v1/webhook", json={
                    "source": "evocloud",
                    "event_type": "project_switched",
                    "payload": {
                        "new_project": {
                            "path": "/path/to/new/project",
                            "name": "New Project"
                        }
                    }
                })

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "switched"

    def test_generic_webhook(self, client, mock_guest_access):
        """Test generic webhook event."""
        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.domain.integration.adapters.EventAdapter.adapt") as mock_adapt:
                from langchain_core.messages import HumanMessage
                mock_adapt.return_value = [HumanMessage(content="Event occurred")]

                response = client.post("/api/v1/webhook", json={
                    "source": "github",
                    "event_type": "push",
                    "payload": {
                        "ref": "refs/heads/main",
                        "commits": []
                    }
                })

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "accepted"


class TestResumeWorkflow:
    """Tests for resume workflow after HITL."""

    def test_resume_with_user_input(self, client, mock_authentication):
        """Test resuming with user input."""
        thread_id = "test-thread-resume"

        with patch("app.api.routes.agent.get_graph") as mock_get_graph:
            mock_graph = MagicMock()
            mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={}))
            mock_get_graph.return_value = mock_graph

            with patch("app.api.routes.agent.get_checkpointer") as mock_get_cp:
                mock_get_cp.return_value = MagicMock()

                with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                    mock_monitor.clear_human_request = AsyncMock()
                    mock_monitor.start_run = AsyncMock()

                    with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                        mock_db_session = AsyncMock()
                        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
                        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                        response = client.post("/api/v1/chat/resume", json={
                            "thread_id": thread_id,
                            "user_input": "Yes, proceed with the changes",
                            "command_id": 123
                        })

                        assert response.status_code == 200
                        data = response.json()
                        assert data["status"] == "resuming"
                        assert data["thread_id"] == thread_id


class TestBackgroundTaskWorkflow:
    """Tests for background task execution."""

    def test_stop_running_task(self, client, mock_authentication):
        """Test stopping a running background task."""
        thread_id = "test-thread-stop"

        with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
            mock_monitor.stop_run = AsyncMock()

            response = client.post("/api/v1/chat/stop", json={
                "thread_id": thread_id,
                "message": "stop"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "stopping"
            mock_monitor.stop_run.assert_called_once_with(thread_id)
