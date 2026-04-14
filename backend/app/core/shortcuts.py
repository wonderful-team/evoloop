"""
Quick Shortcuts Database - High-frequency app shortcuts for fast execution

Purpose: Convert common UI actions to keyboard shortcuts automatically
Example: click("发送") → key_press("cmd+return")
"""

# High-frequency apps - manual curation for accuracy
SHORTCUTS = {
    # WeChat
    "com.tencent.xinWeChat": {
        "发送": "return",
        "send": "return",
        "搜索": "cmd+f",
        "search": "cmd+f",
        "新建聊天": "cmd+n",
        "new_chat": "cmd+n",
        "切换聊天": "cmd+]",
        "下一个聊天": "cmd+]",
        "上一个聊天": "cmd+[",
        "关闭": "cmd+w",
        "close": "cmd+w",
    },

    # Chrome / Chromium
    "com.google.Chrome": {
        "地址栏": "cmd+l",
        "address_bar": "cmd+l",
        "新标签": "cmd+t",
        "new_tab": "cmd+t",
        "关闭标签": "cmd+w",
        "close_tab": "cmd+w",
        "刷新": "cmd+r",
        "refresh": "cmd+r",
        "查找": "cmd+f",
        "find": "cmd+f",
        "下一个匹配": "cmd+g",
        "上一个匹配": "cmd+shift+g",
        "全选": "cmd+a",
        "复制": "cmd+c",
        "粘贴": "cmd+v",
    },

    # Safari
    "com.apple.Safari": {
        "地址栏": "cmd+l",
        "新标签": "cmd+t",
        "关闭标签": "cmd+w",
        "刷新": "cmd+r",
        "查找": "cmd+f",
    },

    # System / Finder
    "com.apple.finder": {
        "新建文件夹": "cmd+shift+n",
        "new_folder": "cmd+shift+n",
        "全选": "cmd+a",
        "复制": "cmd+c",
        "粘贴": "cmd+v",
        "剪切": "cmd+x",
        "删除": "cmd+delete",
        "搜索": "cmd+f",
    },

    # Notes
    "com.apple.Notes": {
        "新建": "cmd+n",
        "删除": "cmd+delete",
        "搜索": "cmd+f",
    },

    # Terminal
    "com.apple.Terminal": {
        "新建窗口": "cmd+n",
        "新建标签": "cmd+t",
        "复制": "cmd+c",
        "粘贴": "cmd+v",
        "全选": "cmd+a",
        "清屏": "cmd+k",
    },
}

# Generic shortcuts that work in most apps
GENERIC_SHORTCUTS = {
    "复制": "cmd+c",
    "copy": "cmd+c",
    "粘贴": "cmd+v",
    "paste": "cmd+v",
    "剪切": "cmd+x",
    "cut": "cmd+x",
    "全选": "cmd+a",
    "select_all": "cmd+a",
    "撤销": "cmd+z",
    "undo": "cmd+z",
    "重做": "cmd+shift+z",
    "redo": "cmd+shift+z",
    "保存": "cmd+s",
    "save": "cmd+s",
    "关闭": "cmd+w",
    "close": "cmd+w",
    "退出": "cmd+q",
    "quit": "cmd+q",
    "打印": "cmd+p",
    "print": "cmd+p",
    "查找": "cmd+f",
    "search": "cmd+f",
    "新建": "cmd+n",
    "new": "cmd+n",
}


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
        "cmd+return"
        >>> get_shortcut("com.google.Chrome", "新标签")
        "cmd+t"
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

    return None


def has_shortcut(bundle_id: str, element_name: str) -> bool:
    """Check if an element has a known shortcut."""
    return get_shortcut(bundle_id, element_name) is not None


def list_app_shortcuts(bundle_id: str) -> dict:
    """List all known shortcuts for an app."""
    app_specific = SHORTCUTS.get(bundle_id, {})
    return {**GENERIC_SHORTCUTS, **app_specific}
