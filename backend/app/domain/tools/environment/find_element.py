"""
Find Element Tool - Vision-guided UI element selection.

Uses the Fusion Pipeline for perception and LLM for natural language
element matching.
"""

import logging
from typing import Literal

from app.core.tools import evoloop_tool
from app.core.vision import vision_engine, VisionTask
from app.core.vision.pipeline.manager import pipeline_manager
from app.domain.tools.environment.drivers.macos import macos_driver
from app.domain.tools.environment.drivers.adb import adb_driver, ADBError

logger = logging.getLogger(__name__)


@evoloop_tool
async def find_element(
    target: str,
    platform: Literal["macos", "android"] = "android",
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
                Examples: "微信图标", "搜索按钮", "输入框", "提交按钮"
        platform: Target platform ("macos" or "android")
        action: Optional action to perform on the found element:
                - "None": Find only (default)
                - "tap": Find and tap (Android only)
                - "click": Find and click (MacOS only)
        device_id: Device serial for Android (optional)
        return_all: If True, return all detected elements
        
    Returns:
        Information about the found element and action result.
    
    Example:
        # One-shot Find & Click:
        find_element(target="微信图标", platform="android", action="tap")
        
        # Just Find:
        find_element(target="搜索按钮", platform="android")
    """
    try:
        # Step 1: Take a screenshot
        if platform == "android":
            try:
                screenshot_path = adb_driver.screenshot(device_id=device_id)
            except ADBError as e:
                return f"Android error: {e}"
        else:  # macos
            screenshot_path = macos_driver.screenshot()
        
        # Step 2: Run perception pipeline via VisionEngine
        result = await vision_engine.process(
            task=VisionTask.DETECT,
            image_source=screenshot_path,
            device_id=device_id,
        )
        
        if not result.success or not result.elements:
            return f"No UI elements detected on screen. Error: {result.metadata.get('error', 'None')}"
        
        elements = result.elements
        compressed_path = result.screenshot_path
        
        # Step 3: Return all elements if requested
        if return_all or not target:
            formatted = pipeline_manager.format_for_prompt(elements)
            return f"Screenshot: {compressed_path or screenshot_path}\n\n{formatted}"
        
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
                f"Screenshot: {compressed_path or screenshot_path}"
            )
        
        # Sort by score
        scored_elements.sort(key=lambda x: x[1], reverse=True)
        best_match, score = scored_elements[0]
        
        result_msg = (
            f"✅ Element found!\n"
            f"Text: \"{best_match.text}\"\n"
            f"Position: ({best_match.x}, {best_match.y})\n"
            f"Type: {best_match.element_type.value}\n"
            f"Match Score: {score:.1f}\n"
        )
        
        # Step 5: Perform Action (Turbo Mode)
        if action == "tap" and platform == "android":
            adb_driver.tap(best_match.x, best_match.y, device_id=device_id)
            result_msg += f"\n👉 ACTION PERFORMED: Tapped at ({best_match.x}, {best_match.y})"
        
        elif action == "click" and platform == "macos":
            macos_driver.click(best_match.x, best_match.y)
            result_msg += f"\n👉 ACTION PERFORMED: Clicked at ({best_match.x}, {best_match.y})"
            
        else:
            result_msg += f"\nReady to interact: {platform}_control(action='tap/click', x={best_match.x}, y={best_match.y})"
        
        # Include screenshot path
        result_msg += f"\n\nScreenshot: {compressed_path or screenshot_path}"
        
        return result_msg
    
    except Exception as e:
        logger.error(f"find_element error: {e}")
        return f"Error: {str(e)}"
