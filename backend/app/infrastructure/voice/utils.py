"""
语音合成文本处理工具
用于清理 Markdown 格式、HTML 标签等，使 TTS 读出自然文本
"""

import re


def strip_markdown(text: str) -> str:
    """
    去除 Markdown 格式，保留纯文本

    处理以下内容：
    - **粗体** → 普通文本
    - *斜体* → 普通文本
    - `代码` → 普通文本
    - ```代码块``` → 移除或简化
    - [链接](url) → 只保留文本
    - # 标题 → 普通文本
    - - 列表 → 普通文本
    - > 引用 → 普通文本
    - --- 分割线 → 移除
    """
    if not text:
        return ""

    # 保存原始文本用于调试
    original = text

    # 1. 移除代码块 ```code```
    text = re.sub(r"```[\s\S]*?```", " ", text)

    # 2. 移除行内代码 `code`
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 3. 移除图片 ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # 4. 转换链接 [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 5. 移除粗体 **text** 或 __text__
    # 注意：要先处理粗体，再处理斜体，避免 *text* 残留在 **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)

    # 6. 移除斜体 *text* 或 _text_
    # 注意：要区分列表项 * item 和斜体 *text*
    # 斜体通常是 *text* 没有空格，列表项是 * 空格
    # 同时处理 **处理后残留的*斜体*情况
    text = re.sub(r"(?<![\*\s])\*([^*\s]+)\*(?![\*\s])", r"\1", text)
    text = re.sub(r"(?<!\s)_([^_\s]+)_(?!\s)", r"\1", text)

    # 再次处理可能残留的星号（清理边缘情况）
    # 例如: "这是 * 斜体 * 文字" → "这是 斜体 文字"
    text = re.sub(r"\s*\*\s*([^*\s]+?)\s*\*\s*", r"\1", text)

    # 7. 移除标题标记 # ## ###
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # 8. 移除引用标记 >
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    # 8.5 处理检查清单标记 - [x] 和 - [ ]
    # 先处理带列表标记的检查清单
    text = re.sub(r"^[\-\*+]\s+\[x\]\s*", "已完成", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^[\-\*+]\s+\[\s*\]\s*", "待完成", text, flags=re.MULTILINE)
    # 再处理单独的检查清单 [x] 和 [ ]
    text = re.sub(r"\[x\]\s*", "已完成", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\s*\]\s*", "待完成", text)

    # 9. 移除列表标记 - * + (行首)
    text = re.sub(r"^[\-\*+]\s+", "", text, flags=re.MULTILINE)

    # 10. 移除序号列表 1. 2. 等 (保留数字)
    text = re.sub(r"^(\d+)\.\s+", r"\1 ", text, flags=re.MULTILINE)

    # 11. 移除水平分割线 --- *** ___
    text = re.sub(r"^[\-\*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 12. 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)

    # 13. 转义字符处理
    text = text.replace("\\*", "*")
    text = text.replace("\\`", "`")
    text = text.replace("\\[", "[")
    text = text.replace("\\]", "]")

    # 14. 清理多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)  # 多个换行变成两个
    text = re.sub(r" {2,}", " ", text)  # 多个空格变成一个

    # 15. 去除首尾空白
    text = text.strip()

    return text
