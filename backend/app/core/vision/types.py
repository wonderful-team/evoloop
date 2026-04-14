from enum import Enum
from typing import Any, List, Optional, Tuple

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ElementType(str, Enum):
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


class VisionTask(str, Enum):
    """Types of vision tasks."""
    OCR = "ocr"             # Text extraction
    DETECT = "detect"       # Object/Element detection
    CAPTION = "caption"     # Image description
    ANALYZE = "analyze"     # Detailed UI analysis
    COMPARE = "compare"     # Screenshot comparison


class NativeAttributes(DynamicBaseModel):
    pass


class UIMetadata(DynamicBaseModel):
    provider: str | None = None
    ocr_confidence: float | None = None
    native_attrs: NativeAttributes = Field(default_factory=NativeAttributes)


class VisionMetadata(DynamicBaseModel):
    provider: str | None = None
    model_version: str | None = None
    latency_breakdown: dict[str, float] = Field(default_factory=dict)


class UIElement(DynamicBaseModel):
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
    metadata: UIMetadata = Field(default_factory=UIMetadata)

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
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


class VisionResult(DynamicBaseModel):
    """Standardized result from VisionEngine."""
    task: VisionTask
    success: bool
    elements: List[UIElement] = Field(default_factory=list)
    summary: Optional[str] = None
    raw_output: Any = None
    screenshot_path: Optional[str] = None
    latency_ms: float = 0
    metadata: VisionMetadata = Field(default_factory=VisionMetadata)
