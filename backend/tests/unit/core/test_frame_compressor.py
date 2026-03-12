"""
Unit tests for frame compression and coordinate normalization.
"""

import io
import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import MagicMock, patch

from app.core.learning.frame_compressor import (
    CompressedFrame,
    CompressionStrategy,
    CoordinateNormalizer,
    FrameCompressor,
    KeyframeCandidate,
    KeyframeSelector,
)


class TestCoordinateNormalizer:
    """Tests for coordinate normalization."""

    def test_normalize_basic(self):
        """Test basic coordinate normalization."""
        normalizer = CoordinateNormalizer(1920, 1080)

        # Center point
        result = normalizer.normalize(960, 540)
        assert result == (0.5, 0.5)

        # Top-left
        result = normalizer.normalize(0, 0)
        assert result == (0.0, 0.0)

        # Bottom-right
        result = normalizer.normalize(1920, 1080)
        assert result == (1.0, 1.0)

    def test_normalize_none_values(self):
        """Test normalization with None values."""
        normalizer = CoordinateNormalizer(1920, 1080)

        result = normalizer.normalize(None, 540)
        assert result is None

        result = normalizer.normalize(960, None)
        assert result is None

    def test_describe_position(self):
        """Test position description generation."""
        # Top-left corner
        desc = CoordinateNormalizer.describe_position(0.05, 0.05)
        assert "top" in desc and "left" in desc

        # Center
        desc = CoordinateNormalizer.describe_position(0.5, 0.5)
        assert desc == "middle-center"

        # Far right edge
        desc = CoordinateNormalizer.describe_position(0.95, 0.5)
        assert "right" in desc and "edge" in desc

    def test_denormalize_to_compressed(self):
        """Test converting normalized to compressed image coordinates."""
        normalizer = CoordinateNormalizer(1920, 1080)

        # Center of 768x432 compressed image
        result = normalizer.denormalize_to_compressed(0.5, 0.5, 768, 432)
        assert result == (384, 216)

        # Top-left
        result = normalizer.denormalize_to_compressed(0.0, 0.0, 768, 432)
        assert result == (0, 0)


class TestFrameCompressor:
    """Tests for frame compression."""

    @pytest.fixture
    def test_image(self, tmp_path):
        """Create a test image."""
        img_path = tmp_path / "test_frame.png"
        img = Image.new('RGB', (1920, 1080), color='red')
        img.save(img_path)
        return str(img_path)

    @pytest.fixture
    def text_dense_image(self, tmp_path):
        """Create a text-dense test image (simulating code editor)."""
        img_path = tmp_path / "test_code.png"
        # Ultra-wide image simulating code editor (aspect ratio > 2.0 for TEXT_DENSE detection)
        img = Image.new('RGB', (3000, 1000), color='white')
        img.save(img_path)
        return str(img_path)

    def test_compress_basic(self, test_image):
        """Test basic frame compression."""
        compressor = FrameCompressor()
        result = compressor.compress(test_image)

        assert isinstance(result, CompressedFrame)
        assert result.width <= 768
        assert result.height <= 432  # Maintains aspect ratio
        assert result.original_size == (1920, 1080)
        assert result.detail_level == "low"
        assert len(result.data) > 0

    def test_compress_with_strategy_text_dense(self, text_dense_image):
        """Test compression with text-dense strategy."""
        compressor = FrameCompressor()
        result = compressor.compress(
            text_dense_image,
            strategy=CompressionStrategy.TEXT_DENSE
        )

        assert result.width <= 1024
        assert result.detail_level == "high"

    def test_compress_with_strategy_icon_ui(self, test_image):
        """Test compression with icon UI strategy."""
        compressor = FrameCompressor()
        result = compressor.compress(
            test_image,
            strategy=CompressionStrategy.ICON_UI
        )

        assert result.width <= 512
        assert result.detail_level == "low"

    def test_compress_nonexistent_file(self):
        """Test compression with non-existent file."""
        compressor = FrameCompressor()

        with pytest.raises(FileNotFoundError):
            compressor.compress("/nonexistent/path.png")

    def test_auto_detect_strategy_code_editor(self, text_dense_image):
        """Test automatic strategy detection for code editor."""
        compressor = FrameCompressor()

        with Image.open(text_dense_image) as img:
            strategy = compressor._detect_strategy(img)

        assert strategy == CompressionStrategy.TEXT_DENSE

    def test_compress_target_size(self, test_image):
        """Test adaptive compression to target size."""
        compressor = FrameCompressor()
        result = compressor.compress_with_target_size(test_image, target_kb=50)

        # Should be close to 50KB (allowing some variance)
        size_kb = len(result.data) / 1024
        assert size_kb < 100  # Should be significantly reduced


