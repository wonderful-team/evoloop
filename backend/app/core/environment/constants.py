"""
Environment Core Constants
==========================

Centralized, environment-specific constants used across the
Awakening/Environment domain. Values that are shared with other subsystems
(e.g. ``CACHE_KEY_DYNAMIC_APPS_PREFIX``) remain in ``app.constants``.
"""

from enum import Enum
from pathlib import Path

from app.constants import CACHE_KEY_DYNAMIC_APPS_PREFIX
from app.core.config import settings

# ---------------------------------------------------------------------------
# Capability boundary categories
# ---------------------------------------------------------------------------


class BoundaryCategory(str, Enum):
    """Categories of capability boundaries."""

    NETWORK = "network"
    PERMISSION = "permission"
    DEVICE = "device"
    TOOL = "tool"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Device / cache keys
# ---------------------------------------------------------------------------

CACHE_KEY_DEVICE_LOCK_PREFIX = "device:lock:"


# ---------------------------------------------------------------------------
# Mirror session
# ---------------------------------------------------------------------------

ANDROID_RECORDINGS_DIR = Path(settings.ANDROID_RECORDINGS_DIR)
MIRROR_SESSION_BATCH_SIZE = 10


# ---------------------------------------------------------------------------
# Desktop controller
# ---------------------------------------------------------------------------

MAX_OUTPUT_LENGTH = 60000

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

# System-wide shortcuts (OS level, active app independent)
SYSTEM_SHORTCUTS = {
    "切换应用": "cmd+tab",
    "switch_app": "cmd+tab",
    "Spotlight": "cmd+space",
    "spotlight": "cmd+space",
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


# ---------------------------------------------------------------------------
# Mobile controller
# ---------------------------------------------------------------------------

NOISY_PACKAGES = {
    "com.tencent.mm",
    "com.android.systemui",
    "com.android.launcher3",
    "com.google.android.inputmethod.latin",
    "android",
}


# ---------------------------------------------------------------------------
# Dynamic app explorer
# ---------------------------------------------------------------------------

CACHE_KEY_APP_REASONING_PREFIX = "system:app_categorization"
DYNAMIC_APP_TRIAGE_BATCH_SIZE = 20


# ---------------------------------------------------------------------------
# Usage ranker
# ---------------------------------------------------------------------------

# How many top apps to scan in each cycle
DEFAULT_TOP_N = 5

# Score weights
W_RECENCY = 0.5  # How recently was it used?
W_FREQUENCY = 0.3  # How much total time was spent?
W_RUNNING = 0.2  # Is it currently running?

# Maximum age in days for recency scoring (older -> score = 0)
MAX_AGE_DAYS = 30


# --- Dynamic App Triage 缓存键（explorer 与 worker 任务共用，单一事实源） ---

def processed_apps_key(platform: str) -> str:
    """已分诊应用集合（未标记者下个扫描周期会重试）。"""
    return f"system:processed_apps:{platform}"


def dynamic_apps_key(platform: str) -> str:
    """判定为动态（坐标不稳定）的应用集合。"""
    return f"{CACHE_KEY_DYNAMIC_APPS_PREFIX}:{platform}"


def app_reasoning_key(platform: str) -> str:
    """app_id -> LLM 判定理由。"""
    return f"{CACHE_KEY_APP_REASONING_PREFIX}:{platform}"
