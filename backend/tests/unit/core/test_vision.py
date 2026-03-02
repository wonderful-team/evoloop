"""
Unit tests for Vision Engine - Visual Perception System.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from app.core.vision.types import VisionTask, VisionResult, UIElement, ElementType
from app.core.vision.engine import VisionEngine


class TestVisionTypes:
    """Tests for Vision type definitions."""

    def test_element_type_enum(self):
        """Test ElementType enum values."""
        assert ElementType.BUTTON.value == "button"
        assert ElementType.INPUT.value == "input"
        assert ElementType.TEXT.value == "text"
        assert ElementType.UNKNOWN.value == "unknown"

    def test_vision_task_enum(self):
        """Test VisionTask enum values."""
        assert VisionTask.OCR.value == "ocr"
        assert VisionTask.DETECT.value == "detect"
        assert VisionTask.CAPTION.value == "caption"
        assert VisionTask.ANALYZE.value == "analyze"
        assert VisionTask.COMPARE.value == "compare"

    def test_ui_element_creation(self):
        """Test creating a UIElement."""
        element = UIElement(
            id=1,
            text="Submit Button",
            x=100,
            y=200,
            width=80,
            height=30,
            element_type=ElementType.BUTTON,
            clickable=True,
            confidence=0.95,
            source="ocr"
        )

        assert element.id == 1
        assert element.text == "Submit Button"
        assert element.x == 100
        assert element.y == 200
        assert element.width == 80
        assert element.height == 30
        assert element.element_type == ElementType.BUTTON
        assert element.clickable is True
        assert element.confidence == 0.95

    def test_ui_element_bounds(self):
        """Test UIElement bounds calculation."""
        element = UIElement(
            id=1,
            text="Test",
            x=100,
            y=100,
            width=40,
            height=20
        )

        bounds = element.bounds
        # bounds should be (x1, y1, x2, y2)
        assert bounds == (80, 90, 120, 110)

    def test_ui_element_to_prompt_line(self):
        """Test UIElement prompt formatting."""
        element = UIElement(
            id=1,
            text="Click Me",
            x=100,
            y=200,
            element_type=ElementType.BUTTON
        )

        line = element.to_prompt_line()
        assert "[1]" in line
        assert "Click Me" in line
        assert "(100, 200)" in line
        assert "button" in line

    def test_ui_element_to_prompt_line_short_text(self):
        """Test UIElement prompt formatting with short text (not truncated)."""
        element = UIElement(
            id=1,
            text="Short",
            x=100,
            y=200
        )

        line = element.to_prompt_line()
        assert "..." not in line
        assert "Short" in line

    def test_ui_element_to_dict(self):
        """Test UIElement serialization."""
        element = UIElement(
            id=1,
            text="Test",
            x=100,
            y=200,
            width=50,
            height=30,
            element_type=ElementType.INPUT,
            metadata={"field": "username"}
        )

        data = element.to_dict()

        assert data["id"] == 1
        assert data["text"] == "Test"
        assert data["element_type"] == "input"
        assert data["metadata"] == {"field": "username"}

    def test_vision_result_creation(self):
        """Test creating a VisionResult."""
        elements = [
            UIElement(id=1, text="Button", x=100, y=100),
            UIElement(id=2, text="Input", x=200, y=100)
        ]

        result = VisionResult(
            task=VisionTask.DETECT,
            success=True,
            elements=elements,
            summary="Found 2 elements",
            latency_ms=150.5
        )

        assert result.task == VisionTask.DETECT
        assert result.success is True
        assert len(result.elements) == 2
        assert result.summary == "Found 2 elements"
        assert result.latency_ms == 150.5


class TestVisionEngine:
    """Tests for VisionEngine."""

    @pytest.fixture
    def engine(self):
        """Create VisionEngine instance."""
        return VisionEngine()

    @pytest.mark.asyncio
    async def test_process_analyze_task(self, engine):
        """Test processing ANALYZE task."""
        with patch.object(engine.router, 'get_provider', new_callable=AsyncMock) as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "test_provider"
            mock_provider.process = AsyncMock(return_value=VisionResult(
                task=VisionTask.ANALYZE,
                success=True,
                summary="Image analyzed"
            ))
            mock_get_provider.return_value = mock_provider

            with patch('app.core.vision.engine.system_bus') as mock_bus:
                mock_bus.publish = AsyncMock()

                result = await engine.process(
                    task=VisionTask.ANALYZE,
                    image_source="/path/to/image.png",
                    prompt="Describe this image"
                )

                assert result.success is True
                assert result.summary == "Image analyzed"

    @pytest.mark.asyncio
    async def test_process_detect_task(self, engine):
        """Test processing DETECT task (uses pipeline)."""
        mock_elements = [
            UIElement(id=1, text="Button", x=100, y=100),
            UIElement(id=2, text="Link", x=200, y=200)
        ]

        # Patch at the source module where pipeline_manager is defined
        with patch('app.core.vision.pipeline.manager.pipeline_manager') as mock_pipeline:
            mock_pipeline.perceive = AsyncMock(return_value=(mock_elements, "/compressed.png"))

            with patch('app.core.vision.engine.system_bus') as mock_bus:
                mock_bus.publish = AsyncMock()

                with patch('app.core.vision.engine.macos_driver') as mock_driver:
                    mock_driver.get_current_app.return_value = {"bundle_id": "com.test.app"}

                    with patch('app.core.vision.engine.event_bus') as mock_event_bus:
                        mock_event_bus.publish = AsyncMock()

                        result = await engine.process(
                            task=VisionTask.DETECT,
                            image_source="/screenshot.png"
                        )

                        assert result.success is True
                        assert len(result.elements) == 2
                        assert "Detected 2 items" in result.summary

    @pytest.mark.asyncio
    async def test_process_no_provider_found(self, engine):
        """Test processing when no provider is available."""
        with patch.object(engine.router, 'get_provider', new_callable=AsyncMock) as mock_get_provider:
            mock_get_provider.return_value = None

            with patch('app.core.vision.engine.system_bus') as mock_bus:
                mock_bus.publish = AsyncMock()

                result = await engine.process(
                    task=VisionTask.OCR,
                    image_source="/image.png"
                )

                assert result.success is False
                assert "No available provider" in result.metadata["error"]

    @pytest.mark.asyncio
    async def test_process_provider_error(self, engine):
        """Test processing when provider raises error."""
        with patch.object(engine.router, 'get_provider', new_callable=AsyncMock) as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.name = "test_provider"
            mock_provider.process = AsyncMock(side_effect=Exception("Provider failed"))
            mock_get_provider.return_value = mock_provider

            with patch('app.core.vision.engine.system_bus') as mock_bus:
                mock_bus.publish = AsyncMock()

                result = await engine.process(
                    task=VisionTask.ANALYZE,
                    image_source="/image.png"
                )

                assert result.success is False
                assert "Provider failed" in result.metadata["error"]


class TestVisionTools:
    """Tests for Vision tools integration."""

    @pytest.mark.asyncio
    async def test_analyze_image_tool(self):
        """Test analyze_image tool function."""
        from app.domain.tools.vision import analyze_image

        # evoloop_tool returns a StructuredTool, we need to call the underlying function
        # or use ainvoke
        with patch('app.domain.tools.vision.vision_engine') as mock_engine:
            mock_engine.process = AsyncMock(return_value=MagicMock(
                success=True,
                summary="This is a screenshot of a web browser"
            ))

            # Call the underlying coroutine function through the tool
            result = await analyze_image.ainvoke({
                "image_source": "/screenshot.png",
                "question": "What is this?",
                "include_ax_tree": False
            })

            assert "web browser" in result

    @pytest.mark.asyncio
    async def test_analyze_image_tool_with_ax_tree(self):
        """Test analyze_image tool with AX tree injection."""
        from app.domain.tools.vision import analyze_image

        with patch('app.domain.tools.vision.vision_engine') as mock_engine:
            mock_engine.process = AsyncMock(return_value=MagicMock(
                success=True,
                summary="Analysis complete"
            ))

            # Patch macos_driver where it's used (in the module's namespace during import)
            with patch('app.infrastructure.drivers.macos.macos_driver') as mock_driver:
                mock_driver.dump_ax_tree.return_value = "AX Tree Data"

                result = await analyze_image.ainvoke({
                    "image_source": "/screenshot.png",
                    "question": "What is this?",
                    "include_ax_tree": True
                })

                assert result == "Analysis complete"

    @pytest.mark.asyncio
    async def test_analyze_image_tool_error(self):
        """Test analyze_image tool error handling."""
        from app.domain.tools.vision import analyze_image

        with patch('app.domain.tools.vision.vision_engine') as mock_engine:
            mock_engine.process = AsyncMock(return_value=MagicMock(
                success=False,
                metadata={"error": "Vision processing failed"}
            ))

            result = await analyze_image.ainvoke({
                "image_source": "/invalid.png",
                "question": "Describe",
                "include_ax_tree": False
            })

            assert "Error:" in result
            assert "Vision processing failed" in result

    @pytest.mark.asyncio
    async def test_analyze_image_tool_ax_tree_unavailable(self):
        """Test analyze_image tool when AX tree is unavailable."""
        from app.domain.tools.vision import analyze_image

        with patch('app.domain.tools.vision.vision_engine') as mock_engine:
            mock_engine.process = AsyncMock(return_value=MagicMock(
                success=True,
                summary="Analysis without AX"
            ))

            with patch('app.infrastructure.drivers.macos.macos_driver') as mock_driver:
                mock_driver.dump_ax_tree.return_value = None

                result = await analyze_image.ainvoke({
                    "image_source": "/screenshot.png",
                    "question": "What?",
                    "include_ax_tree": True
                })

                assert result == "Analysis without AX"


class TestVisionRouter:
    """Tests for VisionRouter."""

    @pytest.mark.asyncio
    async def test_get_provider_for_task(self):
        """Test getting provider for a task."""
        from app.core.vision.router import VisionRouter

        router = VisionRouter()

        # Mock provider that is available
        mock_provider = MagicMock()
        mock_provider.name = "ocr_provider"
        mock_provider.is_available = AsyncMock(return_value=True)

        # Replace providers list
        router.providers = [mock_provider]

        provider = await router.get_provider(VisionTask.OCR)

        assert provider is not None
        assert provider.name == "ocr_provider"

    @pytest.mark.asyncio
    async def test_get_provider_not_available(self):
        """Test getting provider when none are available."""
        from app.core.vision.router import VisionRouter

        router = VisionRouter()

        # Mock provider that is not available
        mock_provider = MagicMock(name="unavailable")
        mock_provider.is_available = AsyncMock(return_value=False)

        router.providers = [mock_provider]

        provider = await router.get_provider(VisionTask.OCR)

        assert provider is None

    @pytest.mark.asyncio
    async def test_get_provider_no_configured_providers(self):
        """Test getting provider when no providers are configured."""
        from app.core.vision.router import VisionRouter

        router = VisionRouter()
        router.providers = []

        provider = await router.get_provider(VisionTask.OCR)

        assert provider is None
