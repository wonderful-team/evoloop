import logging

from app.core.environment.schemas import DehydratedElement
from app.infrastructure.vision.providers.native.android_a11y import (
    android_a11y_provider,
)

logger = logging.getLogger(__name__)


class AndroidService:
    """
    High-level services for Android environment awareness.
    """

    @staticmethod
    async def dehydrate_layout(xml_content: str) -> tuple[list[DehydratedElement], str]:
        """
        Processes raw Android XML layout into a dehydrated list of interactive elements.
        Uses AndroidA11yProvider for robust XML parsing and element extraction.
        """
        if not xml_content or not xml_content.strip():
            return [], "Empty layout."

        # Use the provider's internal parse method to avoid re-implementing
        # bounds parsing and coordinate calculation.
        elements = android_a11y_provider._parse_xml(xml_content)

        dehydrated: list[DehydratedElement] = []
        for el in elements:
            # Map UIElement to the dehydrated model format used by harvesting tasks
            dehydrated.append(
                DehydratedElement(
                    id=el.id,
                    text=el.text,
                    x=el.x,
                    y=el.y,
                    width=el.width,
                    height=el.height,
                    clickable=el.clickable,
                    scrollable=el.metadata.get("scrollable", False),
                    package=el.metadata.get("package", ""),
                    class_=el.metadata.get("class", ""),
                    resource_id=el.metadata.get("resource_id", ""),
                )
            )

        summary = f"Dehydrated layout with {len(dehydrated)} interactive elements."
        return dehydrated, summary


android_service = AndroidService()
