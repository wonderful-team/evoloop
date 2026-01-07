"""
Vision Tools for Agent visual perception capabilities.
Enables the agent to "see" and understand screenshots, images, and UI elements.
"""

import os
import logging
import tempfile
from datetime import datetime
from typing import Optional, Literal, List

from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from app.core.llm.vision import VisionLLMFactory, get_vision_llm
from app.core.config import settings

logger = logging.getLogger("evoloop.tools.vision")

# Directory for storing screenshots
SCREENSHOTS_DIR = settings.SCREENSHOTS_DIR
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ============ Input Schemas ============

class AnalyzeScreenshotInput(BaseModel):
    image_path: str = Field(..., description="Absolute path to the screenshot image file.")
    question: Optional[str] = Field(
        None, 
        description="Optional specific question about the image. If not provided, returns general description."
    )
    detail_level: Literal["brief", "detailed", "structured"] = Field(
        "detailed",
        description="Level of detail: 'brief' for short summary, 'detailed' for full description, 'structured' for UI element breakdown."
    )


class LocateElementInput(BaseModel):
    image_path: str = Field(..., description="Absolute path to the screenshot image file.")
    element_description: str = Field(..., description="Description of the element to locate (e.g., 'the blue Submit button', 'the search input field').")


class CompareScreenshotsInput(BaseModel):
    image_path_before: str = Field(..., description="Path to the 'before' screenshot.")
    image_path_after: str = Field(..., description="Path to the 'after' screenshot.")
    focus: Optional[str] = Field(None, description="Optional: specific area or element to compare.")


class ExtractTextInput(BaseModel):
    image_path: str = Field(..., description="Absolute path to the image file.")
    region: Optional[str] = Field(None, description="Optional: specific region to extract text from (e.g., 'top-left', 'center modal').")


# ============ Prompts ============

ANALYZE_PROMPT_BRIEF = """Briefly describe what you see in this screenshot in 2-3 sentences."""

ANALYZE_PROMPT_DETAILED = """Describe this screenshot in detail. Include:
1. What application or webpage is shown
2. The main content and purpose
3. Key UI elements visible (buttons, forms, menus)
4. Any notable state (errors, loading, notifications)
5. The overall layout structure"""

ANALYZE_PROMPT_STRUCTURED = """Analyze this UI screenshot and provide a structured breakdown.
Output as:
## Application Type
[Type of application/website]

## Page/Screen Identification
[What page or screen this appears to be]

## UI Elements
List all interactive elements:
- Buttons: [list with labels]
- Input Fields: [list with placeholder/labels]
- Links: [list]
- Dropdowns/Selectors: [list]
- Other: [any other interactive elements]

## Current State
- Active element: [if any]
- Form values: [visible values]
- Notifications/Alerts: [if any]
- Loading states: [if any]

## Layout
[Brief description of the layout structure]"""

LOCATE_ELEMENT_PROMPT = """Locate the following element in this screenshot: "{element}"

Provide:
1. **Found**: Yes/No
2. **Location**: Approximate position (e.g., "top-right corner", "center of screen", "within the sidebar")
3. **Bounding Box Estimate**: Rough coordinates as percentages of image (x%, y%, width%, height%)
4. **Visual Description**: What the element looks like
5. **Confidence**: High/Medium/Low

If multiple matching elements exist, describe all of them."""

COMPARE_SCREENSHOTS_PROMPT = """Compare these two screenshots (before and after).

Identify:
1. **What Changed**: All visible differences
2. **New Elements**: Elements that appeared
3. **Removed Elements**: Elements that disappeared  
4. **Modified Elements**: Elements that changed (text, color, position, size)
5. **State Changes**: Any state indicators that changed (loading, errors, selections)
{focus_instruction}
Be specific about locations and provide details useful for understanding UI state transitions."""

EXTRACT_TEXT_PROMPT = """Extract all visible text from this screenshot.
{region_instruction}
Output the text organized by:
1. **Headers/Titles**: Main headings
2. **Body Text**: Paragraphs and descriptions
3. **Labels**: Form labels, button text, menu items
4. **Data**: Numbers, dates, identifiers
5. **Status/Alerts**: Error messages, notifications

Preserve the hierarchical structure where possible."""


# ============ Tools ============