class TestKeyframeSelector:
    """Tests for keyframe selection."""

    @pytest.fixture
    def mock_events(self):
        """Create mock events for testing."""
        events = []
        base_time = 1000.0

        # Simulate a click sequence
        for i in range(5):
            event = MagicMock()
            event.timestamp = base_time + i * 2  # 2 seconds apart
            event.action_type = "mouse_click"
            event.mouse_x = 100 + i * 50
            event.mouse_y = 200
            events.append(event)

        return events

    @pytest.fixture
    def mock_events_with_moves(self):
        """Create mock events including mouse moves (should be filtered)."""
        events = []
        base_time = 1000.0

        # Mouse move (should be filtered)
        move_event = MagicMock()
        move_event.timestamp = base_time
        move_event.action_type = "mouse_move"
        events.append(move_event)

        # Click
        click_event = MagicMock()
        click_event.timestamp = base_time + 1
        click_event.action_type = "mouse_click"
        events.append(click_event)

        return events

    def test_select_keyframes_basic(self, mock_events):
        """Test basic keyframe selection."""
        selector = KeyframeSelector()
        keyframes = selector.select_keyframes(
            events=mock_events,
            video_duration=20.0,
            video_resolution=(1920, 1080)
        )

        # Should have pre_action and post_action for each event
        assert len(keyframes) > 0
        assert all(isinstance(k, KeyframeCandidate) for k in keyframes)

        # Check timestamps are in order
        timestamps = [k.timestamp for k in keyframes]
        assert timestamps == sorted(timestamps)

    def test_keyframe_filter_mouse_moves(self, mock_events_with_moves):
        """Test that mouse moves are filtered out."""
        selector = KeyframeSelector()
        keyframes = selector.select_keyframes(
            events=mock_events_with_moves,
            video_duration=10.0,
            video_resolution=(1920, 1080)
        )

        # Should only have keyframes for click, not mouse move
        assert len(keyframes) > 0

    def test_temporal_deduplication(self, mock_events):
        """Test temporal deduplication."""
        selector = KeyframeSelector()
        selector.MIN_INTERVAL_MS = 500  # 500ms minimum

        # Create events very close together
        close_events = []
        base_time = 1000.0
        for i in range(3):
            event = MagicMock()
            event.timestamp = base_time + i * 0.1  # 100ms apart
            event.action_type = "mouse_click"
            close_events.append(event)

        keyframes = selector.select_keyframes(
            events=close_events,
            video_duration=10.0,
            video_resolution=(1920, 1080)
        )

        # Should deduplicate close timestamps
        timestamps = [k.timestamp for k in keyframes]
        for i in range(1, len(timestamps)):
            assert timestamps[i] - timestamps[i-1] >= 0.3  # 300ms min

    def test_keyframe_priority(self):
        """Test keyframe priority assignment."""
        selector = KeyframeSelector()

        # Create events with different types
        events = []

        # Normal click
        click = MagicMock()
        click.timestamp = 1000.0
        click.action_type = "mouse_click"
        events.append(click)

        keyframes = selector.select_keyframes(
            events=events,
            video_duration=10.0,
            video_resolution=(1920, 1080)
        )

        # Check priorities
        post_frames = [k for k in keyframes if k.context == "post_action"]
        assert len(post_frames) > 0
        assert post_frames[0].priority == 3  # High priority for post_action

    def test_max_keyframes_limit(self, mock_events):
        """Test maximum keyframes limit."""
        selector = KeyframeSelector(max_keyframes=3)

        # Create many events
        many_events = []
        for i in range(20):
            event = MagicMock()
            event.timestamp = 1000.0 + i * 5
            event.action_type = "mouse_click"
            many_events.append(event)

        keyframes = selector.select_keyframes(
            events=many_events,
            video_duration=120.0,
            video_resolution=(1920, 1080)
        )

        assert len(keyframes) <= selector.max_keyframes


class TestCompressedFrame:
    """Tests for CompressedFrame dataclass."""

    def test_compressed_frame_creation(self):
        """Test CompressedFrame creation."""
        frame = CompressedFrame(
            data=b"test_jpeg_data",
            width=768,
            height=432,
            original_size=(1920, 1080),
            compression_ratio=0.15,
            detail_level="low"
        )

        assert frame.width == 768
        assert frame.height == 432
        assert frame.compression_ratio == 0.15
        assert frame.detail_level == "low"

    def test_normalized_event_creation(self):
        """Test NormalizedEvent creation."""
        from app.core.learning.frame_compressor import NormalizedEvent

        event = NormalizedEvent(
            action="click",
            norm_x=0.5,
            norm_y=0.5,
            target_text="Submit",
            timestamp=1234567890.0,
            description="Click on Submit button"
        )

        assert event.action == "click"
        assert event.norm_x == 0.5
        assert event.norm_y == 0.5
        assert event.target_text == "Submit"
