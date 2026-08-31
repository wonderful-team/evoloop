import logging

from app.core.tools import evoloop_tool
from app.infrastructure.drivers.macos import macos_driver
from app.infrastructure.vision import VisionTask, vision_engine
from app.infrastructure.vision.types import PlatformType
from app.utils.template import render_template

logger = logging.getLogger(__name__)


@evoloop_tool(
    summary_template="evoloop.tool_summary.analyze_image",
    affected_path_keys=["image_source"],
    is_multimodal=True,
)
async def analyze_image(
    image_source: str,
    question: str = "Describe this image in detail.",
    include_ax_tree: bool = False,
) -> str:
    """
    用统一的 VisionEngine 分析一张图片。

    Args:
        image_source: 本地图片文件的绝对路径 或 公开图片 URL。
        question: 关于图片的问题或指令（如"图片里有什么？"、"描述这个布局问题"）。
        include_ax_tree: 为 True 时 dump macOS Accessibility (AX) 树并追加到 prompt 用于接地。

    Returns:
        基于图片分析得出的文本描述或答案。
    """
    final_prompt = question

    if include_ax_tree:
        try:
            from app.core.context import ContextManager

            ctx = ContextManager.current()
            current_ecosystem = ctx.metadata.get("current_ecosystem")

            if current_ecosystem == PlatformType.ANDROID.value:
                from app.infrastructure.drivers.adb import adb_driver

                ax_tree = adb_driver.dump_ui()
                tree_label = "Android UI Hierarchy"
            else:
                ax_tree = macos_driver.dump_ax_tree()
                tree_label = "macOS Accessibility (AX) Tree"

            if ax_tree and "Error" not in ax_tree:
                final_prompt = render_template(
                    "core/vision/vision_context.prompt.j2",
                    tree_label=tree_label,
                    ax_tree=ax_tree,
                )
                logger.info(f"[Vision] Injected {tree_label} into prompt via template.")
        except Exception as e:
            logger.warning(f"[Vision] Failed to inject AX Tree: {e}", exc_info=True)

    result = await vision_engine.process(
        task=VisionTask.ANALYZE, image_source=image_source, prompt=final_prompt
    )

    if result.success:
        return result.summary
    else:
        return f"Error: {result.metadata.get('error', 'Unknown error')}"
