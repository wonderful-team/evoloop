"""
Android Accessibility Provider - Extract UI elements from Android UI Tree.

Uses `adb shell uiautomator dump` to get the accessibility hierarchy
and parses it into UIElement objects.
"""

import logging
import re
import xml.etree.ElementTree as ET

from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import ElementType, UIElement, VisionResult, VisionTask
from app.infrastructure.drivers.adb import ADBError, adb_driver
from app.utils.geometry import parse_bounds, Bounds

logger = logging.getLogger(__name__)


def _parse_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    """
    Parse bounds string like "[100,200][300,400]" to (x1, y1, x2, y2).
    
    Note: Delegates to app.utils.geometry.parse_bounds for the actual implementation.
    """
    bounds = parse_bounds(bounds_str)
    if bounds:
        return (bounds.x1, bounds.y1, bounds.x2, bounds.y2)
    return None


def _infer_element_type(node: ET.Element) -> ElementType:
    """Infer element type from class name and attributes."""
    class_name = node.get("class", "").lower()

    if "button" in class_name:
        return ElementType.BUTTON
    elif "edittext" in class_name or "textfield" in class_name:
        return ElementType.INPUT
    elif "checkbox" in class_name:
        return ElementType.CHECKBOX
    elif "switch" in class_name or "toggle" in class_name:
        return ElementType.SWITCH
    elif "imageview" in class_name or "image" in class_name:
        return ElementType.IMAGE
    elif "textview" in class_name:
        return ElementType.TEXT
    elif "layout" in class_name or "view" in class_name:
        return ElementType.CONTAINER
    elif "recyclerview" in class_name or "listview" in class_name:
        return ElementType.LIST_ITEM
    else:
        return ElementType.UNKNOWN


class AndroidA11yProvider(VisionProvider):
    """
    Vision provider using Android UI Automator.
    
    This is the fastest and most accurate provider for Android devices,
    as it directly reads the accessibility tree.
    """

    @property
    def name(self) -> str:
        return "android_a11y"

    @property
    def cost_factor(self) -> float:
        return 0.0  # Free - local command

    async def is_available(self) -> bool:
        """Check if an Android device is connected."""
        try:
            devices = adb_driver.list_devices()
            return any(d["status"] == "device" for d in devices)
        except ADBError:
            return False

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: str | None = None,
        **kwargs
    ) -> VisionResult:
        """
        Extract UI elements from Android UI hierarchy.
        
        Args:
            task: VisionTask (detect or analyze)
            image_source: Not used (we get fresh data from device)
            prompt: Not used
            **kwargs: May contain device_id
            
        Returns:
            VisionResult with elements
        """
        if task not in [VisionTask.DETECT, VisionTask.ANALYZE]:
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": f"Task {task} not supported by AndroidA11yProvider"}
            )

        import time
        start = time.time()
        device_id = kwargs.get("device_id")

        try:
            compressed = kwargs.get("compressed", True)
            xml_content = adb_driver.dump_ui(device_id=device_id, compressed=compressed)
        except ADBError as e:
            logger.error(f"UI dump failed: {e}")
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": str(e)}
            )

        elements = self._parse_xml(xml_content)

        latency = (time.time() - start) * 1000
        logger.info(f"[AndroidA11y] Extracted {len(elements)} elements in {latency:.0f}ms")

        return VisionResult(
            task=task,
            success=True,
            elements=elements,
            summary=f"Extracted {len(elements)} elements from Android UI tree.",
            screenshot_path=image_source,
            latency_ms=latency,
        )

    def _parse_xml(self, xml_content: str) -> list[UIElement]:
        """Parse UI hierarchy XML into UIElement list."""
        elements = []
        element_id = 0

        # Clean up XML: some ADB versions append extra text to the stream
        if not xml_content or not xml_content.strip():
            return []

        # Find the actual XML root
        xml_start = xml_content.find("<?xml")
        if xml_start == -1:
            xml_start = xml_content.find("<hierarchy")

        if xml_start >= 0:
            # Also find the end of the root element to strip trailing junk
            xml_end = xml_content.rfind(">")
            if xml_end > xml_start:
                xml_content = xml_content[xml_start : xml_end + 1]

        try:
            root = ET.fromstring(xml_content.strip())
        except ET.ParseError as e:
            logger.error(f"XML parse error (content preview: {xml_content[:100]}...): {e}")
            return []

        for node in root.iter():
            # Skip container nodes without meaningful content
            text = node.get("text", "") or node.get("content-desc", "")
            clickable = node.get("clickable") == "true"
            focusable = node.get("focusable") == "true"

            # Only include interactive elements or elements with text
            if not (text or clickable or focusable):
                continue

            bounds_str = node.get("bounds", "")
            bounds = _parse_bounds(bounds_str)

            if not bounds:
                continue

            x1, y1, x2, y2 = bounds
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            width = x2 - x1
            height = y2 - y1

            # Skip very small elements (likely invisible)
            if width < 10 or height < 10:
                continue

            # Enhanced metadata for element classification
            scrollable = node.get("scrollable") == "true"
            checkable = node.get("checkable") == "true"
            checked = node.get("checked") == "true"
            selected = node.get("selected") == "true"

            element = UIElement(
                id=element_id,
                text=text,
                x=center_x,
                y=center_y,
                width=width,
                height=height,
                element_type=_infer_element_type(node),
                clickable=clickable,
                confidence=1.0,
                source=self.name,
                metadata={
                    "class": node.get("class", ""),
                    "resource_id": node.get("resource-id", ""),
                    "package": node.get("package", ""),
                    # Additional attributes for element classification
                    "scrollable": scrollable,
                    "checkable": checkable,
                    "checked": checked,
                    "focusable": focusable,
                    "selected": selected,
                    "content_desc": node.get("content-desc", ""),
                    "index": node.get("index", ""),
                }
            )

            elements.append(element)
            element_id += 1

        return elements


# Singleton
android_a11y_provider = AndroidA11yProvider()
