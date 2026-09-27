"""Integration: 真实 Agent 执行路径的变更追踪契约测试。

不 mock 任何内部持久化符号，走真实公共路径：
真实 ``AgentToolExecutor`` + 真实 edit/write/delete 工具 + 真实持久化
+ 真实 ``FileRewind`` 还原。仅断言可观察结果（功能契约）：

- 工具确实改了文件；
- 恰好落一行 ``FileOperation``（operation / original / diff 正确，无双写）；
- ``FileRewind`` 依据记录物理还原。

这是对"重构是否丢功能"的行为级验证（区别于贴合内部结构的单测）。
"""

import uuid

import pytest
from sqlalchemy import select

import app.models  # noqa: F401  # 注册全部模型，确保测试库建出 messages 等表
from app.core.context.manager import ContextManager, EvoContext
from app.core.engine.state.base import AgentState
from app.core.engine.tools.executor import AgentToolExecutor
from app.core.tools.registry import get_tool_map
from app.utils.diff import diff_tracker


@pytest.fixture
def real_scope(test_session_scope, monkeypatch):
    """把持久化链路（tasks / message repository）的 session_scope 指向测试库。"""
    import app.core.engine.message.repository as repo_mod
    import app.core.engine.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "session_scope", test_session_scope)
    monkeypatch.setattr(repo_mod, "session_scope", test_session_scope)
    return test_session_scope


@pytest.fixture
def real_env(real_scope):
    diff_tracker.clear()
    yield real_scope
    diff_tracker.clear()


async def _run_tool(workdir: str, thread_id: str, tool_name: str, args: dict, tool_call_id: str) -> None:
    """用真实 executor 执行真实工具（真实改文件 + 真实持久化）。"""
    ctx = EvoContext(
        thread_id=thread_id,
        project_id=1,
        run_id=f"r-{thread_id}",
        current_tool_call_id=tool_call_id,
    )
    token = ContextManager.set(ctx)
    try:
        config = {
            "configurable": {
                "thread_id": thread_id,
                "run_id": f"r-{thread_id}",
                "working_directory": workdir,
            },
            "metadata": {"project_id": 1},
        }
        executor = AgentToolExecutor(
            tool_map={tool_name: get_tool_map()[tool_name]},
            state=AgentState(),
            config=config,
        )
        await executor.execute_tool(tool_name, args, tool_call_id, [])
    finally:
        ContextManager.reset(token)


async def _rows(scope, thread_id: str) -> list:
    from app.models import FileOperation

    async with scope() as db:
        result = await db.execute(
            select(FileOperation).where(FileOperation.thread_id == thread_id)
        )
        return list(result.scalars().all())


async def _revert_one(op) -> int:
    from app.core.file.event.subscribers import FileRewind

    return await FileRewind()._revert_files(
        [
            {
                "id": op.id,
                "path": op.file_path,
                "operation": op.operation,
                "backup_content": op.original_content,
            }
        ]
    )


@pytest.mark.asyncio
async def test_edit_file_persists_once_and_rewinds(real_env, tmp_path):
    tid = f"t-{uuid.uuid4().hex[:8]}"
    workdir = tmp_path / "w"
    workdir.mkdir()
    target = workdir / "f.txt"
    target.write_text("hello\n", encoding="utf-8")

    await _run_tool(
        str(workdir), tid, "edit",
        {"path": "f.txt", "target": "hello", "replacement": "hi"},
        "call-1",
    )

    assert target.read_text(encoding="utf-8") == "hi\n"
    rows = await _rows(real_env, tid)
    assert len(rows) == 1, "真实 edit 必须恰好落一行 FileOperation（无双写）"
    assert rows[0].operation == "EDIT"
    assert rows[0].original_content == "hello\n"
    assert rows[0].diff_content

    assert await _revert_one(rows[0]) == 1
    assert target.read_text(encoding="utf-8") == "hello\n"


