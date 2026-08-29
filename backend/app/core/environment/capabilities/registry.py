from typing import Any

from pydantic import BaseModel, Field


class ActionDef(BaseModel):
    """
    Definition of a system-wide action (Capability).
    Acts as the single source of truth for prompts, UI, and execution.
    """

    id: str
    platforms: list[str]  # ["dom", "mobile", "desktop"]
    icon: str  # Lucide icon name
    description: str  # For Agent prompt instructions
    translation_key: str  # i18n key for translations (e.g., "actions.click")
    params: dict[str, Any] = Field(default_factory=dict)

    # Mapping to technical tool action names
    # e.g., mappings={"mobile": "tap"} for a "click" action
    mappings: dict[str, str] = Field(default_factory=dict)


class ActionRegistry:
    """Central registry for all Agent capabilities."""

    _actions: dict[str, ActionDef] = {}

    @classmethod
    def register(cls, action: ActionDef):
        cls._actions[action.id] = action

    @classmethod
    def get_action(cls, action_id: str) -> ActionDef | None:
        return cls._actions.get(action_id)

    @classmethod
    def list_actions(cls, platform: str | None = None) -> list[ActionDef]:
        if platform:
            return [a for a in cls._actions.values() if platform in a.platforms]
        return list(cls._actions.values())

    @classmethod
    def get_tool_action(cls, action_id: str, platform: str) -> str:
        """Get the specific tool action name for a platform."""
        action = cls.get_action(action_id)
        if not action:
            return action_id
        return action.mappings.get(platform, action_id)


# --- Core Action Definitions ---

