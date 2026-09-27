"""Unit tests for ``FileChangeTracker``（capture → compute_and_persist 编排）。

验证单一写入语义：有变化恰好落一次 FileOperation，无变化 / 无快照不落。
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.file.changes.tracker import file_change_tracker
from app.utils.diff import diff_tracker


@pytest.fixture
def tracker():
    yield file_change_tracker
    diff_tracker.clear()


@pytest.fixture
def embedded():
    with patch.object(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "EMBEDDED_MODE",
        True,
    ):
        yield


async def _persist_mock(**_kwargs):
    return None


class TestEdit:
    @pytest.mark.asyncio
    async def test_edit_persists_once_with_original(self, tmp_path, tracker, embedded):
        p = tmp_path / "f.txt"
        p.write_text("hello\nworld\n")

        with patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(side_effect=_persist_mock),
        ) as mock_persist:
            tracker.capture(str(p), "t-1")
            p.write_text("hello\npython\n")
            await tracker.compute_and_persist(
                str(p), "t-1", message_id="msg-1", tool_call_id="call-1", run_id="run-1"
            )

        mock_persist.assert_awaited_once()
        kwargs = mock_persist.await_args.kwargs
        assert kwargs["operation"] == "EDIT"
        assert kwargs["original_content"] == "hello\nworld\n"
        assert kwargs["thread_id"] == "t-1"
        assert kwargs["message_id"] == "msg-1"
        assert kwargs["tool_call_id"] == "call-1"

    @pytest.mark.asyncio
    async def test_no_change_does_not_persist(self, tmp_path, tracker, embedded):
        p = tmp_path / "f.txt"
        p.write_text("same\n")

        with patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(side_effect=_persist_mock),
        ) as mock_persist:
            tracker.capture(str(p), "t-1")
            await tracker.compute_and_persist(str(p), "t-1", message_id="m-1")

        mock_persist.assert_not_awaited()


class TestAddDelete:
    @pytest.mark.asyncio
    async def test_add_persists(self, tmp_path, tracker, embedded):
        p = tmp_path / "new.txt"

        with patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(side_effect=_persist_mock),
        ) as mock_persist:
            tracker.capture(str(p), "t-1")
            p.write_text("brand new\n")
            await tracker.compute_and_persist(str(p), "t-1", message_id="m-1")

        mock_persist.assert_awaited_once()
        kwargs = mock_persist.await_args.kwargs
        assert kwargs["operation"] == "ADD"
        assert kwargs["original_content"] is None

    @pytest.mark.asyncio
    async def test_delete_persists_with_original(self, tmp_path, tracker, embedded):
        p = tmp_path / "gone.txt"
        p.write_text("to be deleted\n")

        with patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(side_effect=_persist_mock),
        ) as mock_persist:
            tracker.capture(str(p), "t-1")
            p.unlink()
            await tracker.compute_and_persist(str(p), "t-1", message_id="m-1")

        mock_persist.assert_awaited_once()
        kwargs = mock_persist.await_args.kwargs
        assert kwargs["operation"] == "DELETE"
        assert kwargs["original_content"] == "to be deleted\n"


class TestNonEmbeddedDispatch:
    """非嵌入式（Celery）路径：tracker 必须按外部契约 dispatch 正确的任务名与载荷。

    断言 ``send_task("engine_persist_file_operation", kwargs=...)`` —— 这是
    Celery worker 注册的任务契约，非内部实现细节。
    """

    @pytest.mark.asyncio
    async def test_dispatches_celery_task_with_payload(self, tmp_path):
        from unittest.mock import MagicMock

        target = tmp_path / "f.txt"
        target.write_text("before\n", encoding="utf-8")

        scheduler = MagicMock()
        with (
            patch.object(
                __import__("app.core.config", fromlist=["settings"]).settings,
                "EMBEDDED_MODE",
                False,
            ),
            patch(
                "app.infrastructure.queue.factory.get_scheduler",
                return_value=scheduler,
            ),
        ):
            file_change_tracker.capture(str(target), "t-celery")
            target.write_text("after\n", encoding="utf-8")
            await file_change_tracker.compute_and_persist(
                str(target), "t-celery", message_id="m-1", tool_call_id="call-1", run_id="r-1"
            )

        scheduler.send_task.assert_called_once()
        task_name = scheduler.send_task.call_args.args[0]
        assert task_name == "engine_persist_file_operation"
        kwargs = scheduler.send_task.call_args.kwargs["kwargs"]
        assert kwargs["thread_id"] == "t-celery"
        assert kwargs["file_path"] == str(target)
        assert kwargs["operation"] == "EDIT"
        assert kwargs["original_content"] == "before\n"
        assert kwargs["tool_call_id"] == "call-1"
        assert kwargs["run_id"] == "r-1"

    @pytest.mark.asyncio
    async def test_no_dispatch_without_change(self, tmp_path):
        from unittest.mock import MagicMock

        target = tmp_path / "f.txt"
        target.write_text("same\n", encoding="utf-8")

        scheduler = MagicMock()
        with (
            patch.object(
                __import__("app.core.config", fromlist=["settings"]).settings,
                "EMBEDDED_MODE",
                False,
            ),
            patch(
                "app.infrastructure.queue.factory.get_scheduler",
                return_value=scheduler,
            ),
        ):
            file_change_tracker.capture(str(target), "t-celery")
            await file_change_tracker.compute_and_persist(
                str(target), "t-celery", message_id="m-1"
            )

        scheduler.send_task.assert_not_called()


class TestSingleWriteSemantics:
    @pytest.mark.asyncio
    async def test_without_capture_no_persist(self, tmp_path, tracker, embedded):
        p = tmp_path / "f.txt"
        p.write_text("x\n")

        with patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(side_effect=_persist_mock),
        ) as mock_persist:
            p.write_text("y\n")
            await tracker.compute_and_persist(str(p), "t-1", message_id="m-1")

        mock_persist.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_snapshot_consumed_no_double_persist(self, tmp_path, tracker, embedded):
        """快照被消费：同一次变更只落一次（双写防护的语义保证）。"""
        p = tmp_path / "f.txt"
        p.write_text("before\n")

        with patch(
            "app.core.engine.tasks.run_persist_file_operation",
            new=AsyncMock(side_effect=_persist_mock),
        ) as mock_persist:
            tracker.capture(str(p), "t-1")
            p.write_text("after\n")
            await tracker.compute_and_persist(str(p), "t-1", message_id="m-1")
            # 第二次 compute 无快照 → 不再落库
            await tracker.compute_and_persist(str(p), "t-1", message_id="m-1")

        mock_persist.assert_awaited_once()
