"""
Find Element Tool - Vision-guided UI element selection.

Uses the Fusion Pipeline for perception and LLM for natural language
element matching.
"""
import asyncio
import logging
from typing import Literal

from app.core.tools import evoloop_tool
from app.core.vision import VisionTask, vision_engine
from app.core.vision.pipeline.manager import pipeline_manager
from app.infrastructure.drivers.adb import ADBError, adb_driver
from app.infrastructure.drivers.macos import macos_driver

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    summary_template="evoloop.tool_summary.find_element"
)
async def find_element(
    target: str,
    platform: Literal["macos", "android"] | None = None,
    action: Literal["None", "tap", "click"] = "None",
    device_id: str | None = None,
    return_all: bool = False,
) -> str:
    """
    Find a UI element by natural language description and optionally interact with it.
    
    This tool uses Fusion Perception to extract all visible UI elements
    and either returns the best match or directly acts on it (tap/click).
    
    Args:
        target: Natural language description of the element to find.
        platform: Target platform ("macos" or "android"). If None, resolved from session context.
        action: Optional action to perform on the found element ("tap" for mobile, "click" for desktop).
        device_id: Device serial for Android (optional).
        return_all: If True, return all detected elements.
    """
    try:
        # Step 1: Resolve Platform & Take a screenshot
        if platform is None:
            from app.core.context import ContextManager
            ctx = ContextManager.current()
            platform = ctx.metadata.get("current_ecosystem")

        if not platform:
            return "Error: Platform not specified and could not be resolved from context. Please specify 'platform' (macos/android)."

        if platform == "android":
            try:
                screenshot_path = adb_driver.screenshot(device_id=device_id)
            except ADBError as e:
                return f"Android error: {e}"
        elif platform == "macos":
            screenshot_path = macos_driver.screenshot()
        else:
            return f"Error: Unsupported platform '{platform}'"

        # Step 2: Run perception pipeline via VisionEngine
        result = await vision_engine.process(
            task=VisionTask.DETECT,
            image_source=screenshot_path,
            device_id=device_id,
        )

        if not result.success or not result.elements:
            return f"No UI elements detected on screen. Error: {result.metadata.get('error', 'None')}"

        elements = result.elements

        # Fire UI_TREE_OBSERVED event for spatial mapping (Background)
        try:
            from app.core.environment.event import UiTreeObservedEvent
            from app.core.environment.bus import event_bus

            if platform == "android":
                app_info = adb_driver.get_current_app(device_id=device_id)
                bundle_id = app_info.get("package", "unknown")
                window_title = app_info.get("activity", "unknown")
            else:
                app_info = macos_driver.get_current_app()
                bundle_id = app_info.get("bundle_id", "unknown")
                window_title = app_info.get("title", "unknown")

            from app.core.environment.event.publishers import publish_ui_tree_observed
            asyncio.create_task(publish_ui_tree_observed(
                platform=platform,
                bundle_id=bundle_id,
                window_title=window_title,
                elements=[e.model_dump() for e in elements],
                screenshot_hash=result.metadata.get("file_hash", ""),
            ))
        except Exception as e:
            logger.warning(f"Failed to publish UI_TREE_OBSERVED: {e}")

        if return_all or not target:
            formatted = pipeline_manager.format_for_prompt(elements)
            return f"Screenshot: {screenshot_path}\n\n{formatted}", {"count": len(elements)}

        # Step 4: Find best match
        target_lower = target.lower()

        # Score each element
        scored_elements = []
        for element in elements:
            score = 0
            element_text = element.text.lower()

            # Exact match
            if target_lower == element_text:
                score = 100
            # Contains target
            elif target_lower in element_text:
                score = 80
            # Target contains element text
            elif element_text and element_text in target_lower:
                score = 60
            # Partial word match
            else:
                target_words = set(target_lower.split())
                element_words = set(element_text.split())
                common_words = target_words & element_words
                if common_words:
                    score = 40 * len(common_words) / max(len(target_words), 1)

            # Boost clickable elements
            if element.clickable:
                score += 5

            # Apply confidence
            score *= element.confidence

            if score > 0:
                scored_elements.append((element, score))

        if not scored_elements:
            # No match found, return all elements for context
            formatted = pipeline_manager.format_for_prompt(elements[:15])
            return (
                f"No element matching '{target}' found.\n\n"
                f"Available elements:\n{formatted}\n\n"
                f"Screenshot: {screenshot_path}"
            ), {"count": 0, "available_count": len(elements)}

        # Sort by score
        scored_elements.sort(key=lambda x: x[1], reverse=True)
        best_match, score = scored_elements[0]

        result_msg = (
            "Element found!\n"
            f"Text: \"{best_match.text}\"\n"
            f"Position: ({best_match.x}, {best_match.y})\n"
            f"Type: {best_match.element_type.value}\n"
            f"Match Score: {score:.1f}\n"
        )

        # Step 5: Perform Action (Turbo Mode)
        if action == "tap" or action == "click":
            if platform == "android":
                adb_driver.tap(best_match.x, best_match.y, device_id=device_id)
                result_msg += f"\nACTION PERFORMED: Tapped at ({best_match.x}, {best_match.y})"
            elif platform == "macos":
                macos_driver.click(best_match.x, best_match.y)
                result_msg += f"\nACTION PERFORMED: Clicked at ({best_match.x}, {best_match.y})"
            else:
                result_msg += f"\nWarning: Action '{action}' is not supported on platform '{platform}'"
        else:
            result_msg += f"\nReady to interact: {platform}_control(action='tap/click', x={best_match.x}, y={best_match.y})"

        # Include screenshot path
        result_msg += f"\n\nScreenshot: {screenshot_path}"

        return result_msg, {"count": 1, "target": target}

    except Exception as e:
        logger.error(f"find_element error: {e}")
        return f"Error: {str(e)}"