# Navigation
ActionRegistry.register(
    ActionDef(
        id="navigate",
        platforms=["dom"],
        icon="ArrowRight",
        description="Navigate to a specific URL.",
        translation_key="actions.navigate",
        params={"url": "str"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="back",
        platforms=["dom", "mobile"],
        icon="ArrowLeft",
        description="Go back to the previous page/screen.",
        translation_key="actions.back",
        mappings={
            "mobile": "press_key"
        },  # Usually mapped to back key or press_key("back")
    )
)

ActionRegistry.register(
    ActionDef(
        id="forward",
        platforms=["dom"],
        icon="ArrowRight",
        description="Go forward to the next page.",
        translation_key="actions.forward",
    )
)

ActionRegistry.register(
    ActionDef(
        id="reload",
        platforms=["dom"],
        icon="RotateCcw",
        description="Reload the current page.",
        translation_key="actions.reload",
    )
)

# Interaction
ActionRegistry.register(
    ActionDef(
        id="click",
        platforms=["dom", "mobile", "desktop"],
        icon="MousePointerClick",
        description="Click on a target element or coordinate.",
        translation_key="actions.click",
        mappings={"mobile": "tap"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="double_click",
        platforms=["dom", "desktop"],
        icon="MousePointerClick",
        description="Double-click on a target element or coordinate.",
        translation_key="actions.double_click",
    )
)

ActionRegistry.register(
    ActionDef(
        id="hover",
        platforms=["dom"],
        icon="MousePointer",
        description="Hover over an element.",
        translation_key="actions.hover",
    )
)

ActionRegistry.register(
    ActionDef(
        id="input",
        platforms=["dom", "mobile"],
        icon="Keyboard",
        description="Input text into a field.",
        translation_key="actions.input",
        params={"text": "str"},
        mappings={"mobile": "input_text", "dom": "input"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="key_press",
        platforms=["dom", "mobile", "desktop"],
        icon="Keyboard",
        description="Press a specific key or key combination.",
        translation_key="actions.key_press",
        params={"key": "str"},
        mappings={"mobile": "press_key"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="scroll",
        platforms=["dom", "mobile", "desktop"],
        icon="RefreshCw",
        description="Scroll the page or element.",
        translation_key="actions.scroll",
    )
)

ActionRegistry.register(
    ActionDef(
        id="drag_drop",
        platforms=["dom", "desktop"],
        icon="Move",
        description="Drag an element and drop it at a target.",
        translation_key="actions.drag_drop",
    )
)

# Wait
ActionRegistry.register(
    ActionDef(
        id="wait",
        platforms=["dom", "mobile", "desktop"],
        icon="Clock",
        description="Wait for a specific duration in milliseconds.",
        translation_key="actions.wait",
        params={"duration_ms": "int"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="wait_for",
        platforms=["dom"],
        icon="Clock",
        description="Wait for an element to appear or a page to load.",
        translation_key="actions.wait_for",
    )
)

# Extraction
ActionRegistry.register(
    ActionDef(
        id="get_text",
        platforms=["dom"],
        icon="Download",
        description="Extract text content from an element.",
        translation_key="actions.get_text",
    )
)

ActionRegistry.register(
    ActionDef(
        id="get_elements",
        platforms=["dom"],
        icon="List",
        description="Extract a list of elements matching a selector. Returns a list of element data objects.",
        translation_key="actions.get_elements",
    )
)

ActionRegistry.register(
    ActionDef(
        id="get_attribute",
        platforms=["dom"],
        icon="Download",
        description="Extract a specific attribute from an element.",
        translation_key="actions.get_attribute",
        params={"attribute": "str"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="screenshot",
        platforms=["dom", "mobile", "desktop"],
        icon="Eye",
        description="Take a screenshot of the current view. Supports 'region' parameter (x,y,w,h).",
        translation_key="actions.screenshot",
        params={"region": "str"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="gui_extract",
        platforms=["mobile", "desktop"],
        icon="ScanText",
        description="Extract text from a specific GUI region using coordinates and OCR. Supports 'ocr_nearby' method.",
        translation_key="actions.gui_extract",
        params={"relative_position": "dict", "extraction_method": "str"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="get_clipboard",
        platforms=["mobile"],
        icon="Clipboard",
        description="Read the current text from the system clipboard.",
        translation_key="actions.get_clipboard",
    )
)

# OS / App
ActionRegistry.register(
    ActionDef(
        id="open_app",
        platforms=["mobile", "desktop"],
        icon="ExternalLink",
        description="Open an application by name or package.",
        translation_key="actions.open_app",
        params={"app_name": "str"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="close_app",
        platforms=["mobile", "desktop"],
        icon="Power",
        description="Close the currently active application.",
        translation_key="actions.close_app",
    )
)

ActionRegistry.register(
    ActionDef(
        id="home",
        platforms=["mobile"],
        icon="Home",
        description="Return to the home screen.",
        translation_key="actions.home",
    )
)

ActionRegistry.register(
    ActionDef(
        id="back_key",
        platforms=["mobile"],
        icon="ArrowLeft",
        description="Press the physical back button.",
        translation_key="actions.back_key",
        mappings={"mobile": "press_key"},
    )
)

# Desktop Specific
ActionRegistry.register(
    ActionDef(
        id="applescript",
        platforms=["desktop"],
        icon="Type",
        description="Execute an AppleScript snippet.",
        translation_key="actions.applescript",
        params={"script": "str"},
    )
)

ActionRegistry.register(
    ActionDef(
        id="get_active_app",
        platforms=["desktop"],
        icon="ExternalLink",
        description="Get information about the currently active application.",
        translation_key="actions.get_active_app",
    )
)

ActionRegistry.register(
    ActionDef(
        id="dump_ui",
        platforms=["mobile", "desktop"],
        icon="Eye",
        description="Dump the current UI hierarchy.",
        translation_key="actions.dump_ui",
    )
)


ActionRegistry.register(
    ActionDef(
        id="detect_pagination",
        platforms=["dom"],
        icon="ArrowRightCircle",
        description="Detect next-page buttons or indicators on the current page. Returns JSON with 'has_next' and 'next_selector'.",
        translation_key="actions.detect_pagination",
    )
)


ActionRegistry.register(
    ActionDef(
        id="scroll_to_bottom",
        platforms=["dom"],
        icon="ChevronLast",
        description="Scroll to the bottom of the page incrementally to trigger infinite scroll/loading. Supports 'max_scrolls' and 'delay_ms'.",
        translation_key="actions.scroll_to_bottom",
    )
)
