"""Atlas subsystem constants.

Module-level constants that were previously scattered across Atlas logic files.
Dedicated enums (e.g. AppMapEventType) live in their own ``types.py`` modules and
are NOT re-exported here.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Surveyor
# ---------------------------------------------------------------------------
MAX_DEPTH = 12
MENUBAR_STATE_ID = "__menubar__"
RESURVEY_JACCARD_THRESHOLD = 0.8

INTERACTIVE_ROLES = {
    "AXButton",
    "AXTextField",
    "AXTextArea",
    "AXMenuItem",
    "AXMenuBarItem",
    "AXCheckBox",
    "AXRadioButton",
    "AXSlider",
    "AXPopUpButton",
    "AXComboBox",
    "AXTab",
    "AXTabGroup",
    "AXLink",
    "AXSwitch",
    "AXStepper",
    "AXSearchField",
    "AXIncrementor",
    "AXValueIndicator",
    "AXOutline",
    "AXTable",
    "AXRow",
}

# Labels that must NEVER be clicked during exploration (recorded, not triggered).
# Compiled to ACTION_BLACKLIST in surveyor.py.
ACTION_BLACKLIST_PATTERN = (
    r"quit|退出|log ?out|登出|sign out|delete|删除|清空|erase|抹掉|force quit|强制退出"
    r"|close all|全部关闭|remove|移除|trash|废纸篓|reset|重置|format|格式化"
    r"|empty|倒空|restore|还原|恢复出厂|uninstall|卸载|deactivat|注销|关机|shutdown|restart|重启"
)

# ---------------------------------------------------------------------------
# Cache keys (global cross-module keys live in app.constants)
# ---------------------------------------------------------------------------
CACHE_KEY_APP_NAME_MAP = "atlas:app_name_map"  # Hash: name -> bundle_id
CACHE_KEY_ATLAS_STRATEGIES = "atlas:strategies"

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
SCROLLABLE_CLASSES = [
    "recyclerview",
    "listview",
    "scrollview",
    "viewpager",
    "horizontalscrollview",
    "webview",
]

# ---------------------------------------------------------------------------
# AppMap source schemas
# ---------------------------------------------------------------------------
ACTION_KINDS = ("read", "write")
RISK_TIERS = ("ui", "data", "money")
SELECTOR_TYPES = ("id", "name", "class", "css", "lay-filter", "text", "data-attr")

# ---------------------------------------------------------------------------
# Native factory (macOS native macro generation)
# ---------------------------------------------------------------------------
NATIVE_NS = "native_macos"
MAX_MENU_DEPTH = 3

# Menu roots whose children are ALL dynamic content (bookmarks/history) or
# OS-level junk with badge-suffixed labels ("App Store…，9项更新").
DYNAMIC_MENU_ROOTS = {
    "apple",
    "书签",
    "bookmarks",
    "历史记录",
    "history",
    "最近使用",
    "最近使用的项目",
    "最近打开",
    "open recent",
    "recents",
    "recent items",
}

MAX_LEAF_LABEL_LEN = 30

# macOS 标准窗口平铺子菜单：每个应用内容全同 + 内部近亲对（左侧与右侧 vs
# 右侧与左侧），是跨应用路由混淆的最大来源（M4 语料实测 27 miss 中 15 条）。
# 系统级窗口管理交给系统快捷键/Agent，不出宏。
TILING_SUBMENUS = {"全屏幕拼贴", "移动与调整大小", "move & resize", "tile", "tiling"}

# Leaves never generated (destructive, irreversible).
SKIP_LEAF_PATTERN = (
    r"delete|删除|清空|erase|抹掉|format|格式化|uninstall|卸载|empty trash|倒空废纸篓"
)

# Leaves generated but gated behind user confirmation.
CONFIRM_LEAF_PATTERN = (
    r"退出|quit|close all|全部关闭|关闭所有|force quit|强制退出|注销|log ?out|sign out"
    r"|restart|重启|shutdown|关机|hide others|隐藏其他"
)

FIELD_ROLES = {"AXTextField", "AXSearchField", "AXComboBox"}
FIELD_CONTAINER_RE_PATTERN = r"AXOutline|AXTable"
ADDRESS_FIELD_RE_PATTERN = r"address|地址|搜索栏|search"

# Junk field labels observed in surveys (log-level text misread as a field).
FIELD_LABEL_STOPWORDS = {
    "error",
    "warn",
    "warning",
    "info",
    "debug",
    "fatal",
    "log",
    "错误",
    "警告",
    "日志",
}

# ---------------------------------------------------------------------------
# Skeleton generator
# ---------------------------------------------------------------------------
SKIP_TOP_DIRS = {
    "vendor",
    "node_modules",
    ".git",
    ".github",
    ".evoloop",
    "dist",
    "build",
    "out",
    "coverage",
    "htmlcov",
    "tmp",
    "temp",
    "logs",
    "cache",
    "uploads",
    "static",
    "public",
}

CATEGORY_LAYER = {
    "controller": ("entry_point", "ui"),
    "route": ("entry_point", "ui"),
    "entry_point": ("entry_point", "ui"),
    "model": ("data", "data"),
    "repository": ("data", "data"),
    "service": ("business_logic", "business"),
    "view": ("presentation", "ui"),
    "config": ("infrastructure", "system"),
    "middleware": ("infrastructure", "system"),
    "library": ("shared", "business"),
    "schema": ("data", "data"),
    "test": ("test", "system"),
    "asset": ("asset", "ui"),
    "third_party": ("third_party", "system"),
    "unknown": ("unknown", "system"),
}

APPMAP_ACTION_CATEGORIES = {
    "controller",
}
