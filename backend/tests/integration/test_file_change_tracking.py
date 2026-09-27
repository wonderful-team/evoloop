"""Integration: 文件变更追踪全链路（真实 SQLite + 真实 FileRewind 还原）。

覆盖重构后单一写入链路的确定性闭环：
1. ``FileChangeTracker.capture → compute_and_persist`` 真实落库 FileOperation。
2. 同一次变更恰落一行（无双写）。
3. ``FileRewind`` 依据该行物理还原文件（EDIT / ADD / DELETE）。

该链路此前仅由 LLM 依赖的 e2e（test_11_rollback）覆盖且不稳定，此处用
真实测试库确定性验证。
"""

import pytest
from sqlalchemy import select

import app.models  # noqa: F401  # 注册全部模型，确保 test_session_scope create_all 建出 messages 等表
from app.core.file.changes.tracker import file_change_tracker
from app.utils.diff import diff_tracker


@pytest.fixture
def tracking_scope(test_session_scope, monkeypatch):
    """把持久化链路的 session_scope 指向测试 SQLite。"""
    import app.core.engine.message.repository as repo_mod
    import app.core.engine.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "session_scope", test_session_scope)
    monkeypatch.setattr(repo_mod, "session_scope", test_session_scope)
    return test_session_scope


@pytest.fixture
def tracking_env(tracking_scope):
    diff_tracker.clear()
    yield tracking_scope
    diff_tracker.clear()


async def _rows(scope, thread_id: str) -> list:
    from app.models import FileOperation

    async with scope() as db:
        result = await db.execute(
            select(FileOperation)
            .where(FileOperation.thread_id == thread_id)
            .order_by(FileOperation.created_at.asc())
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_edit_persists_one_row_and_rewind_restores(tmp_path, tracking_env):
    target = tmp_path / "f.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")

    file_change_tracker.capture(str(target), "t-edit")
    target.write_text("hello\npython\n", encoding="utf-8")
    await file_change_tracker.compute_and_persist(
        str(target), "t-edit", message_id="m-1", tool_call_id="call-1", run_id="r-1"
    )

    rows = await _rows(tracking_env, "t-edit")
    assert len(rows) == 1, "同一次 EDIT 必须恰好落一行（无双写）"
    op = rows[0]
    assert op.operation == "EDIT"
    assert op.original_content == "hello\nworld\n"
    assert op.diff_content

    from app.core.file.event.subscribers import FileRewind

    rewinder = FileRewind()
    count = await rewinder._revert_files(
        [
            {
                "id": op.id,
                "path": str(target),
                "operation": op.operation,
                "backup_content": op.original_content,
            }
        ]
    )
    assert count == 1
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"


@pytest.mark.asyncio
async def test_delete_persists_and_rewind_restores(tmp_path, tracking_env):
    target = tmp_path / "gone.txt"
    target.write_text("to be deleted\n", encoding="utf-8")

    file_change_tracker.capture(str(target), "t-del")
    target.unlink()
    await file_change_tracker.compute_and_persist(
        str(target), "t-del", message_id="m-2", tool_call_id="call-2", run_id="r-2"
    )

    rows = await _rows(tracking_env, "t-del")
    assert len(rows) == 1
    assert rows[0].operation == "DELETE"
    assert rows[0].original_content == "to be deleted\n"

    from app.core.file.event.subscribers import FileRewind

    count = await FileRewind()._revert_files(
        [
            {
                "id": rows[0].id,
                "path": str(target),
                "operation": "DELETE",
                "backup_content": rows[0].original_content,
            }
        ]
    )
    assert count == 1
    assert target.read_text(encoding="utf-8") == "to be deleted\n"


@pytest.mark.asyncio
async def test_add_persists_original_none(tmp_path, tracking_env):
    target = tmp_path / "new.txt"

    file_change_tracker.capture(str(target), "t-add")
    target.write_text("brand new\n", encoding="utf-8")
    await file_change_tracker.compute_and_persist(
        str(target), "t-add", message_id="m-3", tool_call_id="call-3", run_id="r-3"
    )

    rows = await _rows(tracking_env, "t-add")
    assert len(rows) == 1
    assert rows[0].operation == "ADD"
    assert rows[0].original_content is None


@pytest.mark.asyncio
async def test_persist_fires_notify_and_changeset_event(tmp_path, tracking_env, monkeypatch):
    """功能契约：嵌入式真实持久化后必须触发 SSE 细粒度通知与 ChangesetUpdatedEvent。

    锁定"重构未丢 SSE/事件"——这是此前 SSE 徽章丢失的回归防线。
    """
    import app.core.engine.tasks as tasks_mod
    from app.core.events import system_bus
    from app.core.file.event import ChangesetUpdatedEvent

    notify_calls: list[tuple] = []
    published_events: list = []

    async def _capture_notify(*args, **_kwargs):
        notify_calls.append(args)

    async def _capture_publish(event, **_kwargs):
        published_events.append(event)

    monkeypatch.setattr(tasks_mod, "_notify_file_operation", _capture_notify)
    monkeypatch.setattr(system_bus, "publish", _capture_publish)

    target = tmp_path / "f.txt"
    target.write_text("hello\n", encoding="utf-8")

    file_change_tracker.capture(str(target), "t-sse")
    target.write_text("hi\n", encoding="utf-8")
    await file_change_tracker.compute_and_persist(
        str(target), "t-sse", message_id="m-4", tool_call_id="call-4", run_id="r-4"
    )

    # 真实落库确实发生
    rows = await _rows(tracking_env, "t-sse")
    assert len(rows) == 1
    assert rows[0].operation == "EDIT"

    assert len(notify_calls) == 1, "SSE 细粒度通知必须触发一次"
    assert any(isinstance(e, ChangesetUpdatedEvent) for e in published_events), (
        "必须发布 ChangesetUpdatedEvent（侧栏变更集刷新）"
    )
