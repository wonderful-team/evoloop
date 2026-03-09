from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActionDef(BaseModel):
    """
    Definition of a system-wide action (Capability).
    Acts as the single source of truth for prompts, UI, and execution.
    """
    id: str
    platforms: List[str]  # ["dom", "mobile", "desktop"]
    icon: str  # Lucide icon name
    description: str  # For Agent prompt instructions
    zh: str  # Chinese label
    en: str  # English label
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Mapping to technical tool action names
    # e.g., mappings={"mobile": "tap"} for a "click" action
    mappings: Dict[str, str] = Field(default_factory=dict)


class ActionRegistry:
    """Central registry for all Agent capabilities."""
    
    _actions: Dict[str, ActionDef] = {}

    @classmethod
    def register(cls, action: ActionDef):
        cls._actions[action.id] = action

    @classmethod
    def get_action(cls, action_id: str) -> Optional[ActionDef]:
        return cls._actions.get(action_id)

    @classmethod
    def list_actions(cls, platform: Optional[str] = None) -> List[ActionDef]:
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
ActionRegistry.register(ActionDef(
    id="navigate",
    platforms=["dom"],
    icon="ArrowRight",
    description="Navigate to a specific URL.",
    zh="导航",
    en="Navigate",
    params={"url": "str"}
))

ActionRegistry.register(ActionDef(
    id="back",
    platforms=["dom", "mobile"],
    icon="ArrowLeft",
    description="Go back to the previous page/screen.",
    zh="后退",
    en="Back",
    mappings={"mobile": "press_key"} # Usually mapped to back key or press_key("back")
))

ActionRegistry.register(ActionDef(
    id="forward",
    platforms=["dom"],
    icon="ArrowRight",
    description="Go forward to the next page.",
    zh="前进",
    en="Forward"
))

ActionRegistry.register(ActionDef(
    id="reload",
    platforms=["dom"],
    icon="RotateCcw",
    description="Reload the current page.",
    zh="刷新",
    en="Reload"
))

# Interaction
ActionRegistry.register(ActionDef(
    id="click",
    platforms=["dom", "mobile", "desktop"],
    icon="MousePointerClick",
    description="Click on a target element or coordinate.",
    zh="点击",
    en="Click",
    mappings={"mobile": "tap"}
))

ActionRegistry.register(ActionDef(
    id="double_click",
    platforms=["dom", "desktop"],
    icon="MousePointerClick",
    description="Double-click on a target element or coordinate.",
    zh="双击",
    en="Double Click"
))

ActionRegistry.register(ActionDef(
    id="hover",
    platforms=["dom"],
    icon="MousePointer",
    description="Hover over an element.",
    zh="悬停",
    en="Hover"
))

ActionRegistry.register(ActionDef(
    id="input",
    platforms=["dom", "mobile"],
    icon="Keyboard",
    description="Input text into a field.",
    zh="输入",
    en="Input",
    params={"text": "str"},
    mappings={"mobile": "input_text", "dom": "input"}
))

ActionRegistry.register(ActionDef(
    id="key_press",
    platforms=["dom", "mobile", "desktop"],
    icon="Keyboard",
    description="Press a specific key or key combination.",
    zh="按键",
    en="Key Press",
    params={"key": "str"},
    mappings={"mobile": "press_key"}
))

ActionRegistry.register(ActionDef(
    id="scroll",
    platforms=["dom", "mobile", "desktop"],
    icon="RefreshCw",
    description="Scroll the page or element.",
    zh="滚动",
    en="Scroll"
))

ActionRegistry.register(ActionDef(
    id="drag_drop",
    platforms=["dom", "desktop"],
    icon="Move",
    description="Drag an element and drop it at a target.",
    zh="拖拽",
    en="Drag & Drop"
))

# Wait
ActionRegistry.register(ActionDef(
    id="wait",
    platforms=["dom", "mobile", "desktop"],
    icon="Clock",
    description="Wait for a specific duration in milliseconds.",
    zh="等待时间",
    en="Wait Duration",
    params={"duration_ms": "int"}
))