@tool("analyze_screenshot", args_schema=AnalyzeScreenshotInput)
async def analyze_screenshot(
    image_path: str,
    question: Optional[str] = None,
    detail_level: Literal["brief", "detailed", "structured"] = "detailed"
) -> str:
    """
    Analyze a screenshot using Vision LLM.
    
    Use this tool to understand what's displayed on screen, identify UI elements,
    or answer specific questions about visual content.
    
    Returns a textual description of the screenshot.
    """
    if not os.path.exists(image_path):
        return f"Error: Image not found at {image_path}"
    
    try:
        llm = get_vision_llm()
        
        # Select prompt based on detail level
        if question:
            prompt = f"Looking at this screenshot, answer this question: {question}"
        elif detail_level == "brief":
            prompt = ANALYZE_PROMPT_BRIEF
        elif detail_level == "structured":
            prompt = ANALYZE_PROMPT_STRUCTURED
        else:
            prompt = ANALYZE_PROMPT_DETAILED
        
        message = VisionLLMFactory.create_image_message(image_path, prompt)
        
        response = await llm.ainvoke([message])
        
        logger.info(f"Analyzed screenshot: {image_path}")
        return response.content
        
    except Exception as e:
        logger.error(f"Failed to analyze screenshot: {e}")
        return f"Error analyzing screenshot: {e}"


@tool("locate_element", args_schema=LocateElementInput)
async def locate_element(
    image_path: str,
    element_description: str
) -> str:
    """
    Locate a specific UI element in a screenshot.
    
    Use this tool when you need to find where a button, input field, or other
    element is located on screen for interaction.
    
    Returns the element's location and visual description.
    """
    if not os.path.exists(image_path):
        return f"Error: Image not found at {image_path}"
    
    try:
        llm = get_vision_llm()
        
        prompt = LOCATE_ELEMENT_PROMPT.format(element=element_description)
        message = VisionLLMFactory.create_image_message(image_path, prompt)
        
        response = await llm.ainvoke([message])
        
        logger.info(f"Located element '{element_description}' in {image_path}")
        return response.content
        
    except Exception as e:
        logger.error(f"Failed to locate element: {e}")
        return f"Error locating element: {e}"


@tool("compare_screenshots", args_schema=CompareScreenshotsInput)
async def compare_screenshots(
    image_path_before: str,
    image_path_after: str,
    focus: Optional[str] = None
) -> str:
    """
    Compare two screenshots to identify visual differences.
    
    Use this tool for:
    - Verifying UI changes after an action
    - Detecting state transitions
    - Identifying what changed between two points in time
    
    Returns a detailed comparison of the differences.
    """
    if not os.path.exists(image_path_before):
        return f"Error: 'Before' image not found at {image_path_before}"
    if not os.path.exists(image_path_after):
        return f"Error: 'After' image not found at {image_path_after}"
    
    try:
        llm = get_vision_llm()
        
        focus_instruction = ""
        if focus:
            focus_instruction = f"\n\nFocus especially on: {focus}"
        
        prompt = COMPARE_SCREENSHOTS_PROMPT.format(focus_instruction=focus_instruction)
        
        message = VisionLLMFactory.create_multi_image_message(
            [image_path_before, image_path_after],
            prompt
        )
        
        response = await llm.ainvoke([message])
        
        logger.info(f"Compared screenshots: {image_path_before} vs {image_path_after}")
        return response.content
        
    except Exception as e:
        logger.error(f"Failed to compare screenshots: {e}")
        return f"Error comparing screenshots: {e}"


@tool("extract_text_from_image", args_schema=ExtractTextInput)
async def extract_text_from_image(
    image_path: str,
    region: Optional[str] = None
) -> str:
    """
    Extract all visible text from an image (OCR-like functionality).
    
    Use this tool when you need to read text displayed on screen,
    such as error messages, form content, or displayed data.
    
    Returns organized text content from the image.
    """
    if not os.path.exists(image_path):
        return f"Error: Image not found at {image_path}"
    
    try:
        llm = get_vision_llm()
        
        region_instruction = ""
        if region:
            region_instruction = f"Focus on extracting text from: {region}"
        
        prompt = EXTRACT_TEXT_PROMPT.format(region_instruction=region_instruction)
        message = VisionLLMFactory.create_image_message(image_path, prompt)
        
        response = await llm.ainvoke([message])
        
        logger.info(f"Extracted text from: {image_path}")
        return response.content
        
    except Exception as e:
        logger.error(f"Failed to extract text: {e}")
        return f"Error extracting text: {e}"


# ============ Screenshot Capture Utilities ============

def get_screenshot_path(prefix: str = "screenshot") -> str:
    """Generate a unique screenshot file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.png"
    return os.path.join(SCREENSHOTS_DIR, filename)


# Placeholder for desktop screenshot capture
# This will be implemented in the Tauri frontend layer
async def capture_screen_region(
    x: int, y: int, width: int, height: int
) -> Optional[str]:
    """
    Capture a region of the screen.
    
    Note: This is a placeholder. Actual implementation requires
    platform-specific code (Tauri command for desktop app).
    """
    logger.warning("capture_screen_region is not implemented in backend. Use Tauri frontend API.")
    return None
