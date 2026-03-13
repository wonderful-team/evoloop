"""
Tests for SmartSynthesizer - covering bugs found in code review.

Bugs to test:
1. Missing asyncio import
2. _save_intermediate_result parameter type handling
"""

import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime


class TestSmartSynthesizerImports:
    """Test that SmartSynthesizer has all required imports."""

    def test_asyncio_imported(self):
        """Bug #1: Verify asyncio is imported for run_in_executor usage."""
        # This test will fail if asyncio is not imported
        try:
            from app.core.learning import smart_synthesizer

            # Check that asyncio is accessible in the module
            assert hasattr(smart_synthesizer, 'asyncio') or 'asyncio' in dir(smart_synthesizer), \
                "asyncio should be imported in smart_synthesizer module"

            # Verify asyncio.get_event_loop can be called
            import asyncio
            loop = asyncio.get_event_loop()
            assert loop is not None
        except ImportError as e:
            pytest.fail(f"Failed to import smart_synthesizer: {e}")
        except AttributeError as e:
            pytest.fail(f"asyncio not properly imported: {e}")


class TestSmartSynthesizerSaveIntermediateResult:
    """Test _save_intermediate_result method - Bug #2."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_job = MagicMock()
        mock_result.scalar_one.return_value = mock_job
        mock_session.execute.return_value = mock_result
        return mock_session, mock_job

    @pytest.fixture
    def synthesizer(self):
        """Create a SmartSynthesizer instance with mocked dependencies."""
        from app.core.learning.smart_synthesizer import SmartSynthesizer

        # Mock annotations
        mock_annotation = MagicMock()
        mock_annotation.video_timestamp_ms = 1000
        mock_annotation.annotation_type = "extract_region"
        mock_annotation.region_x = 10.0
        mock_annotation.region_y = 20.0
        mock_annotation.region_width = 100.0
        mock_annotation.region_height = 50.0
        mock_annotation.user_note = "Test annotation"

        synthesizer = SmartSynthesizer(
            job_id=1,
            session_id="test_session",
            thread_id="test_thread",
            task_goal="Test task",
            annotations=[mock_annotation]
        )
        return synthesizer

    @pytest.mark.asyncio
    async def test_save_intermediate_result_keyframes_type(self, synthesizer, mock_db_session):
        """Bug #2: Test that keyframes data is properly handled as list."""
        mock_session, mock_job = mock_db_session

        # Test data - keyframes should be a list
        keyframes_data = [
            {"timestamp_ms": 1000, "frame_path": "/path/to/frame1.jpg"},
            {"timestamp_ms": 2000, "frame_path": "/path/to/frame2.jpg"}
        ]

        with patch('app.core.learning.smart_synthesizer.session_scope') as mock_scope:
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            # This should not raise any type errors
            await synthesizer._save_intermediate_result("keyframes", keyframes_data)

            # Verify the job's keyframes was set to the list
            assert mock_job.keyframes == keyframes_data

    @pytest.mark.asyncio
    async def test_save_intermediate_result_frame_analyses_type(self, synthesizer, mock_db_session):
        """Bug #2: Test that frame_analyses data is properly handled as list."""
        mock_session, mock_job = mock_db_session

        # Test data - frame_analyses should be a list of analysis results
        analyses_data = [
            {
                "timestamp_ms": 1000,
                "scene_description": "Test scene",
                "ui_elements": ["button", "input"],
                "intent": "Test intent"
            }
        ]

        with patch('app.core.learning.smart_synthesizer.session_scope') as mock_scope:
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            await synthesizer._save_intermediate_result("frame_analyses", analyses_data)
            assert mock_job.frame_analyses == analyses_data

    @pytest.mark.asyncio
    async def test_save_intermediate_result_phase_analysis_type(self, synthesizer, mock_db_session):
        """Bug #2: Test that phase_analysis data is properly handled as dict."""
        mock_session, mock_job = mock_db_session

        # Test data - phase_analysis should be a dict
        phase_data = {
            "phases": [
                {"name": "Phase 1", "start_time_ms": 0, "end_time_ms": 5000}
            ],
            "overall_pattern": "Test pattern"
        }

        with patch('app.core.learning.smart_synthesizer.session_scope') as mock_scope:
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            await synthesizer._save_intermediate_result("phase_analysis", phase_data)
            assert mock_job.phase_analysis == phase_data

    @pytest.mark.asyncio
    async def test_save_intermediate_result_invalid_key(self, synthesizer, mock_db_session):
        """Test that invalid keys are handled gracefully."""
        mock_session, mock_job = mock_db_session

        with patch('app.core.learning.smart_synthesizer.session_scope') as mock_scope:
            mock_scope.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_scope.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise for unknown keys (silently ignored)
            await synthesizer._save_intermediate_result("unknown_key", {"data": "test"})

            # The job was fetched, but no known attribute was set
            # MagicMock will have any attribute, but our code didn't explicitly set it
            # So we just verify no error was raised


