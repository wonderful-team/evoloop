"""PromptLoader — pure-text `.txt` prompt loading with placeholder substitution.

对齐 OpenCode：提示词是纯文本 `.txt` 文件，无 Jinja2 / 无 str.format。
动态内容由代码层组装后，经本模块的显式占位符表替换。

⚠ 禁止使用 `str.format` / f-string 渲染模板：提示词正文必然含 JSON/代码
示例的花括号，format 会抛 KeyError。本模块只做「文件读取缓存 + 占位符替换」。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

_CONFIG_TEMPLATE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "templates")
)


@lru_cache(maxsize=256)
def read_prompt(relative_path: str) -> str:
    """读取模板目录下的文本文件（缓存）。路径如 "core/agent/main.txt"。"""
    full = os.path.join(_CONFIG_TEMPLATE_DIR, relative_path)
    with open(full, encoding="utf-8") as f:
        return f.read()


def render_prompt(relative_path: str, placeholders: dict[str, Any] | None = None) -> str:
    """读取 `.txt` 提示词并替换显式占位符。

    占位符形如 ``{{name}}``，仅做精确字符串替换；缺失占位符原样保留
    （便于发现模板里遗漏的占位符，不做隐式填充）。
    """
    text = read_prompt(relative_path)
    if not placeholders:
        return text
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def prompt_exists(relative_path: str) -> bool:
    return os.path.exists(os.path.join(_CONFIG_TEMPLATE_DIR, relative_path))
