from app.domain.system.service import SystemConfigService


class VisionPromptBuilder:
    """
    Builder for Vision-related prompts.
    """

    @staticmethod
    def _get_lang_instruction() -> str:
        # Vision analysis often needs to return structured data, but sometimes descriptions.
        # If descriptions are needed, they should be in user language.
        user_lang = SystemConfigService.get_language_preference()
        return f"\nIMPORTANT: Provide all descriptions and analysis in {user_lang}."

    @staticmethod
    def build_ui_analysis_prompt() -> str:
        return f"""Analyze this UI screenshot and provide a structured breakdown.
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
[Brief description of the layout structure]

{VisionPromptBuilder._get_lang_instruction()}
"""

    @staticmethod
    def build_locate_element_prompt(element: str) -> str:
        return f"""Locate the following element in this screenshot: "{element}"

Provide:
1. **Found**: Yes/No
2. **Location**: Approximate position (e.g., "top-right corner", "center of screen", "within the sidebar")
3. **Bounding Box Estimate**: Rough coordinates as percentages of image (x%, y%, width%, height%)
4. **Visual Description**: What the element looks like
5. **Confidence**: High/Medium/Low

If multiple matching elements exist, describe all of them.
{VisionPromptBuilder._get_lang_instruction()}
"""

    @staticmethod
    def build_compare_screenshots_prompt(focus_instruction: str = "") -> str:
        return f"""Compare these two screenshots (before and after).

Identify:
1. **What Changed**: All visible differences
2. **New Elements**: Elements that appeared
3. **Removed Elements**: Elements that disappeared  
4. **Modified Elements**: Elements that changed (text, color, position, size)
5. **State Changes**: Any state indicators that changed (loading, errors, selections)
{focus_instruction}
Be specific about locations and provide details useful for understanding UI state transitions.
{VisionPromptBuilder._get_lang_instruction()}
"""

    @staticmethod
    def build_extract_text_prompt(region_instruction: str = "") -> str:
        return f"""Extract all visible text from this screenshot.
{region_instruction}
Output the text organized by:
1. **Headers/Titles**: Main headings
2. **Body Text**: Paragraphs and descriptions
3. **Labels**: Form labels, button text, menu items
4. **Data**: Numbers, dates, identifiers
5. **Status/Alerts**: Error messages, notifications

Preserve the hierarchical structure where possible.
"""
# Note: Text extraction usually preserves original language, so we don't force translation here unless requested.