class TestSmartSynthesizerExtractKeyframes:
    """Test _extract_keyframes method - requires asyncio."""

    @pytest.fixture
    def synthesizer_with_video(self):
        """Create a synthesizer with mocked video path."""
        from app.core.learning.smart_synthesizer import SmartSynthesizer

        synthesizer = SmartSynthesizer(
            job_id=1,
            session_id="test_session",
            thread_id="test_thread",
            task_goal="Test task",
            annotations=[]
        )
        synthesizer.video_path = "/fake/path/video.mp4"
        return synthesizer

    @pytest.mark.asyncio
    async def test_extract_keyframes_uses_asyncio(self, synthesizer_with_video):
        """Bug #1: Verify _extract_keyframes uses asyncio properly."""
        synthesizer = synthesizer_with_video

        # Mock os.path.exists to return True
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getmtime', return_value=datetime.now().timestamp()):
                with patch('os.listdir', return_value=['video.mp4']):
                    with patch('os.path.join', return_value='/fake/path/video.mp4'):
                        # Mock subprocess.run for ffprobe
                        with patch('subprocess.run') as mock_run:
                            mock_run.return_value.stdout = "60.0\n"
                            mock_run.return_value.returncode = 0

                            # Mock FrameExtractor
                            with patch('app.core.learning.smart_synthesizer.FrameExtractor') as MockExtractor:
                                mock_extractor = MagicMock()
                                mock_extractor.extract_frames.return_value = ['/frame1.jpg', '/frame2.jpg']
                                MockExtractor.return_value = mock_extractor

                                # Mock _save_intermediate_result
                                with patch.object(synthesizer, '_save_intermediate_result', new_callable=AsyncMock):
                                    # This should work if asyncio is properly imported
                                    try:
                                        keyframes = await synthesizer._extract_keyframes()
                                        assert isinstance(keyframes, list)
                                    except NameError as e:
                                        if "asyncio" in str(e):
                                            pytest.fail(f"asyncio not imported: {e}")
                                        raise


class TestSmartSynthesizerVisionAnalysis:
    """Test vision analysis methods."""

    @pytest.fixture
    def synthesizer(self):
        from app.core.learning.smart_synthesizer import SmartSynthesizer

        mock_annotation = MagicMock()
        mock_annotation.video_timestamp_ms = 1000
        mock_annotation.annotation_type = "extract_region"
        mock_annotation.region_x = 10.0
        mock_annotation.region_y = 20.0
        mock_annotation.region_width = 100.0
        mock_annotation.region_height = 50.0
        mock_annotation.user_note = "Test region"

        return SmartSynthesizer(
            job_id=1,
            session_id="test_session",
            thread_id="test_thread",
            task_goal="Extract data from website",
            annotations=[mock_annotation]
        )

    def test_build_vision_prompt_with_annotations(self, synthesizer):
        """Test that vision prompt is built correctly with annotations."""
        frame = {"timestamp_ms": 1000, "frame_path": "/test.jpg"}
        annotations = synthesizer.annotations

        prompt = synthesizer._build_vision_prompt(frame, annotations)

        # Verify prompt contains key elements - uses task_goal not "Test task"
        assert "Extract data from website" in prompt  # Actual task_goal
        assert "Test region" in prompt  # user_note from annotation
        assert "JSON format" in prompt
        assert "regions of interest" in prompt
        assert "Bounding box" in prompt

    def test_build_vision_prompt_empty_annotations(self, synthesizer):
        """Test prompt generation with no annotations."""
        frame = {"timestamp_ms": 1000, "frame_path": "/test.jpg"}

        prompt = synthesizer._build_vision_prompt(frame, [])

        # Uses actual task_goal
        assert "Extract data from website" in prompt
        assert "JSON format" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
