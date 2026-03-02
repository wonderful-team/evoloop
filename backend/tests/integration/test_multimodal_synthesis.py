"""
Integration tests for multimodal skill synthesis API.

These tests verify the end-to-end flow of the synthesis API,
including video processing, frame extraction, and LLM calls.

Note: Tests requiring actual LLM calls are marked with @pytest.mark.llm
and should be run with care due to API costs.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Check if we should skip DB-dependent tests
from tests.unit.core.test_learning import skip_if_no_db


@pytest.mark.asyncio
class TestSynthesizeFromRecordingAPI:
    """Tests for /skills/synthesize-from-recording endpoint."""

    @skip_if_no_db
    async def test_synthesize_endpoint_success(self, client):
        """Test successful synthesis via API."""
        # Mock the synthesizer
        with patch(
            'app.api.routes.learning.MultimodalSkillSynthesizer'
        ) as mock_synth_class:

            mock_synth = MagicMock()
            mock_synth.synthesize = AsyncMock(return_value={
                "skill": {
                    "name": "test_skill",
                    "namespace": "test/ns",
                    "description": "Test description",
                    "trigger_patterns": ["test pattern"],
                    "parameters": [],
                    "instructions": "# Guide\nTest",
                    "source_session_id": "test-session",
                    "source_thread_id": None,
                    "skill_source": "multimodal_record",
                    "status": "draft",
                },
                "metadata": {
                    "processing_time_seconds": 5.5,
                    "frames_analyzed": 5,
                    "events_processed": 10,
                    "video_duration": 15.0,
                    "model": "gpt-4o",
                }
            })
            mock_synth_class.return_value = mock_synth

            # Mock file existence check
            with patch('os.path.exists', return_value=True):
                response = client.post(
                    "/api/v1/learning/skills/synthesize-from-recording",
                    json={
                        "video_path": "/test/video.mp4",
                        "session_id": "test-session",
                        "task_description": "Test task",
                    }
                )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["skill_name"].startswith("test_skill")
        assert data["frames_analyzed"] == 5
        assert data["events_processed"] == 10
        assert "skill_yaml" in data

    @skip_if_no_db
    async def test_synthesize_endpoint_video_not_found(self, client):
        """Test synthesis with non-existent video."""
        with patch('os.path.exists', return_value=False):
            response = client.post(
                "/api/v1/learning/skills/synthesize-from-recording",
                json={
                    "video_path": "/nonexistent/video.mp4",
                    "session_id": "test-session",
                    "task_description": "Test task",
                }
            )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    @skip_if_no_db
    async def test_synthesize_endpoint_failure(self, client):
        """Test synthesis failure handling."""
        with patch(
            'app.api.routes.learning.MultimodalSkillSynthesizer'
        ) as mock_synth_class:

            mock_synth = MagicMock()
            mock_synth.synthesize = AsyncMock(
                side_effect=Exception("Synthesis failed")
            )
            mock_synth_class.return_value = mock_synth

            with patch('os.path.exists', return_value=True):
                response = client.post(
                    "/api/v1/learning/skills/synthesize-from-recording",
                    json={
                        "video_path": "/test/video.mp4",
                        "session_id": "test-session",
                        "task_description": "Test task",
                    }
                )

        assert response.status_code == 200  # Returns 200 with error info
        data = response.json()

        assert data["success"] is False
        assert "error" in data
        assert "Synthesis failed" in data["error"]

    @skip_if_no_db
    async def test_preview_endpoint(self, client):
        """Test preview endpoint."""
        with patch(
            'app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer'
        ) as mock_synth_class:

            mock_synth = MagicMock()
            mock_synth._get_video_info = AsyncMock(return_value=MagicMock(
                duration=10.0,
                width=1920,
                height=1080,
                fps=15.0
            ))
            mock_synth._fetch_events = AsyncMock(return_value=[
                MagicMock(timestamp=1000.0, action_type="mouse_click"),
                MagicMock(timestamp=1002.0, action_type="mouse_click"),
            ])
            mock_synth_class.return_value = mock_synth

            with patch(
                'app.core.learning.frame_compressor.KeyframeSelector'
            ) as mock_selector_class:

                mock_selector = MagicMock()
                mock_selector.select_keyframes.return_value = [
                    MagicMock(
                        timestamp=1000.0,
                        context="pre_action",
                        description="Before click",
                        priority=2
                    ),
                    MagicMock(
                        timestamp=1002.5,
                        context="post_action",
                        description="After click",
                        priority=3
                    ),
                ]
                mock_selector_class.return_value = mock_selector

                response = client.get(
                    "/api/v1/learning/skills/synthesize-from-recording/preview",
                    params={
                        "session_id": "test-session",
                        "video_path": "/test/video.mp4"
                    }
                )

        assert response.status_code == 200
        data = response.json()

        assert "video_info" in data
        assert "events" in data
        assert "keyframes" in data
        assert data["video_info"]["duration"] == 10.0


@pytest.mark.asyncio
class TestMultimodalSynthesisIntegration:
    """Integration tests requiring actual components."""

    @pytest.mark.llm
    @skip_if_no_db
    @pytest.mark.skipif(
        not os.getenv("VISION_MODEL"),
        reason="VISION_MODEL not configured"
    )
    async def test_end_to_end_synthesis(self):
        """
        End-to-end test with real components (requires LLM).

        This test requires:
        - Database connection
        - Valid video file
        - LLM API key configured
        """
        from app.core.learning.multimodal_synthesizer import (
            MultimodalSkillSynthesizer,
            RecordingSession,
        )

        # Skip if no test video
        test_video = os.getenv("TEST_VIDEO_PATH")
        if not test_video or not Path(test_video).exists():
            pytest.skip("TEST_VIDEO_PATH not set or file not found")

        synthesizer = MultimodalSkillSynthesizer()

        recording = RecordingSession(
            video_path=test_video,
            session_id="integration-test",
            task_description="Test task for integration",
        )

        # This will make actual LLM call - use with caution
        result = await synthesizer.synthesize(recording)

        assert "skill" in result
        assert "metadata" in result
        assert result["skill"]["name"]
        assert result["skill"]["instructions"]


@pytest.fixture
def client():
    """Create test client."""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)
