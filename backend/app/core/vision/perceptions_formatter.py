"""Perceptions formatting utilities.

Formats environment perception data (links, devices, cookies, UI elements)
for display to the agent via the core/vision/perceptions.prompt.j2 template.
"""

from app.utils.template import render_template


class PerceptionsFormatter:
    """
    Utility class for formatting environment perception/display outputs.

    Centralizes formatting logic for vision/perceptions.prompt.j2 template
    to eliminate repetitive manual list building across the codebase.

    Usage:
        from app.core.vision.perceptions_formatter import PerceptionsFormatter

        # Format links
        return PerceptionsFormatter.links(links_raw)

        # Format Android devices
        return PerceptionsFormatter.android_devices(devices)
    """

    @staticmethod
    def links(links_raw: list) -> str:
        """Format web links for display."""
        return render_template("core/vision/perceptions.prompt.j2", type="links", items=links_raw)

    @staticmethod
    def android_devices(devices: list) -> str:
        """Format Android device list for display."""
        if not devices:
            return render_template("core/vision/perceptions.prompt.j2", type="android_devices", items=[])
        items = [f"{d['serial']} ({d['status']}) {d['info']}" for d in devices]
        return render_template("core/vision/perceptions.prompt.j2", type="android_devices", items=items)

    @staticmethod
    def cookies(cookies_list: list) -> str:
        """Format browser cookies for display."""
        return render_template("core/vision/perceptions.prompt.j2", type="cookies", items=cookies_list)

    @staticmethod
    def ui_elements(elements: list, max_items: int = 50) -> str:
        """Format UI elements for display."""
        return render_template(
            "core/vision/perceptions.prompt.j2",
            type="ui_elements",
            items=elements,
            max_items=max_items,
        )
