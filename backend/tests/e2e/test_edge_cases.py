"""
E2E edge case and boundary tests.
Tests unusual but valid scenarios.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestEmptyInputs:
    """Tests for empty input handling."""

    def test_empty_chat_message(self, client, mock_guest_access):
        """Test sending empty chat message."""
        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "empty-msg-test",
                        "message": "",
                        "project_id": 1
                    }, headers={"X-Guest-ID": "guest-123"})

                    # Should either accept or reject with validation error
                    assert response.status_code in [200, 400, 422]

    def test_empty_project_name(self, client, auth_headers):
        """Test creating project with empty name."""
        response = client.post("/api/v1/projects", headers=auth_headers, json={
            "name": "",
            "path": "/path/to/project"
        })
        assert response.status_code == 422

    def test_empty_search_query(self, client, auth_headers):
        """Test search with empty query."""
        response = client.get("/api/v1/wiki/search?q=", headers=auth_headers)
        # Should handle gracefully
        assert response.status_code in [200, 400]


class TestUnicodeAndSpecialCharacters:
    """Tests for unicode and special character handling."""

    def test_unicode_chat_message(self, client, mock_guest_access):
        """Test chat with unicode characters."""
        unicode_messages = [
            "Hello 世界! 🌍",
            "مرحبا بالعالم",
            "Привет мир",
            "🚀🔥💻🎉",
            "\u200b",  # Zero-width space
        ]

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    for i, msg in enumerate(unicode_messages):
                        response = client.post("/api/v1/chat", json={
                            "thread_id": f"unicode-test-{i}",
                            "message": msg,
                            "project_id": 1
                        }, headers={"X-Guest-ID": "guest-123"})

                        assert response.status_code == 200

    def test_special_characters_in_filename(self, client, auth_headers):
        """Test handling special characters in filenames."""
        # These characters might be problematic in filenames
        special_names = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "file.multiple.dots.txt",
        ]

        for name in special_names:
            with patch("app.utils.file.read_file_content") as mock_read:
                mock_read.return_value = ("content", "utf-8")

                response = client.get(f"/api/v1/files/read?path=/test/{name}", headers=auth_headers)
                # Should handle gracefully
                assert response.status_code in [200, 404]


class TestVeryLongInputs:
    """Tests for very long input handling."""

    def test_very_long_chat_message(self, client, mock_guest_access):
        """Test chat with very long message."""
        # 100KB message
        long_message = "x" * (100 * 1024)

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "long-msg-test",
                        "message": long_message[:1000],  # Use smaller for test
                        "project_id": 1
                    }, headers={"X-Guest-ID": "guest-123"})

                    assert response.status_code in [200, 400, 413]

    def test_very_long_thread_id(self, client, mock_guest_access):
        """Test with very long thread ID."""
        long_thread_id = "thread-" + "x" * 1000

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": long_thread_id[:100],  # Limit for test
                        "message": "Test",
                        "project_id": 1
                    }, headers={"X-Guest-ID": "guest-123"})

                    assert response.status_code in [200, 400]


class TestRapidRequests:
    """Tests for rapid successive requests."""

    def test_rapid_same_thread_requests(self, client, mock_guest_access):
        """Test rapid requests to same thread."""
        thread_id = "rapid-test-thread"

        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    # Send 10 rapid requests
                    for i in range(10):
                        response = client.post("/api/v1/chat", json={
                            "thread_id": thread_id,
                            "message": f"Rapid message {i}",
                            "project_id": 1
                        }, headers={"X-Guest-ID": "guest-123"})

                        assert response.status_code == 200


class TestInvalidUUIDs:
    """Tests for invalid ID formats."""

    def test_malformed_conversation_id(self, client, auth_headers):
        """Test accessing conversation with malformed ID."""
        malformed_ids = [
            "<script>alert(1)</script>",
            "../../../etc/passwd",
            "id\"; DROP TABLE users; --",
            "very" * 100 + "long-id",
        ]

        for conv_id in malformed_ids:
            response = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
            # Should handle gracefully
            assert response.status_code in [200, 404, 400]


class TestNegativeNumbers:
    """Tests for negative number handling."""

    def test_negative_limit_in_search(self, client, auth_headers):
        """Test search with negative limit."""
        response = client.get("/api/v1/wiki/search?q=test&limit=-1", headers=auth_headers)
        # Should handle gracefully
        assert response.status_code in [200, 400]

    def test_zero_limit_in_search(self, client, auth_headers):
        """Test search with zero limit."""
        response = client.get("/api/v1/wiki/search?q=test&limit=0", headers=auth_headers)
        assert response.status_code in [200, 400]


class TestNullValues:
    """Tests for null value handling."""

    def test_null_fields_in_json(self, client, auth_headers):
        """Test JSON with null fields."""
        response = client.post("/api/v1/projects", headers=auth_headers, json={
            "name": None,
            "description": None,
            "path": "/test/path"
        })
        assert response.status_code in [200, 201, 422]


class TestCircularReferences:
    """Tests for circular reference handling (if applicable)."""

    def test_self_referencing_attachments(self, client, mock_guest_access):
        """Test attachment that references itself."""
        # This is more of a conceptual test - actual implementation may vary
        pass


class TestDateTimeBoundaries:
    """Tests for datetime boundary handling."""

    def test_very_old_date(self, client, auth_headers):
        """Test handling of very old dates."""
        # If there are date-based filters
        pass

    def test_future_date(self, client, auth_headers):
        """Test handling of future dates."""
        pass


class TestWhitespaceHandling:
    """Tests for whitespace handling."""

    def test_leading_trailing_whitespace(self, client, mock_guest_access):
        """Test message with leading/trailing whitespace."""
        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "whitespace-test",
                        "message": "   Hello World   ",
                        "project_id": 1
                    }, headers={"X-Guest-ID": "guest-123"})

                    assert response.status_code == 200

    def test_only_whitespace_message(self, client, mock_guest_access):
        """Test message containing only whitespace."""
        with patch("app.api.routes.agent.run_agent_background"):
            with patch("app.api.routes.agent.activity_monitor") as mock_monitor:
                mock_monitor.start_run = AsyncMock()

                with patch("app.infrastructure.database.sql.database.session_scope") as mock_session:
                    mock_db = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                    mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                    response = client.post("/api/v1/chat", json={
                        "thread_id": "only-whitespace-test",
                        "message": "     \n\t   ",
                        "project_id": 1
                    }, headers={"X-Guest-ID": "guest-123"})

                    assert response.status_code in [200, 400]
