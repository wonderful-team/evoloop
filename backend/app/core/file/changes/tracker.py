"""FileChangeTracker — 文件变更追踪唯一入口（执行编排器调用）。

职责：执行前 capture（记录 before 内容）→ 执行后 compute_and_persist
（计算统一 diff → 落库 FileOperation）。不感知任何具体工具名，路径由
``get_tool_affected_paths`` 提供。

快照后端当前为进程内存（``app.utils.diff.DiffTracker``，Q4 观察期）；后续
可替换为 Redis/DB 而不改动本模块调用方。
"""

import logging
import os

from app.core.config import settings
from app.core.file.changes.diff import FileDiff, compute_file_diff
from app.utils.diff import diff_tracker

logger = logging.getLogger(__name__)


class FileChangeTracker:
    """文件变更追踪编排器（无状态，内部复用模块级快照后端）。"""

    def has_snapshot(self, path: str, thread_id: str) -> bool:
        return diff_tracker.has_snapshot(path, thread_id)

    def capture(self, path: str, thread_id: str) -> None:
        """执行前记录文件 before 内容（供执行后计算 diff）。"""
        diff_tracker.capture_snapshot(path, thread_id)

    def discard(self, path: str, thread_id: str) -> None:
        """丢弃某个快照（执行失败/中断时清理，避免内存泄漏与陈旧快照复用）。"""
        diff_tracker.drop_snapshot(path, thread_id)

    async def compute_and_persist(
        self,
        path: str,
        thread_id: str,
        message_id: str,
        tool_call_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """执行后：计算 diff，有变化则落库 FileOperation；无变化不落。

        ``message_id`` 用于关联消息徽章；``tool_call_id`` 供落库时反查真实消息。
        """
        before = diff_tracker.get_snapshot(path, thread_id)
        if before is None:
            return
        diff_tracker.drop_snapshot(path, thread_id)

        if os.path.isdir(path):
            return

        try:
            with open(path, encoding="utf-8") as f:
                after = f.read()
        except FileNotFoundError:
            after = ""
        except OSError as e:
            logger.warning(f"[FileChangeTracker] Failed to read {path}: {e}", exc_info=True)
            return

        result = compute_file_diff(before, after, path)
        if not result.operation:
            return
        await self._persist(path, thread_id, message_id, tool_call_id, run_id, result)

    async def _persist(
        self,
        path: str,
        thread_id: str,
        message_id: str,
        tool_call_id: str | None,
        run_id: str | None,
        result: FileDiff,
    ) -> None:
        kwargs = {
            "thread_id": thread_id,
            "message_id": str(message_id),
            "file_path": path,
            "operation": result.operation,
            "diff_content": result.diff,
            "original_content": result.original,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
        }
        if settings.EMBEDDED_MODE:
            # 嵌入式：直接 await 完整持久化协程（落库 + SSE 徽章 + 变更集事件），
            # 进程内确定性完成。不能 await Huey 包装的任务——它返回 Result 而非
            # 协程（历史 executor 路径曾因此静默失败，被宽泛 except 吞掉）。
            from app.core.engine.tasks import _run_persist_file_operation

            await _run_persist_file_operation(**kwargs)
        else:
            from app.infrastructure.queue.factory import get_scheduler

            get_scheduler().send_task(
                "engine_persist_file_operation",
                kwargs=kwargs,
            )
        logger.info(f"[FileChangeTracker] Persisted file operation ({result.operation}) for {path}")


#: 模块级单例（无状态，复用共享快照后端）
file_change_tracker = FileChangeTracker()
