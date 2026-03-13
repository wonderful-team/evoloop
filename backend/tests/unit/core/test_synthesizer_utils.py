"""
Tests for synthesizer_utils module, focusing on timestamp normalization.
"""

import pytest
from app.core.learning.synthesizer_utils import (
    normalize_timestamp_to_seconds,
    describe_normalized_position,
)


class TestNormalizeTimestampToSeconds:
    """Tests for timestamp normalization with video synchronization."""

    def test_relative_milliseconds(self):
        """Relative milliseconds should be converted to seconds."""
        # All sources (Android/DOM/Global) now use relative milliseconds from video start
        timestamp = 5000  # 5 seconds in milliseconds

        result = normalize_timestamp_to_seconds(timestamp)

        assert result == 5.0  # 5000ms / 1000 = 5s

    def test_relative_milliseconds_dom(self):
        """[Desktop DOM] Relative milliseconds should be converted to seconds."""
        timestamp = 3000  # 3 seconds in milliseconds

        result = normalize_timestamp_to_seconds(timestamp)

        assert result == 3.0  # 3000ms / 1000 = 3s

    def test_relative_milliseconds_global(self):
        """[Desktop Global] Relative milliseconds should be converted to seconds."""
        timestamp = 8000  # 8 seconds in milliseconds

        result = normalize_timestamp_to_seconds(timestamp)

        assert result == 8.0  # 8000ms / 1000 = 8s

    def test_small_relative_values(self):
        """Small values should be treated as relative milliseconds."""
        timestamp = 1500  # 1.5 seconds

        result = normalize_timestamp_to_seconds(timestamp)

        assert result == 1.5  # 1500 / 1000 = 1.5s

    def test_none_timestamp(self):
        """None timestamp should return 0."""
        result = normalize_timestamp_to_seconds(None)
        assert result == 0.0

    def test_zero_timestamp(self):
        """Zero timestamp should return 0."""
        result = normalize_timestamp_to_seconds(0)
        assert result == 0.0


class TestDescribeNormalizedPosition:
    """Tests for position description function."""

    def test_center_position(self):
        """Center position should be described as 'middle-center'."""
        result = describe_normalized_position(0.5, 0.5)
        assert result == "middle-center"

    def test_top_left(self):
        """Top-left corner should contain 'top' and 'left'."""
        result = describe_normalized_position(0.1, 0.1)
        assert "top" in result
        assert "left" in result

    def test_bottom_right(self):
        """Bottom-right corner should contain 'bottom' and 'right'."""
        result = describe_normalized_position(0.9, 0.9)
        assert "bottom" in result
        assert "right" in result


class TestTimestampSynchronizationScenario:
    """
    Integration tests for timestamp synchronization scenarios.

    These tests verify that events from different sources are correctly
    normalized for keyframe extraction.
    """

    def test_android_event_synchronization(self):
        """
        [Android] Events should align with video after offset adjustment.

        Scenario:
        - Video starts at T+0s
        - Event recording starts at T+1s (1000ms delay)
        - User clicks at T+5s (video time)
        - Event timestamp: 4000ms (relative to event start)
        - After adjustment: 5000ms (relative to video start)
        """
        # Simulating the offset adjustment that happens in android_event_recorder
        event_timestamp_ms = 4000  # 4s after event recording started
        time_offset_ms = 1000  # Video started 1s before events
        adjusted_timestamp = event_timestamp_ms + time_offset_ms  # 5000ms

        result = normalize_timestamp_to_seconds(adjusted_timestamp)

        # Should be 5 seconds (matching video time)
        assert result == 5.0

    def test_desktop_event_synchronization_after_fix(self):
        """
        [Desktop] Events should align with video after frontend fix.

        Scenario (AFTER fix):
        - recordingStartTime set at T+0s
        - Video starts at T+0.1s (100ms delay)
        - User clicks at T+5s
        - Event timestamp: 5000ms (relative to recordingStartTime)
        - Result: aligns with video at ~5.1s (close enough)
        """
        # After fix: timestamp is relative to recording start
        relative_timestamp_ms = 5000  # 5s after recordingStartTime

        result = normalize_timestamp_to_seconds(relative_timestamp_ms)

        # Should be 5 seconds
        assert result == 5.0

    def test_keyframe_extraction_timing(self):
        """
        Verify that normalized timestamps work for keyframe extraction.

        Keyframe extraction expects timestamps in seconds relative to video start.
        """
        from app.core.learning.frame_compressor import KeyframeSelector

        # Create mock events with normalized timestamps (in seconds)
        class MockEvent:
            def __init__(self, timestamp, action_type):
                self.timestamp = timestamp
                self.action_type = action_type

        events = [
            MockEvent(2.0, "click"),      # 2 seconds
            MockEvent(5.0, "click"),      # 5 seconds
            MockEvent(10.0, "input"),     # 10 seconds
        ]

        selector = KeyframeSelector()
        keyframes = selector.select_keyframes(
            events=events,
            video_duration=15.0,
            video_resolution=(1920, 1080)
        )

        # Should generate keyframes
        assert len(keyframes) > 0

        # All keyframe timestamps should be within video duration
        for kf in keyframes:
            assert 0 <= kf.timestamp <= 15.0

        # Keyframes should be sorted by time
        timestamps = [kf.timestamp for kf in keyframes]
        assert timestamps == sorted(timestamps)
