"""
Perception Layer - Base interfaces and data structures.

This module defines the core abstractions for UI element perception,
enabling fusion of multiple perception sources (UI Tree, OCR, Vision).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


@dataclass
class UIElement:
    """
    Represents a detected UI element on screen.
    
    This is the core data structure passed between perception providers
    and the decision layer.
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
    source: str = ""  # "ui_tree", "ocr", "vision"
    metadata: dict = field(default_factory=dict)
    
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
class PerceptionResult:
    """Result from a perception provider."""
    elements: list[UIElement]
    screenshot_path: str | None = None
    source: str = ""
    latency_ms: float = 0
    metadata: dict = field(default_factory=dict)


class PerceptionProvider(ABC):
    """
    Abstract base class for perception providers.
    
    Each provider implements a different way to extract UI elements:
    - AndroidA11yProvider: Uses UI Automator dump
    - MacOSA11yProvider: Uses Accessibility API
    - OCRProvider: Uses OCR for text detection
    - VisionProvider: Uses VLM for understanding
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging/debugging."""
        pass
    
    @property
    @abstractmethod
    def cost(self) -> float:
        """Relative cost (0 = free, 1 = expensive)."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider can be used in current context."""
        pass
    
    @abstractmethod
    async def extract(
        self,
        screenshot_path: str | None = None,
        device_id: str | None = None,
    ) -> PerceptionResult:
        """
        Extract UI elements from the current screen.
        
        Args:
            screenshot_path: Path to screenshot (for OCR/Vision providers)
            device_id: Device identifier (for mobile providers)
            
        Returns:
            PerceptionResult with detected elements
        """
        pass