@pytest.mark.asyncio
async def test_write_file_add_persists_once(real_env, tmp_path):
    tid = f"t-{uuid.uuid4().hex[:8]}"
    workdir = tmp_path / "w"
    workdir.mkdir()
    target = workdir / "new.txt"

    await _run_tool(
        str(workdir), tid, "write",
        {"path": "new.txt", "content": "brand new\n"},
        "call-2",
    )

    assert target.read_text(encoding="utf-8") == "brand new\n"
    rows = await _rows(real_env, tid)
    assert len(rows) == 1
    assert rows[0].operation == "ADD"
    assert rows[0].original_content is None


@pytest.mark.asyncio
async def test_move_file_persists_delete_source_add_dest(real_env, tmp_path):
    tid = f"t-{uuid.uuid4().hex[:8]}"
    workdir = tmp_path / "w"
    workdir.mkdir()
    (workdir / "a.txt").write_text("aaa\n", encoding="utf-8")

    await _run_tool(
        str(workdir), tid, "move_file",
        {"source": "a.txt", "destination": "b.txt"},
        "call-mv",
    )

    assert (workdir / "b.txt").read_text(encoding="utf-8") == "aaa\n"
    assert not (workdir / "a.txt").exists()
    rows = await _rows(real_env, tid)
    ops = {r.operation: r.file_path for r in rows}
    assert "DELETE" in ops and ops["DELETE"].endswith("a.txt")
    assert "ADD" in ops and ops["ADD"].endswith("b.txt")
    assert rows[0].original_content == "aaa\n"


@pytest.mark.asyncio
async def test_delete_file_persists_once_and_rewinds(real_env, tmp_path):
    tid = f"t-{uuid.uuid4().hex[:8]}"
    workdir = tmp_path / "w"
    workdir.mkdir()
    target = workdir / "del.txt"
    target.write_text("bye\n", encoding="utf-8")

    await _run_tool(
        str(workdir), tid, "delete_file",
        {"path": "del.txt", "confirm": True},
        "call-3",
    )

    assert not target.exists()
    rows = await _rows(real_env, tid)
    assert len(rows) == 1
    assert rows[0].operation == "DELETE"
    assert rows[0].original_content == "bye\n"

    assert await _revert_one(rows[0]) == 1
    assert target.read_text(encoding="utf-8") == "bye\n"


