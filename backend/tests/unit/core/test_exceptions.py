"""
Unit tests for custom exceptions.
"""

import pytest

from app.core.exceptions import AgentCancelledException, AgentHumanInterruptException


class TestAgentCancelledException:
    """Tests for AgentCancelledException."""

    def test_exception_is_base_exception(self):
        """Test that AgentCancelledException inherits from BaseException."""
        exc = AgentCancelledException("Test message")
        assert isinstance(exc, BaseException)
        # Should NOT be caught by except Exception
        assert not isinstance(exc, Exception)

    def test_exception_message(self):
        """Test exception message."""
        exc = AgentCancelledException("Run cancelled by user")
        assert str(exc) == "Run cancelled by user"

    def test_exception_empty_message(self):
        """Test exception with empty message."""
        exc = AgentCancelledException()
        assert str(exc) == ""


class TestAgentHumanInterruptException:
    """Tests for AgentHumanInterruptException."""

    def test_exception_is_base_exception(self):
        """Test that AgentHumanInterruptException inherits from BaseException."""
        exc = AgentHumanInterruptException("req-123")
        assert isinstance(exc, BaseException)
        # Should NOT be caught by except Exception
        assert not isinstance(exc, Exception)

    def test_exception_with_request_id(self):
        """Test exception with request ID."""
        exc = AgentHumanInterruptException("req-123")
        assert exc.request_id == "req-123"
        assert "Human input required" in str(exc)

    def test_exception_with_custom_message(self):
        """Test exception with custom message."""
        exc = AgentHumanInterruptException("req-456", "Please provide approval")
        assert exc.request_id == "req-456"
        assert str(exc) == "Please provide approval"

    def test_exception_caught_by_base_exception(self):
        """Test that exception is caught by except BaseException."""
        exc = AgentCancelledException("Test")
        caught = False
        try:
            raise exc
        except BaseException as e:
            caught = True
            assert isinstance(e, AgentCancelledException)
        assert caught is True

    def test_exception_not_caught_by_exception(self):
        """Test that exception is NOT caught by except Exception."""
        exc = AgentCancelledException("Test")
        caught_by_exception = False
        caught_by_base = False
        try:
            raise exc
        except Exception:
            caught_by_exception = True
        except BaseException:
            caught_by_base = True
        assert caught_by_exception is False
        assert caught_by_base is True
