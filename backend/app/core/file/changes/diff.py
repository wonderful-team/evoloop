"""统一文件变更 diff 计算（文件变更追踪基础设施）。

收敛两套历史 diff 实现：
- ``app.core.file.editor.algorithms.generate_unified_diff``（context=3、末行换行修正）
- ``app.utils.diff.DiffTracker.compute_diff``（ADD/EDIT/DELETE 判定 + original 提取）

本模块对外提供唯一口径 ``compute_file_diff``，供变更追踪、rewind 备份共用。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileDiff:
    """一次文件变更的完整描述（operation + diff + 还原备份）。"""

    operation: str  # "ADD" | "EDIT" | "DELETE"
    diff: str  # unified diff 文本（无变化为空串）
    original: str | None  # 变更前内容：ADD=None；EDIT/DELETE=原文


def _split_with_newline_fix(text: str) -> list[str]:
    """按行切分并修正末行换行，保证 unified diff 头正确。

    与 ``generate_unified_diff`` 的既有行为保持一致。
    """
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return lines


def compute_file_diff(
    before: str,
    after: str,
    file_path: str = "file",
    context_lines: int = 3,
) -> FileDiff:
    """计算文件变更。

    Args:
        before: 变更前内容（新增文件传 ""）
        after: 变更后内容（删除文件传 ""）
        file_path: 用于 diff 头的路径标签
        context_lines: unified diff 上下文行数（默认 3）

    Returns:
        ``FileDiff``：
        - ``operation``：ADD（前空后非空）/ DELETE（前非空后空）/ EDIT
        - ``diff``：unified diff 文本；无变化为空串
        - ``original``：变更前内容；ADD 时为 None，EDIT/DELETE 为 before
    """
    if before == after:
        return FileDiff(operation="", diff="", original=None)

    if not before and after:
        operation = "ADD"
    elif before and not after:
        operation = "DELETE"
    else:
        operation = "EDIT"

    before_lines = _split_with_newline_fix(before)
    after_lines = _split_with_newline_fix(after)

    import difflib

    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )
    diff_text = "".join(diff)

    original = before if operation in ("EDIT", "DELETE") else None
    return FileDiff(operation=operation, diff=diff_text, original=original)
