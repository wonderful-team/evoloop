"""
Unit tests for multimodal skill synthesizer.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from app.core.learning.frame_compressor import CompressedFrame
from app.core.learning.multimodal_synthesizer import (
    MultimodalSkillSynthesizer,
    RecordingSession,
    VideoInfo,
)


class TestMultimodalSkillSynthesizer:
    """Tests for MultimodalSkillSynthesizer."""

    @pytest.fixture
    def synthesizer(self):
        """Create synthesizer with mocked LLM."""
        with patch('app.core.learning.multimodal_synthesizer.VisionLLMFactory') as mock_factory:
            mock_llm = MagicMock()
            mock_factory.create_vision_llm.return_value = mock_llm
            yield MultimodalSkillSynthesizer()

    @pytest.fixture
    def recording_session(self):
        """Create a test recording session."""
        return RecordingSession(
            video_path="/test/video.mp4",
            session_id="test-session-123",
            task_description="Send message to Zhang San",
            thread_id="thread-456"
        )

    @pytest.fixture
    def mock_video_info(self):
        """Create mock video info."""
        return VideoInfo(
            duration=10.0,
            width=1920,
            height=1080,
            fps=15.0
        )

    @pytest.fixture
    def mock_trace_events(self):
        """Create mock trace events."""
        events = []
        for i in range(3):
            event = MagicMock()
            event.timestamp = 1000.0 + i * 2
            event.action_type = "mouse_click"
            event.mouse_x = 960
            event.mouse_y = 540
            event.target_text = f"Button{i}"
            event.window_title = "WeChat"
            event.app_name = "WeChat"
            event.key_name = None
            events.append(event)
        return events

    @pytest.fixture
    def mock_compressed_frames(self):
        """Create mock compressed frames."""
        frames = []
        for i in range(3):
            frame = CompressedFrame(
                data=b"fake_jpeg_data",
                width=768,
                height=432,
                original_size=(1920, 1080),
                compression_ratio=0.15,
                detail_level="low"
            )
            frame.timestamp = 1000.0 + i * 2
            frame.description = f"Frame {i}"
            frame.norm_events = [{
                'action': 'mouse_click',
                'position': (0.5, 0.5),
                'target_text': f'Button{i}'
            }]
            frames.append(frame)
        return frames

    @pytest.mark.asyncio
    async def test_synthesize_success(
        self,
        synthesizer,
        recording_session,
        mock_video_info,
        mock_trace_events,
        mock_compressed_frames
    ):
        """Test successful synthesis."""
        # Mock LLM response
        llm_response = """
---
name: send_wechat_message
namespace: os/macos/wechat
description: Send a message to a contact in WeChat
trigger_patterns:
  - "send message to {{contact}} in WeChat"
parameters:
  - name: contact
    type: string
    required: true
---

# 🧠 Expert Skill Guide

## 1. Mental Model
This skill sends a message to a WeChat contact.

## 2. Visual Anchors
Look for the search icon.

## 3. Execution Workflow
Click search, type name, send message.
"""
        synthesizer.vision_llm.ainvoke = AsyncMock(return_value=MagicMock(content=llm_response))

        # Mock internal methods
        with patch.object(synthesizer, '_get_video_info', return_value=mock_video_info):
            with patch.object(synthesizer, '_fetch_events', return_value=mock_trace_events):
                with patch.object(synthesizer, '_extract_and_compress_frames', return_value=mock_compressed_frames):
                    with patch('app.core.learning.multimodal_synthesizer.session_scope') as mock_session:
                        mock_db = AsyncMock()
                        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

                        result = await synthesizer.synthesize(recording_session)

        assert result["skill"]["name"] == "send_wechat_message"
        assert result["skill"]["namespace"] == "os/macos/wechat"
        assert result["metadata"]["frames_analyzed"] == 3
        assert result["metadata"]["events_processed"] == 3

    @pytest.mark.asyncio
    async def test_synthesize_no_events(self, synthesizer, recording_session):
        """Test synthesis with no events."""
        with patch.object(synthesizer, '_get_video_info', return_value=VideoInfo(10.0, 1920, 1080, 15.0)):
            with patch.object(synthesizer, '_fetch_events', return_value=[]):
                with pytest.raises(ValueError, match="No events found"):
                    await synthesizer.synthesize(recording_session)

    @pytest.mark.asyncio
    async def test_get_video_info_success(self, synthesizer):
        """Test video info extraction."""
        with patch('subprocess.run') as mock_run:
            # Mock duration command
            mock_run.side_effect = [
                MagicMock(stdout="10.5\n", returncode=0),
                MagicMock(
                    stdout=json.dumps({
                        "streams": [{
                            "width": 1920,
                            "height": 1080,
                            "r_frame_rate": "15/1"
                        }]
                    }),
                    returncode=0
                )
            ]

            info = await synthesizer._get_video_info("/test/video.mp4")

            assert info.duration == 10.5
            assert info.width == 1920
            assert info.height == 1080
            assert info.fps == 15.0

    @pytest.mark.asyncio
    async def test_get_video_info_failure(self, synthesizer):
        """Test video info extraction failure."""
        with patch('subprocess.run', side_effect=Exception("ffmpeg not found")):
            info = await synthesizer._get_video_info("/test/video.mp4")

            # Should return defaults
            assert info.duration == 30.0
            assert info.width == 1920
            assert info.height == 1080

    def test_build_event_context(self, synthesizer, mock_trace_events):
        """Test event context building."""
        context = synthesizer._build_event_context(
            events=mock_trace_events,
            original_resolution=(1920, 1080)
        )

        assert "Total Events: 3" in context
        assert "Screen Resolution: 1920x1080" in context
        assert "mouse_click" in context
        assert "WeChat" in context

        # Check normalized coordinates
        assert "(0.500, 0.500)" in context  # 960/1920, 540/1080

    def test_parse_llm_response_success(self, synthesizer, recording_session):
        """Test parsing valid LLM response."""
        response = """
