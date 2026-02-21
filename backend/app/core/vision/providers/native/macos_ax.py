"""
MacOS Accessibility Provider - Extract UI elements from Mac applications.

Uses AppleScript to query the System Events accessibility tree
and parses it into UIElement objects.
"""

import logging
import ast
import time
from typing import Any, Optional

from app.infrastructure.drivers.macos import macos_driver
from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import ElementType, UIElement, VisionResult, VisionTask

logger = logging.getLogger(__name__)


def _infer_element_type(role: str) -> ElementType:
    """Infer element type from AX role."""
    role = role.lower()
    
    if "button" in role:
        return ElementType.BUTTON
    elif "text field" in role or "search field" in role:
        return ElementType.INPUT
    elif "check box" in role:
        return ElementType.CHECKBOX
    elif "switch" in role:
        return ElementType.SWITCH
    elif "image" in role:
        return ElementType.IMAGE
    elif "static text" in role:
        return ElementType.TEXT
    elif "list item" in role:
        return ElementType.LIST_ITEM
    elif "group" in role or "window" in role:
        return ElementType.CONTAINER
    else:
        return ElementType.UNKNOWN


class MacOSAxProvider(VisionProvider):
    """
    Vision provider using MacOS Accessibility via AppleScript.
    """
    
    @property
    def name(self) -> str:
        return "macos_ax"
    
    @property
    def cost_factor(self) -> float:
        return 0.0
    
    async def is_available(self) -> bool:
        """Check if accessibility permissions are granted."""
        return macos_driver.check_accessibility_permission()
    
    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VisionResult:
        """
        Extract UI elements from the frontmost Mac application.
        """
        if task not in [VisionTask.DETECT, VisionTask.ANALYZE]:
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": f"Task {task} not supported by MacOSAxProvider"}
            )
            
        start = time.time()
        
        ax_output = macos_driver.dump_ax_tree()
        if ax_output.startswith("Error"):
            logger.error(f"MacOS AX dump failed: {ax_output}")
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": ax_output}
            )
        
        elements = self._parse_ax_output(ax_output)
        
        latency = (time.time() - start) * 1000
        logger.info(f"[MacOSAx] Extracted {len(elements)} elements in {latency:.0f}ms")
        
        return VisionResult(
            task=task,
            success=True,
            elements=elements,
            summary=f"Extracted {len(elements)} elements from macOS Accessibility tree.",
            screenshot_path=image_source,
            latency_ms=latency,
        )
    
    def _parse_ax_output(self, ax_output: str) -> list[UIElement]:
        """Parse AX tree output into UIElement list."""
        elements = []
        
        # The output is a string like "[{...}, {...}]" using single quotes
        # We can use ast.literal_eval safely for this structured string
        try:
            # Clean up potential "missing value" in AppleScript output
            cleaned_output = ax_output.replace("missing value", "None")
            raw_elements = ast.literal_eval(cleaned_output)
        except Exception as e:
            logger.error(f"Failed to parse MacOS AX output: {e}\nOutput: {ax_output[:200]}")
            return []
            
        for i, raw in enumerate(raw_elements):
            name = raw.get("name")
            if name is None or name == "None":
                 name = ""
                 
            # bounds: [x, y, width, height]
            bounds = raw.get("bounds", [0, 0, 0, 0])
            if len(bounds) != 4:
                continue
                
            x, y, w, h = bounds
            
            # Skip invisible or empty elements
            if w <= 0 or h <= 0:
                continue
                
            element = UIElement(
                id=i,
                text=name,
                x=x + w // 2,
                y=y + h // 2,
                width=w,
                height=h,
                element_type=_infer_element_type(raw.get("role", "")),
                clickable=True, # In Ax Tree, most elements we list are interactive or useful
                confidence=1.0,
                source=self.name,
                metadata={
                    "role": raw.get("role", ""),
                }
            )
            elements.append(element)
            
        return elements


# Singleton
macos_ax_provider = MacOSAxProvider()