ActionRegistry.register(ActionDef(
    id="wait_for",
    platforms=["dom"],
    icon="Clock",
    description="Wait for an element to appear or a page to load.",
    zh="等待元素/页面",
    en="Wait For Element/Page"
))

# Extraction
ActionRegistry.register(ActionDef(
    id="get_text",
    platforms=["dom"],
    icon="Download",
    description="Extract text content from an element.",
    zh="提取文本",
    en="Extract Text"
))

ActionRegistry.register(ActionDef(
    id="get_elements",
    platforms=["dom"],
    icon="List",
    description="Extract a list of elements matching a selector. Returns a list of element data objects.",
    zh="提取元素列表",
    en="Extract Elements List"
))

ActionRegistry.register(ActionDef(
    id="get_attribute",
    platforms=["dom"],
    icon="Download",
    description="Extract a specific attribute from an element.",
    zh="提取属性",
    en="Extract Attribute",
    params={"attribute": "str"}
))

ActionRegistry.register(ActionDef(
    id="screenshot",
    platforms=["dom", "mobile", "desktop"],
    icon="Eye",
    description="Take a screenshot of the current view. Supports 'region' parameter (x,y,w,h).",
    zh="截图",
    en="Screenshot",
    params={"region": "str"}
))

ActionRegistry.register(ActionDef(
    id="gui_extract",
    platforms=["mobile", "desktop"],
    icon="ScanText",
    description="Extract text from a specific GUI region using coordinates and OCR. Supports 'ocr_nearby' method.",
    zh="智能提取 (OCR)",
    en="AI GUI Extract (OCR)",
    params={"relative_position": "dict", "extraction_method": "str"}
))

# OS / App
ActionRegistry.register(ActionDef(
    id="open_app",
    platforms=["mobile", "desktop"],
    icon="ExternalLink",
    description="Open an application by name or package.",
    zh="打开应用",
    en="Open App",
    params={"app_name": "str"}
))

ActionRegistry.register(ActionDef(
    id="close_app",
    platforms=["mobile", "desktop"],
    icon="Power",
    description="Close the currently active application.",
    zh="关闭应用",
    en="Close App"
))

ActionRegistry.register(ActionDef(
    id="home",
    platforms=["mobile"],
    icon="Home",
    description="Return to the home screen.",
    zh="主屏幕",
    en="Home"
))

ActionRegistry.register(ActionDef(
    id="back_key",
    platforms=["mobile"],
    icon="ArrowLeft",
    description="Press the physical back button.",
    zh="物理后退键",
    en="Back Key",
    mappings={"mobile": "press_key"}
))

# Desktop Specific
ActionRegistry.register(ActionDef(
    id="applescript",
    platforms=["desktop"],
    icon="Type",
    description="Execute an AppleScript snippet.",
    zh="AppleScript",
    en="AppleScript",
    params={"script": "str"}
))

ActionRegistry.register(ActionDef(
    id="get_active_app",
    platforms=["desktop"],
    icon="ExternalLink",
    description="Get information about the currently active application.",
    zh="获取活动应用",
    en="Get Active App"
))

ActionRegistry.register(ActionDef(
    id="dump_ui",
    platforms=["mobile", "desktop"],
    icon="Eye",
    description="Dump the current UI hierarchy.",
    zh="转储 UI",
    en="Dump UI"
))


ActionRegistry.register(ActionDef(
    id="detect_pagination",
    platforms=["dom"],
    icon="ArrowRightCircle",
    description="Detect next-page buttons or indicators on the current page. Returns JSON with 'has_next' and 'next_selector'.",
    zh="检测分页",
    en="Detect Pagination"
))


ActionRegistry.register(ActionDef(
    id="scroll_to_bottom",
    platforms=["dom"],
    icon="ChevronLast",
    description="Scroll to the bottom of the page incrementally to trigger infinite scroll/loading. Supports 'max_scrolls' and 'delay_ms'.",
    zh="滚动到底部",
    en="Scroll to Bottom"
))
