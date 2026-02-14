import logging
from app.core.tools import evoloop_tool
from app.core.vision import vision_engine, VisionTask

logger = logging.getLogger(__name__)


@evoloop_tool
async def analyze_image(image_source: str, question: str = "Describe this image in detail.") -> str:
    """
    Analyze an image using the unified VisionEngine.

    Args:
        image_source: The absolute path to a local image file OR a public image URL.
        question: The question or instruction about the image (e.g., "What is in this image?", "Describe the layout bug").

    Returns:
        A text description or answer derived from the image analysis.
    """
    result = await vision_engine.process(
        task=VisionTask.ANALYZE,
        image_source=image_source,
        prompt=question
    )

    if result.success:
        return result.summary
    else:
        return f"Error: {result.metadata.get('error', 'Unknown error')}"
