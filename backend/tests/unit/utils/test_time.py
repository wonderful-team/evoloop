"""
Unit tests for time utilities.
"""

from datetime import datetime, timezone

from app.utils.time import utcnow, now


class TestUtcnow:
    """Tests for utcnow function."""

    def test_returns_datetime(self):
        """Test that utcnow returns a datetime object."""
        result = utcnow()
        assert isinstance(result, datetime)

    def test_has_timezone(self):
        """Test that returned datetime has timezone info."""
        result = utcnow()
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_is_utc(self):
        """Test that returned datetime is in UTC."""
        result = utcnow()
        # UTC offset should be 0
        assert result.utcoffset().total_seconds() == 0


class TestNow:
    """Tests for now function (alias for utcnow)."""

    def test_returns_datetime(self):
        """Test that now returns a datetime object."""
        result = now()
        assert isinstance(result, datetime)

    def test_is_alias_for_utcnow(self):
        """Test that now is equivalent to utcnow."""
        # Both should return datetime with UTC timezone
        utc_result = utcnow()
        now_result = now()

        assert utc_result.tzinfo == now_result.tzinfo
        assert utc_result.utcoffset() == now_result.utcoffset()

    def test_time_is_reasonable(self):
        """Test that returned time is reasonable (not in the past/future)."""
        result = utcnow()
        # Should be after year 2024
        assert result.year >= 2024
        # Should be before year 2100 (sanity check)
        assert result.year < 2100