@pytest.mark.asyncio
async def test_changeset_reference_attached_to_message(real_env, tmp_path):
    """消息徽章契约：真实 edit 落库后，对应 tool 消息须挂上 changeset 引用。"""
    from app.models import FileOperation, Message, MessageReference

    tid = f"t-{uuid.uuid4().hex[:8]}"
    workdir = tmp_path / "w"
    workdir.mkdir()
    target = workdir / "f.txt"
    target.write_text("hello\n", encoding="utf-8")

    # 预创建 tool 消息（携带 tool_call_id），真实持久化会解析并挂 changeset 徽章
    async with real_env() as db:
        msg = Message(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            thread_id=tid,
            role="tool",
            content="edit output",
            tool_call_id="call-badge",
            sequence_number=1,
            category="tool_output",
        )
        db.add(msg)
        await db.flush()
        msg_id = msg.id

    await _run_tool(
        str(workdir), tid, "edit",
        {"path": "f.txt", "target": "hello", "replacement": "hi"},
        "call-badge",
    )

    async with real_env() as db:
        ops = (
            (await db.execute(select(FileOperation).where(FileOperation.thread_id == tid)))
            .scalars()
            .all()
        )
        assert len(ops) == 1
        assert ops[0].message_id == msg_id

        refs = (
            (
                await db.execute(
                    select(MessageReference).where(MessageReference.message_id == msg_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(refs) == 1
        assert refs[0].type == "changeset"
        files = refs[0].meta_data.get("files", [])
        assert any(f["path"] == str(target) for f in files)


class TestExecuteCommandRealPath:
    """execute_command 通过真实 executor 的变更追踪契约（rm/mv/cp/sed/echo）。"""

    @pytest.mark.asyncio
    async def test_echo_redirect_add(self, real_env, tmp_path):
        tid = f"t-{uuid.uuid4().hex[:8]}"
        workdir = tmp_path / "w"
        workdir.mkdir()

        await _run_tool(
            str(workdir), tid, "bash",
            {"command": "echo hi > out.txt"},
            "c-1",
        )

        assert (workdir / "out.txt").read_text(encoding="utf-8").strip() == "hi"
        rows = await _rows(real_env, tid)
        assert len(rows) == 1
        assert rows[0].operation == "ADD"

    @pytest.mark.asyncio
    async def test_mv_delete_source_add_dest(self, real_env, tmp_path):
        tid = f"t-{uuid.uuid4().hex[:8]}"
        workdir = tmp_path / "w"
        workdir.mkdir()
        (workdir / "a.txt").write_text("aaa\n", encoding="utf-8")

        await _run_tool(
            str(workdir), tid, "bash",
            {"command": "mv a.txt b.txt"},
            "c-2",
        )

        assert (workdir / "b.txt").read_text(encoding="utf-8") == "aaa\n"
        assert not (workdir / "a.txt").exists()
        rows = await _rows(real_env, tid)
        ops = {r.operation: r.file_path for r in rows}
        assert "DELETE" in ops and ops["DELETE"].endswith("a.txt")
        assert "ADD" in ops and ops["ADD"].endswith("b.txt")

        # rewind 还原 source
        del_row = next(r for r in rows if r.operation == "DELETE")
        assert await _revert_one(del_row) == 1
        assert (workdir / "a.txt").read_text(encoding="utf-8") == "aaa\n"

    @pytest.mark.asyncio
    async def test_rm_delete_and_rewind(self, real_env, tmp_path):
        tid = f"t-{uuid.uuid4().hex[:8]}"
        workdir = tmp_path / "w"
        workdir.mkdir()
        (workdir / "del.txt").write_text("bye\n", encoding="utf-8")

        await _run_tool(
            str(workdir), tid, "bash",
            {"command": "rm del.txt"},
            "c-3",
        )

        assert not (workdir / "del.txt").exists()
        rows = await _rows(real_env, tid)
        assert len(rows) == 1
        assert rows[0].operation == "DELETE"
        assert rows[0].original_content == "bye\n"

        assert await _revert_one(rows[0]) == 1
        assert (workdir / "del.txt").read_text(encoding="utf-8") == "bye\n"

    @pytest.mark.asyncio
    async def test_cp_adds_dest(self, real_env, tmp_path):
        tid = f"t-{uuid.uuid4().hex[:8]}"
        workdir = tmp_path / "w"
        workdir.mkdir()
        (workdir / "src.txt").write_text("data\n", encoding="utf-8")

        await _run_tool(
            str(workdir), tid, "bash",
            {"command": "cp src.txt dst.txt"},
            "c-4",
        )

        assert (workdir / "dst.txt").read_text(encoding="utf-8") == "data\n"
        rows = await _rows(real_env, tid)
        # src 无变化（无行），dst 新增（ADD 一行）
        assert len(rows) == 1
        assert rows[0].operation == "ADD"
        assert rows[0].file_path.endswith("dst.txt")

    @pytest.mark.asyncio
    async def test_sed_inplace_edit(self, real_env, tmp_path):
        tid = f"t-{uuid.uuid4().hex[:8]}"
        workdir = tmp_path / "w"
        workdir.mkdir()
        (workdir / "f.txt").write_text("aaa\n", encoding="utf-8")

        await _run_tool(
            str(workdir), tid, "bash",
            {"command": "sed -i '' 's/aaa/bbb/' f.txt"},
            "c-5",
        )

        assert (workdir / "f.txt").read_text(encoding="utf-8") == "bbb\n"
        rows = await _rows(real_env, tid)
        assert len(rows) == 1
        assert rows[0].operation == "EDIT"
        assert rows[0].original_content == "aaa\n"

    @pytest.mark.asyncio
    async def test_background_command_not_tracked(self, real_env, tmp_path):
        """background 命令异步执行：确定性地不产生 FileOperation（时序无关）。"""
        tid = f"t-{uuid.uuid4().hex[:8]}"
        workdir = tmp_path / "w"
        workdir.mkdir()

        await _run_tool(
            str(workdir), tid, "bash",
            {"command": "echo bg > bg.txt", "background": True},
            "c-bg",
        )

        rows = await _rows(real_env, tid)
        assert len(rows) == 0
