"""文件变更追踪（单一职责基础设施）。

负责"快照 → 计算 diff → 落库 FileOperation"的统一链路，不感知任何具体工具名。
路径来源由各工具自行声明（``affected_path_keys`` / ``affected_path_extractor``），
经 ``app.core.tools.registry.get_tool_affected_paths`` 内省获得。
"""

from app.core.file.changes.diff import FileDiff, compute_file_diff
from app.core.file.changes.tracker import FileChangeTracker, file_change_tracker

__all__ = [
    "FileDiff",
    "compute_file_diff",
    "FileChangeTracker",
    "file_change_tracker",
]