---
name: test_skill
namespace: test/ns
description: A test skill
trigger_patterns:
  - "do {{thing}}"
parameters:
  - name: thing
    type: string
    required: true
---

# 🧠 Expert Skill Guide

## 1. Mental Model
Test mental model.

## 2. Visual Anchors
Test anchors.
"""
        result = synthesizer._parse_llm_response(response, recording_session)

        assert result["name"] == "test_skill"
        assert result["namespace"] == "test/ns"
        assert result["skill_source"] == "multimodal_record"
        assert result["status"] == "draft"
        assert "source_session_id" in result

    def test_parse_llm_response_no_yaml(self, synthesizer, recording_session):
        """Test parsing response without YAML."""
        response = "Just some text without YAML"
        result = synthesizer._parse_llm_response(response, recording_session)

        assert result["name"] == "unnamed_skill"
        assert result["instructions"] == response

    def test_extract_yaml_from_code_block(self, synthesizer):
        """Test extracting YAML from code block."""
        text = """
Some text
```yaml
name: test
description: test desc
```
More text
"""
        result = synthesizer._extract_yaml(text)
        assert "name: test" in result
        assert "description: test desc" in result

    def test_extract_yaml_from_frontmatter(self, synthesizer):
        """Test extracting YAML from frontmatter."""
        text = """---
name: test_skill
description: Test
---

# Instructions
"""
        result = synthesizer._extract_yaml(text)
        assert "name: test_skill" in result

    def test_extract_instructions(self, synthesizer):
        """Test extracting instructions from response."""
        text = """
---
name: test
---

# 🧠 Expert Skill Guide
This is the guide.

## More content
Details here.
"""
        result = synthesizer._extract_instructions(text)
        assert "# 🧠 Expert Skill Guide" in result
        assert "Details here." in result

    def test_describe_position(self, synthesizer):
        """Test position description."""
        assert synthesizer._describe_position(0.5, 0.5) == "middle-center"
        assert synthesizer._describe_position(0.1, 0.1) == "top-left"
        assert synthesizer._describe_position(0.9, 0.9) == "bottom-right"


class TestRecordingSession:
    """Tests for RecordingSession dataclass."""

    def test_creation(self):
        """Test RecordingSession creation."""
        session = RecordingSession(
            video_path="/path/to/video.mp4",
            session_id="session-123",
            task_description="Test task",
            thread_id="thread-456"
        )

        assert session.video_path == "/path/to/video.mp4"
        assert session.session_id == "session-123"
        assert session.task_description == "Test task"
        assert session.thread_id == "thread-456"

    def test_optional_thread_id(self):
        """Test RecordingSession with optional thread_id."""
        session = RecordingSession(
            video_path="/path/to/video.mp4",
            session_id="session-123",
            task_description="Test task"
        )

        assert session.thread_id is None


class TestVideoInfo:
    """Tests for VideoInfo dataclass."""

    def test_creation(self):
        """Test VideoInfo creation."""
        info = VideoInfo(
            duration=15.5,
            width=1920,
            height=1080,
            fps=30.0
        )

        assert info.duration == 15.5
        assert info.width == 1920
        assert info.height == 1080
        assert info.fps == 30.0
