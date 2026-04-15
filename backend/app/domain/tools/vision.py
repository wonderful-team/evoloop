import logging

from app.core.tools import evoloop_tool
from app.core.vision import VisionTask, vision_engine
from app.infrastructure.drivers.macos import macos_driver
from app.utils import render_template

logger = logging.getLogger(__name__)


@evoloop_tool(
    name_map={"zh": "分析图像", "en": "Analyze Image"}
)
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
            from app.core.context import ContextManager
            ctx = ContextManager.current()
            current_ecosystem = ctx.metadata.get("current_ecosystem")

            if current_ecosystem == "android":
                from app.infrastructure.drivers.adb import adb_driver
                ax_tree = adb_driver.dump_ui()
                tree_label = "Android UI Hierarchy"
            else:
                ax_tree = macos_driver.dump_ax_tree()
                tree_label = "macOS Accessibility (AX) Tree"

            if ax_tree and "Error" not in ax_tree:
                final_prompt = render_template("core/vision/vision_context.prompt.j2", tree_label=tree_label, ax_tree=ax_tree)
                logger.info(f"[Vision] Injected {tree_label} into prompt via template.")
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
