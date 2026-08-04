"""Compound / multi-intent sentence detection for the routing pipeline."""

from __future__ import annotations

import re

# Sequential or additive conjunctions that usually join two distinct actions.
_SEQUENTIAL_MARKERS = re.compile(r"(?:再|然后|接着|同时|并且|并|之后|顺便|先|后)")

# Coordinating conjunctions that join two objects/verbs. These are weaker, so
# we require two action words to avoid false positives such as "发消息给张三".
_COORD_MARKERS = re.compile(r"(?:和|跟|及|还有)")

# "给" can introduce a second recipient/action (e.g. 打开微信给张三发消息).
# Only flag it when two action words are present.
_GIVE_MARKER = "给"

_ACTION_WORDS: tuple[str, ...] = (
    "打开",
    "启动",
    "关闭",
    "切换",
    "退出",
    "截图",
    "搜索",
    "查",
    "查询",
    "找",
    "写",
    "发送",
    "发",
    "播放",
    "暂停",
    "停止",
    "整理",
    "运行",
    "编译",
    "部署",
    "看",
    "听",
    "买",
    "订",
    "约",
    "分析",
    "比较",
    "记录",
    "提醒",
    "锁屏",
    "计算",
    "读取",
    "保存",
    "删除",
    "添加",
    "修改",
    "更新",
    "创建",
    "生成",
    "导出",
    "导入",
    "打印",
    "复制",
    "粘贴",
    "剪切",
    "撤销",
    "重做",
    "放大",
    "缩小",
    "滚动",
    "跳转",
    "刷新",
    "清空",
)


def _action_count(text: str) -> int:
    """Return the number of distinct action words present in ``text``."""
    return sum(1 for word in _ACTION_WORDS if word in text)


def is_compound_intent(text: str) -> bool:
    """Return True when ``text`` likely contains two or more user intents.

    The heuristic is conservative for simple single-action sentences and leans
    toward delegation when sequential markers (再/然后/接着/同时/并...) are used
    between action words.
    """
    if not text:
        return False

    if _SEQUENTIAL_MARKERS.search(text) and _action_count(text) >= 1:
        return True

    if _COORD_MARKERS.search(text) and _action_count(text) >= 2:
        return True

    if _GIVE_MARKER in text and _action_count(text) >= 2:
        return True

    return False


__all__ = ["is_compound_intent"]
