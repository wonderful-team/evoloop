"""
Find Element Tool - Vision-guided UI element selection.

Uses the Fusion Pipeline for perception and LLM for natural language
element matching.
"""

import logging
from typing import Literal

from app.core.tools import evoloop_tool
from app.domain.tools.environment.perception.pipeline import fusion_pipeline
from app.domain.tools.environment.perception.base import UIElement
from app.domain.tools.environment.drivers.macos import macos_driver
from app.domain.tools.environment.drivers.adb import adb_driver, ADBError

logger = logging.getLogger(__name__)


@evoloop_tool
async def find_element(
    target: str,
    platform: Literal["macos", "android"] = "android",
    device_id: str | None = None,
    return_all: bool = False,
) -> str:
    """
    Find a UI element by natural language description.
    
    This tool uses Fusion Perception to extract all visible UI elements
    and returns the best match for your target description.
    
    Args:
        target: Natural language description of the element to find.
                Examples: "微信图标", "搜索按钮", "输入框", "提交按钮"
        platform: Target platform ("macos" or "android")
        device_id: Device serial for Android (optional)
        return_all: If True, return all detected elements
        
    Returns:
        Information about the found element including coordinates.
    
    Example:
        # Find an element
        find_element(target="微信图标", platform="android")
        # Returns: Element found: "微信" @ (540, 1800) - Ready to tap
        
        # List all elements
        find_element(target="", platform="android", return_all=True)
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
        
        # Step 2: Run perception pipeline
        elements, compressed_path = await fusion_pipeline.perceive(
            screenshot_path=screenshot_path,
            device_id=device_id,
        )
        
        if not elements:
            return "No UI elements detected on screen. The screen might be empty or OCR failed."
        
        # Step 3: Return all elements if requested
        if return_all or not target:
            formatted = fusion_pipeline.format_for_prompt(elements)
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
            formatted = fusion_pipeline.format_for_prompt(elements[:15])
            return (
                f"No element matching '{target}' found.\n\n"
                f"Available elements:\n{formatted}\n\n"
                f"Screenshot: {compressed_path or screenshot_path}"
            )
        
        # Sort by score
        scored_elements.sort(key=lambda x: x[1], reverse=True)
        best_match, score = scored_elements[0]
        
        result = (
            f"✅ Element found!\n"
            f"Text: \"{best_match.text}\"\n"
            f"Position: ({best_match.x}, {best_match.y})\n"
            f"Type: {best_match.element_type.value}\n"
            f"Confidence: {best_match.confidence:.2f}\n"
            f"Match Score: {score:.1f}\n\n"
            f"To interact with this element:\n"
        )
        
        if platform == "android":
            result += f"  mobile_control(action=\"tap\", x={best_match.x}, y={best_match.y})"
        else:
            result += f"  desktop_control(action=\"click\", x={best_match.x}, y={best_match.y})"
        
        # Include screenshot path for vision analysis if needed
        result += f"\n\nScreenshot: {compressed_path or screenshot_path}"
        
        return result
    
    except Exception as e:
        logger.error(f"find_element error: {e}")
        return f"Error: {str(e)}"
