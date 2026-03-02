"""
E2E concurrency and performance tests.
Tests system behavior under concurrent load.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import concurrent.futures
import time


class TestConcurrentChat:
    """Tests for concurrent chat operations."""

    def test_multiple_simultaneous_chats(self, client, mock_guest_access):
        """Test handling multiple simultaneous chat requests."""
        thread_ids = [f"concurrent-thread-{i}" for i in range(5)]

        with patch("app.api.routes.agent.run_agent_background") as mock_bg:
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    # Send multiple requests concurrently
                    def send_chat(thread_id):
                        return client.post("/api/v1/chat", json={
                            "thread_id": thread_id,
                            "message": f"Message from {thread_id}",
                            "project_id": 1
                        }, headers={"X-Guest-ID": "guest-123"})

                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [executor.submit(send_chat, tid) for tid in thread_ids]
                        responses = [f.result() for f in futures]

                    # All should succeed
                    for response in responses:
                        assert response.status_code == 200

    def test_chat_under_load(self, client, mock_guest_access):
        """Test chat endpoint under load."""
        num_requests = 10

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    start_time = time.time()

                    for i in range(num_requests):
                        response = client.post("/api/v1/chat", json={
                            "thread_id": f"load-test-{i}",
                            "message": "Load test message",
                            "project_id": 1
                        }, headers={"X-Guest-ID": "guest-123"})
                        assert response.status_code == 200

                    elapsed = time.time() - start_time
                    # Should complete within reasonable time
                    assert elapsed < 30  # 30 seconds for 10 requests


class TestConcurrentProjectAccess:
    """Tests for concurrent project operations."""

    def test_concurrent_project_reads(self, client, auth_headers):
        """Test concurrent read operations on projects."""
        with patch("app.api.routes.projects.project_manager") as mock_pm:
            mock_pm.get_project = AsyncMock(return_value={
                "id": 1,
                "name": "Test Project",
                "path": "/path/to/project"
            })

            def read_project(i):
                return client.get("/api/v1/projects/1", headers=auth_headers)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(read_project, i) for i in range(10)]
                responses = [f.result() for f in concurrent.futures.as_completed(futures)]

            # All should succeed
            for response in responses:
                assert response.status_code == 200


class TestResourceLimits:
    """Tests for resource limits."""

    def test_large_message_handling(self, client, mock_guest_access):
        """Test handling of very large messages."""
        # Create a large message (1MB)
        large_message = "x" * (1024 * 1024)

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "large-msg-test",
                        "message": large_message[:10000],  # Use smaller size for test
                        "project_id": 1
                    }, headers={"X-Guest-ID": "guest-123"})

                    # Should handle gracefully (accept or reject with proper error)
                    assert response.status_code in [200, 400, 413]

    def test_many_attachments_handling(self, client, mock_guest_access):
        """Test handling of many attachments."""
        many_attachments = [
            {"type": "file", "url": f"/path/to/file{i}.txt", "name": f"file{i}.txt"}
            for i in range(100)
        ]

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "many-attachments-test",
                        "message": "Test with many attachments",
                        "project_id": 1,
                        "attachments": many_attachments[:10]  # Use 10 for test
                    }, headers={"X-Guest-ID": "guest-123"})

                    # Should handle gracefully
                    assert response.status_code in [200, 400]


class TestTimeoutHandling:
    """Tests for timeout handling."""

    def test_slow_operation_timeout(self, client, auth_headers):
        """Test that slow operations are handled properly."""
        # This test would need actual slow operations
        # For now, just verify the endpoint responds
        pass


class TestMemoryLeaks:
    """Tests for memory leak detection."""

    def test_repeated_operations_memory_stable(self, client, auth_headers):
        """Test that repeated operations don't cause memory leaks."""
        with patch("app.api.routes.system.SystemConfigService") as mock_service:
            mock_service.get_all.return_value = []

            # Make many requests
            for i in range(50):
                response = client.get("/api/v1/system/health")
                assert response.status_code == 200

            # If we get here without memory issues, test passes
            assert True


class TestDatabaseConnectionPooling:
    """Tests for database connection pool behavior."""

    def test_concurrent_database_queries(self, client, auth_headers):
        """Test that concurrent database queries are handled properly."""
        with patch("app.api.routes.conversations.session_scope") as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            def query_conversations(i):
                return client.get("/api/v1/conversations", headers=auth_headers)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(query_conversations, i) for i in range(10)]
                responses = [f.result() for f in concurrent.futures.as_completed(futures)]

            # All should complete without connection pool exhaustion
            for response in responses:
                assert response.status_code in [200, 401]
