"""
Quick Shortcuts Database - High-frequency app shortcuts for fast execution

Purpose: Convert common UI actions to keyboard shortcuts automatically
Example: click("发送") → key_press("cmd+return")
"""

from app.core.environment.constants import (
    GENERIC_SHORTCUTS,
    SHORTCUTS,
    SYSTEM_SHORTCUTS,
)


def get_shortcut(bundle_id: str, element_name: str) -> str | None:
    """
    Get keyboard shortcut for an element.

    Args:
        bundle_id: App bundle identifier (e.g., "com.tencent.xinWeChat")
        element_name: UI element name/label (e.g., "发送", "close")

    Returns:
        Shortcut string like "cmd+return" or None

    Examples:
        >>> get_shortcut("com.tencent.xinWeChat", "发送")
        'return'
        >>> get_shortcut("com.google.Chrome", "新标签")
        'cmd+t'
    """
    # Normalize input
    element_key = element_name.lower().replace(" ", "_")

    # 1. Check app-specific shortcuts
    if bundle_id in SHORTCUTS:
        app_shortcuts = SHORTCUTS[bundle_id]
        if shortcut := app_shortcuts.get(element_name):
            return shortcut
        if shortcut := app_shortcuts.get(element_key):
            return shortcut

    # 2. Check generic shortcuts
    if shortcut := GENERIC_SHORTCUTS.get(element_name):
        return shortcut
    if shortcut := GENERIC_SHORTCUTS.get(element_key):
        return shortcut

    # 3. Check system-wide shortcuts (OS level, active app independent)
    if shortcut := SYSTEM_SHORTCUTS.get(element_name):
        return shortcut
    if shortcut := SYSTEM_SHORTCUTS.get(element_key):
        return shortcut

    return None
