from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ElementType(Enum):
    """Type of UI element."""
    BUTTON = "button"
    INPUT = "input"
    TEXT = "text"
    ICON = "icon"
    IMAGE = "image"
    CONTAINER = "container"
    LIST_ITEM = "list_item"
    CHECKBOX = "checkbox"
    SWITCH = "switch"
    UNKNOWN = "unknown"


class VisionTask(Enum):
    """Types of vision tasks."""
    OCR = "ocr"             # Text extraction
    DETECT = "detect"       # Object/Element detection
    CAPTION = "caption"     # Image description
    ANALYZE = "analyze"     # Detailed UI analysis
    COMPARE = "compare"     # Screenshot comparison


@dataclass
class UIElement:
    """
    Represents a detected UI element on screen.
    """
    id: int
    text: str
    x: int  # Center X coordinate
    y: int  # Center Y coordinate
    width: int = 0
    height: int = 0
    element_type: ElementType = ElementType.UNKNOWN
    clickable: bool = True
    confidence: float = 1.0
    source: str = ""  # "ocr", "native", "llm"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Return (x1, y1, x2, y2) bounds."""
        half_w = self.width // 2
        half_h = self.height // 2
        return (
            self.x - half_w,
            self.y - half_h,
            self.x + half_w,
            self.y + half_h,
        )

    def to_prompt_line(self) -> str:
        """Format element for LLM prompt."""
        type_str = self.element_type.value
        text_preview = self.text[:30] + "..." if len(self.text) > 30 else self.text
        return f"[{self.id}] \"{text_preview}\" ({self.x}, {self.y}) [{type_str}]"


@dataclass
class VisionResult:
    """Standardized result from VisionEngine."""
    task: VisionTask
    success: bool
    elements: List[UIElement] = field(default_factory=list)
    summary: Optional[str] = None
    raw_output: Any = None
    screenshot_path: Optional[str] = None
    latency_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
