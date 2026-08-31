"""Unified tool-output truncation for the React engine (OpenCode `tool/truncate.ts` semantic).

超限的工具输出在写回消息流之前被自动折叠：
- 行数（MAX_LINES）与字节数（MAX_BYTES）任一超限即截断；
- 支持 ``direction``：head（保留开头）| tail（保留结尾）；
- 完整内容落盘到 ``~/.evoloop/artifacts/truncated/``，返回 preview + ``outputPath``
  （模型可用 read 工具读取全文，或用 task 让 explore 子代理处理大文件）；
- 阈值可由配置 ``TOOL_OUTPUT_MAX_LINES`` / ``TOOL_OUTPUT_MAX_BYTES`` 覆盖。

工具作者无需关心截断——由 executor 统一调用本模块。
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

#: 触发截断的默认阈值（对齐 OpenCode MAX_LINES=2000 / MAX_BYTES=50KB）
DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 32000


@dataclass(frozen=True)
class TruncateResult:
    content: str
    truncated: bool
    output_path: str | None = None


def _truncated_dir() -> str:
    path = os.path.join(settings.APP_DATA_DIR, "artifacts", "truncated")
    os.makedirs(path, exist_ok=True)
    return path


def _write_artifact(content: str, thread_id: str | None = None) -> str:
    name = f"{thread_id or 'agent'}-{uuid.uuid4().hex[:12]}.txt"
    path = os.path.join(_truncated_dir(), name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def truncation_limits() -> tuple[int, int]:
    """返回 (max_lines, max_bytes)，可由配置覆盖。"""
    max_lines = getattr(settings, "TOOL_OUTPUT_MAX_LINES", None) or DEFAULT_MAX_LINES
    max_bytes = getattr(settings, "TOOL_OUTPUT_MAX_BYTES", None) or DEFAULT_MAX_BYTES
    return int(max_lines), int(max_bytes)


def _build_hint(output_path: str, task_tool_enabled: bool = False) -> str:
    if task_tool_enabled:
        return (
            f"完整输出已保存到: {output_path}\n"
            "大文件请用 task 工具让 explore 子代理用 grep/read(offset/limit) 处理，"
            "不要自己读全文以节省上下文。"
        )
    return (
        f"完整输出已保存到: {output_path}\n"
        "可用 read 分段（start_line/end_line）查看，或 grep 检索关键词。"
    )


def truncate_output(
    output: str,
    *,
    max_lines: int | None = None,
    max_bytes: int | None = None,
    direction: str = "head",
    thread_id: str | None = None,
    task_tool_enabled: bool = False,
) -> TruncateResult:
    """截断超限输出；未超限时原样返回（零开销）。

    ``direction``: "head" 保留开头 | "tail" 保留结尾（OpenCode 语义）。
    """
    if not output:
        return TruncateResult(content=output, truncated=False)

    resolved_lines, resolved_bytes = truncation_limits()
    max_lines = int(max_lines or resolved_lines)
    max_bytes = int(max_bytes or resolved_bytes)

    lines = output.split("\n")
    total_bytes = len(output.encode("utf-8"))

    if len(lines) <= max_lines and total_bytes <= max_bytes:
        return TruncateResult(content=output, truncated=False)

    # 按行 + 字节裁剪 preview
    out_lines: list[str] = []
    bytes_used = 0
    if direction == "head":
        iterator = range(min(len(lines), max_lines))
        for i in iterator:
            size = len(lines[i].encode("utf-8")) + (1 if i > 0 else 0)
            if bytes_used + size > max_bytes:
                break
            out_lines.append(lines[i])
            bytes_used += size
    else:  # tail
        for i in range(len(lines) - 1, -1, -1):
            if len(out_lines) >= max_lines:
                break
            size = len(lines[i].encode("utf-8")) + (1 if out_lines else 0)
            if bytes_used + size > max_bytes:
                break
            out_lines.insert(0, lines[i])
            bytes_used += size

    # 单行本身超字节预算时，仍保留该行开头/结尾的一部分（模型能看到头部结论）
    if not out_lines and lines:
        if direction == "head":
            out_lines = [lines[0][:max_bytes]]
        else:
            out_lines = [lines[-1][-max_bytes:]]

    removed = len(lines) - len(out_lines)
    path = _write_artifact(output, thread_id)
    hint = _build_hint(path, task_tool_enabled)
    preview = "\n".join(out_lines)

    if direction == "head":
        content = f"{preview}\n\n...[TRUNCATED] {removed} lines truncated...\n\n{hint}"
    else:
        content = f"...[TRUNCATED] {removed} lines truncated...\n\n{hint}\n\n{preview}"

    return TruncateResult(content=content, truncated=True, output_path=path)


def summarize_output(output: Any, thread_id: str | None = None) -> TruncateResult:
    """对非字符串输出（dict/BaseModel 等）先序列化再截断。"""
    if not isinstance(output, str):
        try:
            output = str(output)
        except Exception:
            output = repr(output)
    return truncate_output(output, thread_id=thread_id)
