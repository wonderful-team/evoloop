import logging

from app.core.tools import evoloop_tool
from app.core.vision import VisionTask, vision_engine

logger = logging.getLogger(__name__)


@evoloop_tool
async def analyze_image(
    image_source: str,
    question: str = "Describe this image in detail.",
    include_ax_tree: bool = False
) -> str:
    """
    Analyze an image using the unified VisionEngine.

    Args:
        image_source: The absolute path to a local image file OR a public image URL.
        question: The question or instruction about the image (e.g., "What is in this image?", "Describe the layout bug").
        include_ax_tree: If True, dumps the macOS Accessibility (AX) Tree and appends it to the prompt for grounding.

    Returns:
        A text description or answer derived from the image analysis.
    """
    final_prompt = question

    if include_ax_tree:
        try:
            from app.infrastructure.drivers.macos import macos_driver
            ax_tree = macos_driver.dump_ax_tree()
            if ax_tree and "Error" not in ax_tree:
                final_prompt += f"\n\n### macOS Accessibility (AX) Tree Context:\n{ax_tree}\n\nUse the element names and bounds above to provide precise coordinates if asked to click or interact."
                logger.info("[Vision] Injected AX Tree into prompt for grounding.")
        except Exception as e:
            logger.warning(f"[Vision] Failed to inject AX Tree: {e}")

    result = await vision_engine.process(
        task=VisionTask.ANALYZE,
        image_source=image_source,
        prompt=final_prompt
    )

    if result.success:
        return result.summary
    else:
        return f"Error: {result.metadata.get('error', 'Unknown error')}"
